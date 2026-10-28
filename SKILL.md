---
name: pdf-inplace-translate
description: >
  把 PDF 文档翻译成另一种语言，同时完整保留原版式、背景图、矢量表格、图标与二维码。
  当用户说「把这个 PDF 转成西班牙语/法语/德语版」「翻译这份说明书/规格书，版式别乱」
  「保持原设计做多语言版本」时使用。做法是挖掉文字层、按原始基线坐标回填译文，
  不重排版面，因此不会出现错行、错位、花屏。内置抽取、回填、自检、出图四个子命令。
description_en: >
  Translate a PDF into another language while preserving its exact layout, background artwork,
  vector tables, icons and QR codes. Redacts only the text layer and re-inserts the translation
  at the original baselines. Use when the user asks for a localized version of a brochure,
  datasheet, or spec sheet that must keep the original design.
license: MIT
---

# PDF 原位翻译（保持版式）

把 PDF 做多语言版本时，**不要重排**。重排必然丢失原设计（渐变、曲线、图标、表格合并单元格）。

正确做法：**只动文字层** —— 精确删除原文，再按原始基线坐标把译文写回去。
图片、矢量图形、表格填充、二维码全部原样保留，所以版式不可能错乱。

## 依赖

只依赖 PyMuPDF（`fitz`），Python 3.8+：

```bash
pip install pymupdf
```

还需要系统里有 Arial / Calibri / Verdana 之一（或其自由替代 Carlito、Liberation Sans、
DejaVu Sans）。脚本会按 `arial → LiberationSans → DejaVuSans` 的顺序自动回落，
所以 Linux 容器里也能跑。

脚本：`scripts/pdf_translate.py`（下文用 `$T` 代指其绝对路径）。

## 四步流程

### 1. 抽取

```bash
python $T extract 原文.pdf -o spec.json --lang es
```

输出每个文本块：`id / src / baselines / bbox / x0 / align / cx / cell / font / size /
color / maxw / max_lines`。脚本会：

- 合并同一单元格内的多行（行距 < 1.22×字号 且左起点、字体、字号一致）
- 用矢量填充块与细竖线的边缘推断「格子」左右边界，据此算 `maxw`（可用宽度）
- 判定对齐：同一列（同边界、同字体、同字号）里各块左起点若参差 → `center`，
  整齐一致 → `left`。`center` 的块会带 `cx`（原文本中心），译文按此对中

### 2. 翻译并回填 JSON

只改三个字段，其他别动：

| 字段 | 说明 |
|---|---|
| `tgt` | 译文。`null` = 保留原文不处理；`""` 无效 |
| `drop` | `true` = 只删除不写回（用于把多块并成一处的场景） |
| `max_lines` | 允许的行数。默认 = 原文行数；排版有余量时可调大 |
| `valign` | `"center"` = 按原文本垂直中心重排，一行原文换成两行时用它 |

回填时脚本自动：按 `maxw` 换行 → 行数超限就按 2% 步长缩字号（下限 `min_scale`）
→ 仍放不下则在终端报 `! 行数超限 / 宽度超限`。

### 3. 回填

```bash
python $T apply spec.json -o 输出.pdf --title "文件名-ES"
```

`spec.json` 的 `source` 存的是相对 spec 文件的路径，换目录/换机器仍可跑；原文挪走了用 `--source 新路径.pdf` 指定。

### 4. 自检 + 目检

```bash
python $T verify 原文.pdf 输出.pdf --spec spec.json   # 残留原文 / 越界 / 重叠
python $T render 输出.pdf -d png/ --dpi 150          # 出图，必须肉眼过一遍
```

`verify` 全绿也要看图：它会漏掉「文字压到图形上」这类问题（图形不是文字，检测不到重叠）。

## 翻译质量守则（踩过的坑）

1. **目标语言普遍更长**（英→西约 +15~25%）。`max_lines` 通常不能加，
   表格行高是固定的，硬塞第二行会压到下一行。**优先精简措辞**，而不是缩字号。
2. **单行单元格不能变两行**。遇到超长标签，用行业通用缩写
   （`Operating temperature` → `Temp. de funcionamiento`），别用整句。
3. **数字与符号本地化**：西/法/德用小数逗号（`5,5”`、`2,0 GHz`、`16,5 mm`），
   尺寸用 `×`，温度写 `°C`（Calibri 缺 `℃` U+2103 字形时会更保险）。
4. **技术串保持原样**：频段 `FDD-LTE: B1/B3/B5...`、`MIL-STD-810H`、`IP68`、
   `IEEE 802.11 a/b/g/n/ac`、型号、URL、电话、邮箱。
5. **品牌标识不译**：Logo 旁的 tagline、屏幕里的品牌字一般是矢量或位图，属品牌资产。
6. **首字母大写风格按目标语言习惯**：西语标题只首词大写（`Controlador de campo profesional`），
   若原稿是全大写版式则保持全大写（`CARACTERÍSTICAS`）。
7. `maxw` 是脚本估的**参考值**。若标题右侧有图标而脚本没识别到，
   手工把 `maxw` 改小，否则译文会压到图标上。

## 已知陷阱

- **不要用 `page.insert_text(fontname=...)`**，会抛 `need font file or buffer`。
  用 `fitz.TextWriter` + `fitz.Font(fontfile=...)`（脚本已封装）。
- **删除文字时**必须 `apply_redactions(images=PDF_REDACT_IMAGE_NONE,
  graphics=PDF_REDACT_LINE_ART_NONE, text=PDF_REDACT_TEXT_REMOVE)`，
  且 `add_redact_annot(..., fill=None)`。否则会连背景图、表格线一起挖白。
- **原文字体常有连字替换**（`ti`→`Ɵ`、`tt`→`Ʃ`、`fi`→`ﬁ`），
  靠字符串匹配定位会失败；一律按 bbox 操作。
- 基线坐标取自 `get_text("rawdict")` 的 `span["origin"]`，不是 bbox 顶端。
- `doc.subset_fonts()` 必须在 `save()` 之前，否则文件会因整字体内嵌而暴涨。
- 文本被写成 `U+2010` 连字符（复制出来是 `‐` 而非 `-`）是 PyMuPDF 的反查问题，
  渲染完全一致，可忽略。

## 交付前检查表

- [ ] `verify` 输出「校验通过：无残留、无越界、无重叠」
- [ ] 每页 PNG 目检：无文字压图标、无跨行挤压、居中标签居中
- [ ] 数字/单位/型号/URL 与原稿逐项核对
- [ ] 页数、页面尺寸与原稿一致
- [ ] 文件名带语言后缀；写入 PDF 标题元数据

参考案例见 `references/worked-example.md`。
