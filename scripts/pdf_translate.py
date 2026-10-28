#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pdf_translate.py — 在保留原版式的前提下，把 PDF 里的文字替换成另一种语言。

思路：不动任何图形元素，只把「文字层」挖掉再按原始基线坐标重新写回。
     · 图片 (images=PDF_REDACT_IMAGE_NONE) 与矢量图形 (graphics=PDF_REDACT_LINE_ART_NONE) 全部保留
     · 每个文本块所在「格子」的左右边界由矢量填充块 / 细竖线的边缘推断（带 y 轴重叠判断）
     · 一列里各块的左起点若完全一致 → 左对齐；否则 → 居中对齐（按原文本中心对中）
     · 译文比原文长时先自动换行，仍放不下再按比例微缩字号，并汇报超限项

子命令：
    extract  PDF -> spec.json          抽取文本块（含坐标、基线、字体、颜色、可用宽度）
    apply    spec.json -> PDF          按 tgt 字段回填译文
    verify   src.pdf out.pdf           自检：残留原文 / 文字重叠 / 越界
    render   PDF -> PNG                出图做目检

典型用法：
    python pdf_translate.py extract in.pdf -o spec.json --lang es
    # 编辑 spec.json：给每个 block 填 "tgt": "译文"；不翻译的留 null；要并掉的块写 "drop": true
    python pdf_translate.py apply spec.json -o out.pdf
    python pdf_translate.py verify in.pdf out.pdf --spec spec.json
    python pdf_translate.py render out.pdf -d png/
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import fitz

# --------------------------------------------------------------------------
# 字体：按原名做角色归并，找不到时回落到同族字体
# --------------------------------------------------------------------------
FONT_CANDIDATES = {
    "arial": ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
    "arialb": ["arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "calibri": ["calibri.ttf", "Calibri.ttf", "Carlito-Regular.ttf", "LiberationSans-Regular.ttf"],
    "calibrib": ["calibrib.ttf", "Calibri Bold.ttf", "Carlito-Bold.ttf", "LiberationSans-Bold.ttf"],
    "verdana": ["verdana.ttf", "Verdana.ttf", "DejaVuSans.ttf"],
    "verdanab": ["verdanab.ttf", "Verdana Bold.ttf", "DejaVuSans-Bold.ttf"],
    "times": ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf"],
    "timesb": ["timesbd.ttf", "Times New Roman Bold.ttf", "LiberationSerif-Bold.ttf"],
}

FONT_DIRS = [
    r"C:\Windows\Fonts",
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    "/usr/share/fonts/truetype/msttcorefonts",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts",
]

_ROLE_FONT = {}
_FITZ_FONT = {}


def role_of(pdf_font_name: str, flags: int = 0) -> str:
    """把 PDF 里的字体名归并成 arial/arialb/calibri/calibrib/verdana/... 之一。"""
    n = (pdf_font_name or "").lower()
    bold = ("bold" in n) or ("black" in n) or ("heavy" in n) or bool(flags & 16)
    if "calibri" in n or "carlito" in n or "segoe" in n:
        return "calibrib" if bold else "calibri"
    if "verdana" in n:
        return "verdanab" if bold else "verdana"
    if "times" in n or "song" in n or "serif" in n:
        return "timesb" if bold else "times"
    return "arialb" if bold else "arial"


def font_path(role: str):
    if role in _ROLE_FONT:
        return _ROLE_FONT[role]
    for name in FONT_CANDIDATES.get(role, []):
        for d in FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.exists(p):
                _ROLE_FONT[role] = p
                return p
    for other in ("arial", "arialb", "calibri", "calibrib"):
        for name in FONT_CANDIDATES[other]:
            for d in FONT_DIRS:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    _ROLE_FONT[role] = p
                    return p
    raise RuntimeError("找不到可用字体，请检查系统字体或改用已安装的 ffi 字体")


def fz_font(role: str):
    if role not in _FITZ_FONT:
        _FITZ_FONT[role] = fitz.Font(fontfile=font_path(role))
    return _FITZ_FONT[role]


def text_w(s: str, role: str, size: float) -> float:
    return fz_font(role).text_length(s, fontsize=size)


# --------------------------------------------------------------------------
# 几何工具
# --------------------------------------------------------------------------
def _hex(color: int) -> str:
    return "#%06x" % (color & 0xFFFFFF)


def _unhex(s: str) -> int:
    s = (s or "#000000").lstrip("#")
    return int(s[:6], 16)


def merge_rect(a, b):
    return fitz.Rect(min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))


def collect_edges(page: fitz.Page):
    """页面上的竖直边界：[(x, y0, y1)]，来自矢量填充块左右沿和细竖线。"""
    edges = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.width < 1.5 and r.height > 3:
            edges.append((round(r.x0, 1), r.y0, r.y1))
        if dr.get("fill") is not None and r.width > 2 and r.height > 1.5:
            edges.append((round(r.x0, 1), r.y0, r.y1))
            edges.append((round(r.x1, 1), r.y0, r.y1))
    return edges


def cell_bounds(box: fitz.Rect, edges, page_w: float, y_tol: float = 4.0):
    """文本块所在格子的左右沿。"""
    L, R = 24.0, page_w - 24.0
    for x, y0, y1 in edges:
        if y1 < box.y0 - y_tol or y0 > box.y1 + y_tol:
            continue
        if x <= box.x0 + 0.6 and x > L:
            L = x
        if x >= box.x1 - 0.6 and x < R:
            R = x
    return L, R


# --------------------------------------------------------------------------
# 文本块抽取
# --------------------------------------------------------------------------
def page_blocks(page: fitz.Page, pad: float = 3.5, merge_gap: float = 1.22):
    raw = page.get_text("rawdict")
    lines = []
    for b in raw["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            spans = [s for s in ln["spans"] if "".join(c["c"] for c in s["chars"]).strip()]
            if not spans:
                continue
            text = "".join("".join(c["c"] for c in s["chars"]) for s in spans)
            box = fitz.Rect(spans[0]["bbox"])
            for s in spans[1:]:
                box = merge_rect(box, fitz.Rect(s["bbox"]))
            lines.append({
                "text": text,
                "bbox": box,
                "origin": spans[0]["origin"],
                "font": spans[0]["font"],
                "size": round(spans[0]["size"], 2),
                "color": spans[0]["color"],
            })

    # 同一单元格内的多行合并：同 x 起点 + 同字体字号 + 行距 < merge_gap*字号
    lines.sort(key=lambda l: (round(l["bbox"].y0, 1), l["bbox"].x0))
    blocks = []
    for ln in lines:
        if blocks:
            prev = blocks[-1]
            gap = ln["origin"][1] - prev["baselines"][-1]
            if (abs(ln["bbox"].x0 - prev["x0"]) < 1.5
                    and abs(ln["size"] - prev["size"]) < 0.6
                    and ln["font"] == prev["font"]
                    and 0 < gap < merge_gap * ln["size"]):
                prev["lines"].append(ln["text"])
                prev["baselines"].append(ln["origin"][1])
                prev["bbox"] = merge_rect(prev["bbox"], ln["bbox"])
                prev["_boxes"].append(ln["bbox"])
                continue
        blocks.append({
            "lines": [ln["text"]],
            "baselines": [ln["origin"][1]],
            "bbox": fitz.Rect(ln["bbox"]),
            "x0": ln["bbox"].x0,
            "font": ln["font"],
            "size": ln["size"],
            "color": ln["color"],
            "_boxes": [ln["bbox"]],
        })

    edges = collect_edges(page)
    # 先算每块的格子边界，再按「同一列左起点是否一致」判断对齐
    for b in blocks:
        b["_L"], b["_R"] = cell_bounds(fitz.Rect(b["bbox"]), edges, page.rect.width)

    cols = {}
    for b in blocks:
        # 同列 + 同字体 + 同字号才算一组，避免把注释/页脚和表头混为一谈
        cols.setdefault((round(b["_L"]), b["font"], round(b["size"], 1)), []).append(b)
    for grp in cols.values():
        xs = [b["x0"] for b in grp]
        spread = (max(xs) - min(xs)) if len(xs) > 1 else 0.0
        for b in grp:
            b["_center"] = len(grp) > 1 and spread > 1.2
            b["_spread"] = round(spread, 2)

    out = []
    for i, b in enumerate(blocks):
        role = role_of(b["font"])
        L, R = b["_L"], b["_R"]
        if b["_center"]:
            centers = [(r.x0 + r.x1) / 2.0 for r in b["_boxes"]]
            cx = sum(centers) / len(centers)
            maxw = max((R - L) - 2 * pad, 10.0)
        else:
            cx = None
            indent = min(max(b["x0"] - L, pad), 9.0)
            maxw = max(R - b["x0"] - indent, 10.0)
        out.append({
            "id": "p%d_b%02d" % (page.number + 1, i + 1),
            "src": " ".join(b["lines"]).strip(),
            "lines": b["lines"],
            "baselines": [round(y, 2) for y in b["baselines"]],
            "bbox": [round(v, 2) for v in b["bbox"]],
            "x0": round(b["x0"], 2),
            "align": "center" if b["_center"] else "left",
            "cx": round(cx, 2) if cx is not None else None,
            "cell": [round(L, 1), round(R, 1)],
            "font": role,
            "size": b["size"],
            "color": _hex(b["color"]),
            "maxw": round(maxw, 1),
            "max_lines": len(b["lines"]),
            "tgt": None,
        })
    return out


def cmd_extract(a):
    doc = fitz.open(a.pdf)
    pages = []
    for page in doc:
        pages.append({
            "page": page.number + 1,
            "width": round(page.rect.width, 2),
            "height": round(page.rect.height, 2),
            "blocks": page_blocks(page, a.pad, a.merge_gap),
        })
    # source 存成相对 spec.json 的路径，仓库/协作场景换机器也能跑；
    # source_abs 留作兜底（跨盘符时无法求相对路径）
    spec_dir = os.path.dirname(os.path.abspath(a.out)) or os.getcwd()
    pdf_abs = os.path.abspath(a.pdf)
    try:
        rel = os.path.relpath(pdf_abs, spec_dir)
        if rel.startswith(".." + os.sep + ".."):
            rel = pdf_abs
    except ValueError:
        rel = pdf_abs
    spec = {
        "source": rel,
        "source_abs": pdf_abs,
        "options": {"pad": a.pad, "min_scale": a.min_scale, "line_factor": a.line_factor},
        "target_language": a.lang,
        "pages": pages,
    }
    if a.map and os.path.exists(a.map):
        mapping = json.load(open(a.map, encoding="utf-8"))
        hit = 0
        for pg in pages:
            for b in pg["blocks"]:
                for k, v in mapping.items():
                    if k.strip() == b["src"]:
                        b["tgt"] = v
                        hit += 1
                        break
        print("通过 --map 预填 %d 个文本块" % hit, file=sys.stderr)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    n = sum(len(p["blocks"]) for p in pages)
    print("已抽取 %d 页 / %d 个文本块 -> %s" % (len(pages), n, a.out))


# --------------------------------------------------------------------------
# 回填
# --------------------------------------------------------------------------
def wrap_text(text, role, size, maxw):
    out = []
    for para in str(text).split("\n"):
        words, cur = para.split(), ""
        for w in words:
            cand = (cur + " " + w).strip()
            if not cur or text_w(cand, role, size) <= maxw:
                cur = cand
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return [l for l in out if l != ""] or [""]


def resolve_source(spec, spec_path, override=None):
    """定位原文 PDF：--source > spec.source（相对 spec 目录）> spec.source_abs。"""
    base = os.path.dirname(os.path.abspath(spec_path))
    cands = []
    if override:
        cands.append(override)
    s = str(spec.get("source") or "")
    if s:
        cands.append(s if os.path.isabs(s) else os.path.join(base, s))
        cands.append(os.path.join(base, os.path.basename(s)))
    if spec.get("source_abs"):
        cands.append(spec["source_abs"])
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit("找不到原文 PDF。试过：\n  " + "\n  ".join(str(c) for c in cands)
             + "\n用 --source 指定原文路径。")


def cmd_apply(a):
    spec = json.load(open(a.spec, encoding="utf-8"))
    doc = fitz.open(resolve_source(spec, a.spec, a.source))

    opt = spec.get("options", {})
    min_scale = opt.get("min_scale", 0.84)
    line_factor = opt.get("line_factor", 1.2)

    warnings, done = [], 0
    for pg in spec["pages"]:
        page = doc[pg["page"] - 1]
        jobs, drops = [], []
        for b in pg["blocks"]:
            if b.get("drop"):
                drops.append(b)
                continue
            tgt = b.get("tgt")
            if not tgt or not str(tgt).strip():
                continue
            role, base = b["font"], float(b["size"])
            size, maxw = base, float(b.get("maxw") or 300)
            max_lines = int(b.get("max_lines", 99))
            lines = wrap_text(tgt, role, size, maxw)
            scale = 1.0
            while len(lines) > max_lines and scale > min_scale:
                scale = round(scale - 0.02, 2)
                size = round(base * scale, 3)
                lines = wrap_text(tgt, role, size, maxw)
            if len(lines) > max_lines:
                warnings.append("%s 行数超限 (%d>%d): %s" % (b["id"], len(lines), max_lines, tgt))
            if max(text_w(l, role, size) for l in lines) > maxw + 0.5:
                warnings.append("%s 宽度超限: %s" % (b["id"], tgt))
            jobs.append((b, lines, size, role))
            done += 1

        for b in list(drops) + [j[0] for j in jobs]:
            r = fitz.Rect(b["bbox"])
            r.x0 -= 0.8
            r.x1 += 0.8
            r.y0 -= 0.5
            r.y1 += 0.5
            page.add_redact_annot(r, fill=None)
        if drops or jobs:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)

        writers = {}
        for b, lines, size, role in jobs:
            gaps = [b["baselines"][i + 1] - b["baselines"][i] for i in range(len(b["baselines"]) - 1)]
            gap = sum(gaps) / len(gaps) if gaps else size * line_factor
            if gap < size * 0.95:
                gap = size * line_factor
            y0 = b["baselines"][0]
            if b.get("valign") == "center":
                # 以原文本的垂直中心为锚点重排，行数变化时保持视觉居中
                anchor = (b["baselines"][0] + b["baselines"][-1]) / 2.0
                y0 = anchor - (len(lines) - 1) * gap / 2.0
            w = writers.setdefault(_unhex(b["color"]), fitz.TextWriter(page.rect))
            for i, ln in enumerate(lines):
                y = y0 + i * gap
                x = b["cx"] - text_w(ln, role, size) / 2.0 if (b["align"] == "center" and b.get("cx") is not None) else b["x0"]
                w.append((x, y), ln, font=fz_font(role), fontsize=size)
        for color, w in writers.items():
            if not w.text_rect.is_empty:
                w.write_text(page, color=fitz.sRGB_to_pdf(color))

    doc.subset_fonts()
    meta = doc.metadata or {}
    if a.title:
        meta["title"] = a.title
        doc.set_metadata(meta)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    doc.save(a.out, garbage=4, deflate=True)
    print("已回填 %d 个文本块（另清除 %d 个占位块）-> %s" % (done, sum(1 for p in spec["pages"] for b in p["blocks"] if b.get("drop")), a.out))
    for w in warnings:
        print("  ! " + w)


# --------------------------------------------------------------------------
# 校验 / 出图
# --------------------------------------------------------------------------
def _spans(page):
    res = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            for s in ln["spans"]:
                if s["text"].strip():
                    res.append(s)
    return res


def cmd_verify(a):
    src = fitz.open(a.src)
    out = fitz.open(a.out)
    print("页数 %d/%d   尺寸 %s / %s" % (
        src.page_count, out.page_count,
        tuple(round(v, 1) for v in src[0].rect[2:]),
        tuple(round(v, 1) for v in out[0].rect[2:])))
    if src.page_count != out.page_count:
        print("  ! 页数不一致")

    problems = 0
    if a.spec:
        spec = json.load(open(a.spec, encoding="utf-8"))
        # 译文与原文相同的块（型号、IP68 等）本身就会命中，排除掉再判断残留
        srcs = [b["src"] for pg in spec["pages"] for b in pg["blocks"]
                if b.get("tgt") and not b.get("drop")
                and str(b["tgt"]).strip() != str(b["src"]).strip()]
        body = "\n".join(out[i].get_text() for i in range(out.page_count))
        left = [s for s in srcs if len(s) > 3 and s in body]
        if left:
            problems += 1
            print("  ! 仍有 %d 段原文未替换，例如: %r" % (len(left), left[:3]))
        else:
            print("  原文残留：无")
        pending = [b["id"] for pg in spec["pages"] for b in pg["blocks"] if not b.get("tgt") and not b.get("drop")]
        if pending:
            print("  未翻译（保留原文）%d 块: %s" % (len(pending), pending[:8]))

    for i in range(out.page_count):
        page = out[i]
        W, H = page.rect.width, page.rect.height
        spans = _spans(page)
        for s in spans:
            x0, y0, x1, y1 = s["bbox"]
            if x0 < 2 or y0 < 2 or x1 > W - 2 or y1 > H - 2:
                problems += 1
                print("  ! p%d 越界: %r @ %.1f-%.1f" % (i + 1, s["text"][:36], x0, x1))
        boxes = sorted([(fitz.Rect(s["bbox"]), s["text"]) for s in spans], key=lambda t: (t[0].y0, t[0].x0))
        for m in range(len(boxes)):
            for n in range(m + 1, min(m + 4, len(boxes))):
                r1, t1 = boxes[m]
                r2, t2 = boxes[n]
                inter = fitz.Rect(r1) & r2
                if inter.is_empty:
                    continue
                if inter.width * inter.height > 0.35 * min(r1.width * r1.height, r2.width * r2.height):
                    problems += 1
                    print("  ! p%d 文字重叠: %r <-> %r" % (i + 1, t1[:26], t2[:26]))
    print("校验通过：无残留、无越界、无重叠" if problems == 0 else "共 %d 处待确认" % problems)
    return problems


def cmd_render(a):
    doc = fitz.open(a.pdf)
    os.makedirs(a.dir, exist_ok=True)
    for i, page in enumerate(doc):
        p = os.path.join(a.dir, "%s_page%d.png" % (a.prefix, i + 1))
        page.get_pixmap(dpi=a.dpi).save(p)
        print(p)


def main():
    ap = argparse.ArgumentParser(description="保持版式的 PDF 文本替换工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="抽取文本块到 JSON")
    e.add_argument("pdf")
    e.add_argument("-o", "--out", required=True)
    e.add_argument("--pad", type=float, default=3.5, help="格内左右留白，推断可用宽度用")
    e.add_argument("--merge-gap", type=float, default=1.22, help="同格多行合并阈值（行距/字号）")
    e.add_argument("--min-scale", type=float, default=0.84)
    e.add_argument("--line-factor", type=float, default=1.2)
    e.add_argument("--lang", default="", help="目标语言备注")
    e.add_argument("--map", default="", help='预填用的 {"原句":"译文"} JSON')
    e.set_defaults(func=cmd_extract)

    p = sub.add_parser("apply", help="按 JSON 回填译文")
    p.add_argument("spec")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--source", default="", help="原文 PDF 路径（spec 里记录失效时用）")
    p.set_defaults(func=cmd_apply)

    v = sub.add_parser("verify", help="自检")
    v.add_argument("src")
    v.add_argument("out")
    v.add_argument("--spec", default="")
    v.set_defaults(func=cmd_verify)

    r = sub.add_parser("render", help="渲染 PNG")
    r.add_argument("pdf")
    r.add_argument("-d", "--dir", required=True)
    r.add_argument("--dpi", type=int, default=150)
    r.add_argument("--prefix", default="pg")
    r.set_defaults(func=cmd_render)

    a = ap.parse_args()
    rc = a.func(a)
    # verify 返回待确认项数量，便于 CI 用退出码卡关
    sys.exit(1 if rc else 0)


if __name__ == "__main__":
    main()
