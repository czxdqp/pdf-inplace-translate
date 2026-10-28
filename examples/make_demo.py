#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成一个供演示/回归用的样例 PDF（英文），特征与原实战案例同类：
整幅色块背景 + 图形式图标 + 无边框的渐变填充表格 + 页脚。

    python examples/make_demo.py examples/demo_datasheet.pdf
"""
import sys

import fitz

W, H = 595.3, 841.9
M = 36.0                      # 页边距
INK = (0.10, 0.13, 0.17)
MUTED = (0.42, 0.46, 0.52)
BRAND = (0.85, 0.44, 0.13)    # 橙色强调
HEAD_BG = (0.11, 0.16, 0.24)

ROWS = [
    ("Product model", "ACME PX-200"),
    ("Input configuration", "Full QWERTY keypad, separated number/letter keys"),
    ("Operating temperature", "-30 \u00b0C to +60 \u00b0C"),
    ("Storage temperature", "-40 \u00b0C to +70 \u00b0C"),
    ("Wireless", "Wi-Fi 802.11 a/b/g/n/ac, Bluetooth 5.0"),
    ("Ingress protection", "IP68, MIL-STD-810H"),
    ("Dimensions", "221 \u00d7 78 \u00d7 16.5 mm, 380 g"),
]

FEATURES = [
    "Rugged housing rated for two-metre drops onto concrete.",
    "Sunlight-readable 5.5-inch display with glove-friendly touch.",
    "All-day battery, hot-swappable without losing the current job.",
]


def build(path):
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    # ---- 头部色块 ----
    page.draw_rect(fitz.Rect(0, 0, W, 150), color=None, fill=HEAD_BG)
    page.draw_rect(fitz.Rect(0, 150, W, 154), color=None, fill=BRAND)
    page.insert_text((M, 74), "ACME PX-200", fontname="hebo", fontsize=26,
                     color=(1, 1, 1))
    page.insert_text((M, 102), "Professional Field Controller", fontname="helv",
                     fontsize=13, color=(0.78, 0.82, 0.88))
    page.insert_text((M, 128), "DATASHEET  \u00b7  REV. 2024-02", fontname="helv",
                     fontsize=8, color=BRAND)

    # ---- 卖点 ----
    page.insert_text((M, 190), "HIGHLIGHTS", fontname="hebo", fontsize=12, color=INK)
    y = 216.0
    for txt in FEATURES:
        page.draw_circle(fitz.Point(M + 4, y - 3), 2.6, color=None, fill=BRAND)
        page.insert_text((M + 16, y), txt, fontname="helv", fontsize=9.5, color=INK)
        y += 19.0

    # ---- 规格表：无单元格线，靠整列填充块区分 ----
    top, left, lw = 300.0, M, 168.0
    rh = 26.0
    page.insert_text((M, top - 18), "SPECIFICATIONS", fontname="hebo", fontsize=12,
                     color=INK)
    page.draw_rect(fitz.Rect(left, top, W - M, top + rh * len(ROWS)),
                   color=None, fill=(0.96, 0.97, 0.98))
    # 标签列浅色底
    page.draw_rect(fitz.Rect(left, top, left + lw, top + rh * len(ROWS)),
                   color=None, fill=(0.90, 0.92, 0.95))
    for i, (k, v) in enumerate(ROWS):
        yy = top + rh * i
        if i:
            page.draw_line(fitz.Point(left, yy), fitz.Point(W - M, yy),
                           color=(0.85, 0.87, 0.90), width=0.6)
        page.insert_text((left + 10, yy + 17), k, fontname="hebo", fontsize=8.6,
                         color=INK)
        page.insert_text((left + lw + 12, yy + 17), v, fontname="helv", fontsize=8.6,
                         color=(0.20, 0.24, 0.30))

    # ---- 页脚 ----
    fy = H - 48
    page.draw_line(fitz.Point(M, fy - 16), fitz.Point(W - M, fy - 16),
                   color=(0.85, 0.87, 0.90), width=0.8)
    page.insert_text((M, fy), "Specifications are subject to change without notice.",
                     fontname="helv", fontsize=7.5, color=MUTED)
    page.insert_text((M, fy + 13), "ACME Instruments \u00b7 example.com \u00b7 +00 000 0000",
                     fontname="helv", fontsize=7.5, color=MUTED)

    doc.set_metadata({"title": "ACME PX-200 Datasheet (demo)",
                      "subject": "Demo document for pdf-inplace-translate"})
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    print("wrote", path)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "examples/demo_datasheet.pdf")
