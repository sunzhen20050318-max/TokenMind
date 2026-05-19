---
name: presentations
description: Build editable PowerPoint (.pptx) decks with native shapes, charts, tables, images, and a render-and-verify visual QA loop. Bundled Python scripts cover slide layout, design-system styling, industry presets, and PDF/PNG rendering via LibreOffice for inspection.
metadata: {"tokenmind":{"emoji":"🖼️","requires":{"bins":["soffice","pdftoppm"],"python":["pptx","pdf2image"]},"install":[{"id":"brew-libreoffice","kind":"brew","formula":"libreoffice","bins":["soffice"],"label":"Install LibreOffice (brew)"},{"id":"apt-libreoffice","kind":"apt","package":"libreoffice","bins":["soffice"],"label":"Install LibreOffice (apt)"},{"id":"win-libreoffice","kind":"download","url":"https://www.libreoffice.org/download/","bins":["soffice"],"label":"Install LibreOffice (Windows installer)"},{"id":"brew-poppler","kind":"brew","formula":"poppler","bins":["pdftoppm"],"label":"Install poppler (brew, for pdf2image)"},{"id":"apt-poppler","kind":"apt","package":"poppler-utils","bins":["pdftoppm"],"label":"Install poppler (apt, for pdf2image)"},{"id":"win-poppler","kind":"download","url":"https://github.com/oschwartz10612/poppler-windows/releases","bins":["pdftoppm"],"label":"Install poppler (Windows binaries)"},{"id":"pip","kind":"pip","packages":["python-pptx","pdf2image","Pillow"],"label":"Install Python deps (pip)"}]}}
---

# Presentations skill

Produce editable PowerPoint decks where every shape, chart, table, and text run is real OOXML — not a screenshot. Build the structure with Python helpers, restyle with a design system, then render to PNG via LibreOffice for visual QA.

The target is a deck that feels like a strong editor, a strong analyst, and a strong designer built it together. For analytics narratives, investor / operating reviews, strategy stories, and product / business performance decks, treat "looks clean" as the minimum and aim for an audience-ready story.

---

## Tools + Contract

- All scripts run on **system Python**. Pip deps: `python-pptx`, `pdf2image`, `Pillow`. System binary: `soffice` (LibreOffice headless) for the render step, plus `poppler` (`pdftoppm`) for pdf2image.
- The **9 bundled scripts** under `scripts/` are the canonical surface. Prefer them over hand-rolling python-pptx code: stable CLIs, validate inputs, and are covered by **70 tests**. Every script has `--help`.
- Run scripts from a writable scratch directory (`/tmp/<task-id>/`), not from this skill's own folder. Render output (`slide-*.png`, intermediate PDF) belongs in scratch too.
- Final user-visible response: a Markdown link to the produced `.pptx` only. Don't surface intermediate PNGs / PDFs / verify reports unless the user explicitly asks for QA intermediates.

---

## Storytelling profiles

Read the matching profile narrative before composing slides — these describe **what stories the deck should tell**, what slides go where, what NOT to include. They are storytelling guidance, not styling rules.

- `profiles/consumer-retail.md`
- `profiles/engineering-platform.md`
- `profiles/finance-ir.md`
- `profiles/gtm-growth.md`
- `profiles/product-platform.md`
- `profiles/appendix-heavy.md`
- `profiles/template-and-edit.md`

For the *visual* preset that matches a profile (heading font, body font, accent color, background), use `apply_industry_profile.py` — see below.

Read `templates/design-system-template.md` and `templates/visual-qa-template.md` when defining a custom design system or planning the verification loop.

---

## General Rules

- Start composing quickly — the **Quick Script Surface** is your reference, don't burn turns probing python-pptx internals.
- Build deck **structure first** (titles, layout, placeholders), then **content** (text, charts, tables), then **styling** (`apply_design_system` / `apply_industry_profile`). Charts and tables get their own pass last so size/anchor decisions are informed by what's already on the slide.
- One slide = one primary idea. Don't cram analytics into every callout box; subordinate detail belongs in an appendix slide or a follow-up.
- For comparisons, prefer tables to bullet lists. For trends, prefer line charts to numbered text. For mixes/share, prefer bar/pie to multiple stacked numbers.
- **Inches, not pixels.** All position/size args are inches. Default 16:9 deck is `13.333 × 7.5 in`.
- Slide layout choice matters more than caption text. A "Title and Content" layout (index 1) is best for bulleted body; "Title Only" (5) is best for figure slides; "Blank" (6) is best for free-form composition.

---

## Error Recovery

- Read stderr — the scripts emit specific error text ("Series 'X': 3 values does not match 4 categories", etc.) instead of silently producing a broken deck.
- Fix the minimal call (off-by-one in `--data`, wrong slide index, hex with a `#` prefix) and rerun. The .pptx on disk is fine.
- If `render_deck.py` fails, the most common causes are (in order): soffice not installed → install LibreOffice; poppler missing → install poppler; soffice user-profile lock → script already uses an isolated profile, but a stale tmpfs can cause issues on Linux. Pass `--verbose` to see the soffice command and stderr.

---

## Quality Guidelines

- **Stay editable.** Use `add_chart_slide` / `add_table_slide` (native OOXML) over rasterized images of charts/tables. The whole point of .pptx over PDF is downstream editing.
- **Real design system.** Apply colors + fonts via `apply_design_system` or `apply_industry_profile` rather than handwriting hex on every text box. Re-runnable; cheaper to iterate.
- **Visual density.** ≤ 4 short bullet lines per body, ≤ 30 words per slide text-zone. Charts get titles. Tables get a header row. If a slide reads like an appendix, move it to one.
- **Mix structures.** Don't ship a 20-slide deck of identical "title + 5 bullets" layouts. Use figure slides (layout 5), comparison tables, charts, single-callout cards.
- **Verify visually.** `render_deck.py` is the only honest way to know how slides look — text-frame contents don't tell you about clipping, overflow, contrast issues, or chart legend placement.

---

## Completion Criteria

A deck is done when:

- `verify_deck.py` exits 0 against the expectations you asserted.
- `render_deck.py` produces clean PNGs (you've looked at them, fixed obvious defects, and re-rendered).
- Every slide has a clear single takeaway; titles are populated; no slide is empty.
- The `.pptx` opens in PowerPoint / Keynote / Google Slides without warnings about damaged content.

---

## Verification Workflow

```bash
# Structural audit
python scripts/verify_deck.py /tmp/deck.pptx
```

For gates, add `--expect-*`:

```bash
python scripts/verify_deck.py /tmp/deck.pptx \
    --expect-min-slides 6 \
    --expect-all-titled \
    --expect-charts-total ">=1" \
    --expect-no-empty-slides
```

Then visual:

```bash
# soffice + pdf2image → slide-01.png, slide-02.png, ...
python scripts/render_deck.py /tmp/deck.pptx --output-dir /tmp/qa --dpi 144

# Optional: contact-sheet all slides into one image for fast scanning
python scripts/make_contact_sheet.py /tmp/qa/slide-*.png \
    --output /tmp/qa/contact-sheet.png --cols 3
```

Look at the PNGs (or contact sheet). Common issues: text bleed off the right edge, chart legends covering the data, table columns crammed, dark text on dark background. Fix with `format_cells`-equivalent shape edits or by widening/repositioning shapes, then re-render.

Do **one focused visual repair pass**. Don't loop on minor polish once the deck reads cleanly.

---

## Quick Script Surface

All scripts under `scripts/` accept `--help`. CLIs are stable.

### `build_pptx.py` — Create a new deck

```bash
# Empty 16:9
python scripts/build_pptx.py --out /tmp/deck.pptx

# 4:3 or custom
python scripts/build_pptx.py --out /tmp/deck.pptx --size 4:3
python scripts/build_pptx.py --out /tmp/deck.pptx --width-in 11.69 --height-in 8.27

# Quick-start with a cover slide
python scripts/build_pptx.py --out /tmp/deck.pptx --cover-title "Q3 Results"
```

### `add_slide.py` — Add a slide using a layout

```bash
# See what layouts the deck offers
python scripts/add_slide.py /tmp/deck.pptx --list-layouts

# Title + Content with bullets
python scripts/add_slide.py /tmp/deck.pptx --layout 1 \
    --title "Key Findings" \
    --bullets '["Revenue up 12% YoY","Margin expanded 180 bps","Churn flat"]'

# Title Only (good for figure slides)
python scripts/add_slide.py /tmp/deck.pptx --layout 5 --title "Revenue Trend"

# Blank (free-form composition)
python scripts/add_slide.py /tmp/deck.pptx --layout 6

# Insert at a specific position
python scripts/add_slide.py /tmp/deck.pptx --layout 1 --title "Intro" --position 0
```

### `add_text_box.py` — Free-form text on any slide

Inches, top-left origin. Multi-paragraph via `\n` or `--text-file`.

```bash
python scripts/add_text_box.py /tmp/deck.pptx --slide 0 \
    --left 0.5 --top 0.4 --width 9 --height 1.0 \
    --text "Quarterly Results — Q3" \
    --font-size 36 --bold --align left
```

Supports `--bold` / `--italic` / `--font-size` / `--font-color HEX` / `--align left|center|right|justify`.

### `add_chart_slide.py` — Native PowerPoint chart

```bash
python scripts/add_chart_slide.py /tmp/deck.pptx --slide 1 \
    --left 0.5 --top 1.5 --width 9 --height 5 \
    --type bar \
    --data '{"categories":["Q1","Q2","Q3","Q4"],
             "series":{"Revenue":[120,140,170,200],
                       "Costs":[90,100,110,125]}}' \
    --title "FY24 Quarterly"
```

Types: `bar` / `column` / `line` / `pie`. Pie uses the first series only.

### `add_image_slide.py` — Picture on a slide

```bash
# Logo, preserve aspect ratio (only height given)
python scripts/add_image_slide.py /tmp/deck.pptx --slide 0 \
    --image ./logo.png --left 0.4 --top 0.4 --height 1.0

# Full-bleed hero (force fit)
python scripts/add_image_slide.py /tmp/deck.pptx --slide 1 \
    --image ./hero.jpg --left 0 --top 0 --width 13.333 --height 7.5
```

### `add_table_slide.py` — Native PowerPoint table

```bash
python scripts/add_table_slide.py /tmp/deck.pptx --slide 1 \
    --left 0.5 --top 2 --width 9 --height 2 \
    --data '[["Metric","Q3","Q4"],
             ["Revenue","\$12.1M","\$14.8M"],
             ["Margin","42%","47%"]]' \
    --header-row --header-bg 1F2937 --header-font-color FFFFFF
```

For long tables, prefer `--data-file ./roster.json`.

### `apply_design_system.py` — Restyle the deck

```bash
python scripts/apply_design_system.py /tmp/deck.pptx --design '{
  "heading_font":  "Inter",
  "body_font":     "Inter",
  "heading_color": "111827",
  "body_color":    "4B5563",
  "accent_color":  "2563EB",
  "slide_bg":      "FFFFFF"
}'
```

All 6 keys are optional. Re-runnable; never deletes shapes.

### `apply_industry_profile.py` — Curated preset

```bash
# See available profiles
python scripts/apply_industry_profile.py --list

# Dump the spec without applying
python scripts/apply_industry_profile.py --profile finance-ir --dump

# Apply a preset, optionally overriding a key
python scripts/apply_industry_profile.py /tmp/deck.pptx \
    --profile engineering-platform \
    --override accent_color=8B5CF6
```

Profiles: `consumer-retail` / `engineering-platform` / `finance-ir` / `gtm-growth` / `product-platform` / `appendix-heavy` / `template-and-edit`.

### `render_deck.py` — pptx → per-slide PNGs

```bash
python scripts/render_deck.py /tmp/deck.pptx \
    --output-dir /tmp/qa --dpi 144 --emit-pdf
```

Needs `soffice` + `pdftoppm` (poppler). On macOS the script also checks `/Applications/LibreOffice.app/Contents/MacOS/soffice` as a fallback.

### `make_contact_sheet.py` — Grid of slide previews

```bash
python scripts/make_contact_sheet.py /tmp/qa/slide-*.png \
    --output /tmp/qa/contact-sheet.png --cols 3
```

Useful after `render_deck` for at-a-glance review of every slide on one screen.

### `verify_deck.py` — Structural audit

See **Verification Workflow** above.

---

## Common pitfalls

- **Wrong slide index after insertion.** `add_slide --position 0` shifts every subsequent slide's index. Run `--list-layouts` *first* if you're unsure where things landed.
- **Pie chart with multi-series data.** The script silently drops everything past the first series — that's correct PPT behavior (pie shows one dimension), but a misled LLM ends up wondering where its "Costs" series went. Use `bar` if you need multiple series.
- **Hex color with leading `#`.** All scripts accept both `1F2937` and `#1F2937` (stripped internally), but stay consistent in your invocations to keep diffs clean.
- **Font names not installed.** `apply_design_system --heading-font "Inter"` writes the name into the OOXML; if the viewer doesn't have Inter installed, PowerPoint substitutes Calibri silently. Test on the destination platform if typography matters, or stick to safe families (Arial / Helvetica Neue / Georgia / Times New Roman).
- **Tables vs charts.** Avoid putting a styled table where a chart belongs. If the data has a trend, plot it; tables are for comparisons.
- **PDF rendering looks different from PowerPoint.** LibreOffice's renderer isn't pixel-identical to MS Office — close enough for QA but a known gap. If a slide looks 95% right in PNG, it'll look 99% right in PowerPoint.

---

## Workflow template

End-to-end for a polished deck:

```bash
DECK=/tmp/<task-id>/q3-review.pptx
QA=/tmp/<task-id>/qa

# 1. Skeleton
python scripts/build_pptx.py --out "$DECK" --cover-title "Q3 Review"

# 2. Structure first — every slide, no content yet
python scripts/add_slide.py "$DECK" --layout 1 --title "Agenda"
python scripts/add_slide.py "$DECK" --layout 5 --title "Revenue Trend"
python scripts/add_slide.py "$DECK" --layout 1 --title "Key Wins"
python scripts/add_slide.py "$DECK" --layout 5 --title "Customer Mix"
python scripts/add_slide.py "$DECK" --layout 1 --title "Next Quarter"

# 3. Content
python scripts/add_slide.py "$DECK" --layout 1 --title "Agenda" \
    --bullets '["Revenue","Wins","Outlook"]'

python scripts/add_chart_slide.py "$DECK" --slide 2 \
    --left 1 --top 1.5 --width 11 --height 5 \
    --type line \
    --data '{"categories":["Q1","Q2","Q3"],"series":{"Revenue":[10,14,18]}}' \
    --title "Quarterly Revenue (\$M)"

# 4. Industry preset → branded restyle
python scripts/apply_industry_profile.py "$DECK" --profile finance-ir

# 5. Verify
python scripts/verify_deck.py "$DECK" \
    --expect-min-slides 6 --expect-all-titled \
    --expect-charts-total ">=1" --expect-no-empty-slides

# 6. Visual QA
python scripts/render_deck.py "$DECK" --output-dir "$QA" --dpi 144
python scripts/make_contact_sheet.py "$QA"/slide-*.png \
    --output "$QA/contact.png" --cols 3
```

After eyeballing `$QA/contact.png`, fix any clipping / overflow / contrast issues with targeted `add_text_box` / `apply_design_system --override` calls, then re-render. Deliver `$DECK`.
