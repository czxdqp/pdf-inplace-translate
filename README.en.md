# pdf-inplace-translate

**Translate a PDF without touching its layout.** The text layer is redacted and the translation is re-inserted at the original baselines — background artwork, gradients, vector tables, icons and QR codes stay byte-for-byte intact, so the layout *cannot* break.

[中文说明](README.md) · [Example](examples/) · [Case study](references/worked-example.md)

| Source (EN) | Output (ES) |
|---|---|
| ![before](examples/preview_en.png) | ![after](examples/preview_es.png) |

Both pages were produced by `examples/make_demo.py` and are real output. Note the column fills, table rules, orange bullets and header band are all untouched — only the text changed.

---

## Why "in-place"

There are two ways to localize a PDF:

| Approach | Result |
|---|---|
| Extract text → translate → re-typeset a new PDF | Design is gone: gradients dropped, icons moved, merged cells broken, QR code redrawn by hand |
| **Replace only the text layer, leave every graphic alone** | 100% identical layout, because nothing was ever re-laid-out |

This tool takes the second path:

1. **Precise redaction** — `add_redact_annot(fill=None)` + `apply_redactions(images=IMAGE_NONE, graphics=LINE_ART_NONE, text=TEXT_REMOVE)`. Only text objects are removed; artwork and vector rules are untouched.
2. **Baseline-accurate re-insertion** — coordinates come from `span["origin"]` (the baseline, not the bbox top), written back with `TextWriter`, inheriting weight, size, colour and alignment.
3. **Automatic fitting** — target languages usually run 15–25% longer. Lines wrap to the inferred cell width, the font shrinks in 2% steps if the line budget is exceeded, and anything still overflowing is reported.

## Install

```bash
git clone https://github.com/<your-name>/pdf-inplace-translate.git
cd pdf-inplace-translate
pip install -r requirements.txt     # just pymupdf
```

You need a system font family (Arial / Calibri / Verdana, or a free substitute such as Carlito, Liberation Sans, DejaVu Sans). The script falls back `arial → LiberationSans → DejaVuSans`, so it also runs in a bare Linux container.

## Try it in 30 seconds

The repo ships a sample document plus a pre-filled Spanish spec:

```bash
python examples/make_demo.py examples/demo_datasheet.pdf
python scripts/pdf_translate.py apply examples/demo.spec.json -o /tmp/demo_es.pdf --title "Demo ES"
python scripts/pdf_translate.py verify examples/demo_datasheet.pdf /tmp/demo_es.pdf --spec examples/demo.spec.json
python scripts/pdf_translate.py render /tmp/demo_es.pdf -d png/
```

## Workflow

### 1. Extract

```bash
python scripts/pdf_translate.py extract input.pdf -o spec.json --lang es
```

Each block comes out like this — no manual coordinate hunting:

```json
{
  "id": "p2_b14",
  "src": "Operating temperature",
  "baselines": [352.1],
  "x0": 116.7,
  "align": "left",
  "cx": null,
  "cell": [115.6, 214.5],
  "font": "calibri",
  "size": 9.0,
  "color": "#231f20",
  "maxw": 92.0,
  "max_lines": 1,
  "tgt": null
}
```

The extractor does the tedious parts:

- **Merges multi-line cells** — same left edge, same font, same size, leading < 1.22× font size
- **Infers cell bounds** — from the edges of vector fill rects and thin vertical rules, with y-overlap checks so unrelated rules aren't picked up
- **Detects alignment** — within a column (same bounds + font + size), ragged left edges → `center` with a `cx` anchor; flush edges → `left`
- **Computes usable width** — `maxw = cell right edge − text start − padding`

### 2. Fill in the translations

Only these keys are yours to write:

| Key | Meaning |
|---|---|
| `tgt` | Translation. `null` = keep the source (part numbers, `IP68`, …) |
| `drop` | `true` = delete without writing (merge two blocks into one) |
| `max_lines` | Line budget. Defaults to the source line count; raise it for tall merged cells |
| `valign` | `"center"` = re-balance vertically around the original text centre |

Bulk-fill from a glossary with `--map`:

```bash
python scripts/pdf_translate.py extract input.pdf -o spec.json --lang de \
       --map glossary.json     # {"Operating temperature": "Betriebstemperatur", ...}
```

### 3. Apply

```bash
python scripts/pdf_translate.py apply spec.json -o output.pdf --title "name-DE"
```

`spec.json` stores `source` as a path relative to the spec file (with `source_abs` as a fallback), so the repo works after being cloned to another machine or folder. If the source PDF moved, pass `--source new/path.pdf`.

### 4. Verify — then actually look

```bash
python scripts/pdf_translate.py verify input.pdf output.pdf --spec spec.json
python scripts/pdf_translate.py render output.pdf -d png/ --dpi 150
```

`verify` reports leftover source text, out-of-bounds spans, and overlaps:

```
Pages 1/1   size (595.3, 841.9) / (595.3, 841.9)
  leftover source: none
  untranslated (kept as-is) 5 blocks: ['p1_b01', 'p1_b10', ...]
OK: no leftovers, no overflow, no overlap
```

> **A green `verify` is not enough — render and look.** It cannot catch text landing on top of a graphic, because graphics have no text bbox.

## CLI

| Command | Purpose | Key options |
|---|---|---|
| `extract` | PDF → spec.json | `-o`, `--lang`, `--map`, `--pad`, `--merge-gap` |
| `apply` | spec.json → PDF | `-o`, `--title` (writes PDF metadata), `--source` (override source PDF) |
| `verify` | self-check | `--spec` (enables leftover-source detection) |
| `render` | PDF → PNG | `-d`, `--dpi`, `--prefix` |

`--min-scale` (0.84) caps how far the font may shrink; `--line-factor` (1.2) is the leading fallback.

## Translation rules that matter

1. **Target text is longer**, and table rows are fixed height — you usually cannot raise `max_lines`. Tighten the wording instead of shrinking the font.
2. **Single-line cells must stay single-line.** Use conventional abbreviations: `Operating temperature` → `Temp. de funcionamiento`.
3. **Localize numbers**: decimal comma for ES/FR/DE (`5,5"`, `16,5 mm`); write `°C` rather than `℃` (many fonts lack U+2103).
4. **Never touch technical strings**: band numbers, `MIL-STD-810H`, `IP68`, `IEEE 802.11 a/b/g/n/ac`, model numbers, URLs, phone numbers, emails.
5. **Don't translate brand marks** next to logos or inside device screenshots — those are vector/raster brand assets.
6. **Follow the target language's casing**: Spanish headings capitalize only the first word; keep all-caps if the source is all-caps.
7. **`maxw` is a heuristic.** If a heading has an icon to its right that the extractor missed, lower it manually or the text will run into the icon.

## Pitfalls

- **Don't use `page.insert_text(fontname=...)`** with an external font file — it raises `need font file or buffer`. Use `fitz.TextWriter` + `fitz.Font(fontfile=...)` (already wrapped).
- **Redaction needs all three flags** — `images=PDF_REDACT_IMAGE_NONE`, `graphics=PDF_REDACT_LINE_ART_NONE`, `text=PDF_REDACT_TEXT_REMOVE`, plus `fill=None`. Otherwise artwork and rules get punched out.
- **Source PDFs often use ligature substitution** (`ti`→`Ɵ`, `fi`→`ﬁ`), so string matching fails. Always locate by bbox.
- **Baselines** come from `span["origin"]`, not the bbox top.
- **`doc.subset_fonts()` must run before `save()`**, or the file balloons with full embedded fonts.
- `U+2010` hyphens appearing in copied text (`‐`) is a PyMuPDF reverse-lookup quirk; rendering is identical.

## As an agent skill

`SKILL.md` is a ready-to-use skill definition (WorkBuddy / Claude Skills format). Drop the directory into `~/.workbuddy/skills/` and a request like *"translate this PDF into German, keep the layout"* will drive all four steps automatically.

## Limitations

- **Scanned PDFs are unsupported** — no text layer; run OCR first.
- **Text overlapping graphics needs human judgement** — the script has no idea an icon is there.
- **Very tight row heights** (< 1.2× font size) force heavy font shrinking; better to shorten the copy.
- **No reading-order / tag structure handling** — great for brochures and datasheets, not for accessibility-critical documents.

## Fair use

Use this only on documents you have the right to modify. Translating and redistributing someone else's work raises copyright and trademark questions — check your licence first.

## License

MIT
