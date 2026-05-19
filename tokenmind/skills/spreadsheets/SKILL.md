---
name: spreadsheets
description: "Create, modify, analyze, visualize, or work with spreadsheet files (`.xlsx`, `.xls`, `.csv`, `.tsv`) using bundled Python helper scripts. Covers formulas, formatting, charts, data validation, and structural verification."
metadata: {"tokenmind":{"emoji":"📊","requires":{"python":["openpyxl"]},"install":[{"id":"pip","kind":"pip","packages":["openpyxl"],"label":"Install openpyxl (pip)"}]}}
---

# Spreadsheets skill

Produce correct, polished `.xlsx` artifacts that complete the user's request. Layout, readability, style, adherence to industry norms, and correctness all matter — a strong analyst-built workbook is the bar, not just a functional grid.

For complex analytical, financial, or research workbooks: plan the structure before writing. A good default shape is **executive summary / dashboard first, then sources & assumptions, then model / detail sheets**. For simple trackers and templates, prioritize fast delivery without over-engineering.

For style nuance read `style_guidelines.md`. For charting decisions read `charts.md`.

---

## Tools + Contract

- All scripts in this skill run on **system Python**. Required pip package: `openpyxl`. Install via `pip install openpyxl` if it's missing.
- The **8 bundled scripts** under `scripts/` are the canonical surface. Prefer them over hand-rolling openpyxl: they have stable CLIs, validate inputs, and are covered by 53 tests. Each accepts `--help`.
- Run scripts from a writable scratch directory (`/tmp/<task-id>/`), not from this skill's own folder.
- The final user-visible message should include a Markdown link to the produced `.xlsx` only — do not surface intermediate scratch files, debug JSON, or the verification report unless the user asks.
- For analysis that goes beyond workbook authoring (parsing source PDFs, statistical computations, etc.), it's fine to bring in `pandas` / `numpy` / `pypdf` as needed and feed results into the scripts via JSON/CSV.
- Do not invent additional builder libraries (xlsxwriter, pandas `ExcelWriter`, etc.) unless the user explicitly asks for a non-openpyxl fallback — the scripts here are the agreed surface.

---

## Domain Requirements

Read the matching domain template only when the request clearly relates to that domain:

- **Finance / accounting / valuation / forecasting / budgeting / IB / DCF / multi-statement models / sensitivity analysis**: `templates/financial_models.md`
- **Healthcare / clinical / hospital / staffing / care delivery workbooks**: `templates/healthcare.md`
- **Marketing / advertising / campaigns / funnels / CRM / growth / attribution / ROI**: `templates/marketing_advertising.md`
- **Scientific research / experiments / lab measurements / surveys / reproducibility / protocol data**: `templates/scientific_research.md`

Read all that clearly apply. Don't load domain templates for lightweight formatting/edit tasks unless the user asks.

Add a "Checks" sheet only for models where correctness depends on linked calculations, source reconciliation, or financial-statement integrity.

---

## General Rules

- Start meaningful edits quickly; don't burn turns on API exploration — the **Quick Script Surface** section below is the reference.
- For multi-sheet workbooks: build the non-formula inputs + tables on every sheet first, *then* populate cross-sheet formulas. References to an empty cell will surface as `#REF!` or `0` and you'll have to redo them.
- If asked to **edit** an existing workbook, prefer the smallest local change. Don't autofit, restyle, or rewrap sheet-wide unless the user explicitly asked.
- When extending tables, keep formulas / conditional formatting / chart ranges consistent — e.g. adding a column D to a table that has conditional formatting on `A1:C5` means re-applying CF to `A1:D5`.
- For column widths, measure the longest entry in the **relevant data range** and pick a width with a reasonable cap (60 chars max in our `csv_to_xlsx --auto-fit`). Don't autofit the entire sheet.
- The user may ask a **question** instead of an edit. Answer from the workbook content using `verify_xlsx.py` to dump structure — don't speculate and don't make unsolicited edits.

---

## Error Recovery

On script error:
1. Read the stderr message. The scripts emit clear error text — they don't silently swallow problems.
2. Make the minimal patch (correct a cell ref, fix a range syntax, etc.) — don't rewrite the whole workbook.
3. The workbook state on disk is fine; just rerun the failing step.

Don't loop on similar failures. If a third try fails, surface the blocker to the user.

---

## Quality Guidelines

- **Layout stays bounded**: avoid extreme widths/heights, cap auto-fit at sensible bounds.
- **Logic via formulas, not paint**: derived values should be `=B2*1.1`, not the typed result `132`. Use `add_formula.py --fill-range --formula "=B{row}*1.1"` for fill-down.
- **References, not magic numbers**: `=H6*(1+$B$3)` not `=H6*1.07`. Put the rate in a labeled cell.
- **Empty templates look empty**: count / ranking / IRR / variance formulas should guard against unfilled inputs and return `""`, `0`, or "No entries yet" rather than `#DIV/0!`. Alternatively, prefill 2-3 example rows.
- **Visual summary on tracker / planning requests**: a KPI block, chart, or small dashboard area.
- **At least one native Excel chart** on dashboard / visualization / KPI / trend / schedule prompts with plottable data. Don't substitute styled tables for charts silently.
- **Tables / freeze panes / filters / data validation** are real Excel structures — use them on presentation-ready workbooks, not just range formatting.

---

## Completion Criteria

A workbook is done when:

- All content is populated and formulas compute (no `#REF!` / `#DIV/0!` / `#VALUE!` / `#NAME?` / `#N/A` in key ranges).
- `verify_xlsx.py` exits 0 against the expectations you asserted.
- Layout is organized, legible, aligned to the request style.
- The `.xlsx` is saved to a stable path the user can fetch.

---

## Verification Workflow

Before final delivery, run `verify_xlsx.py` against the produced workbook.

```bash
# Plain structural report (JSON, LLM-friendly)
python scripts/verify_xlsx.py /tmp/wb.xlsx
```

That returns shape info per sheet: `max_row`, `max_column`, `cell_count`, `formula_count`, `chart_count`, `merged_ranges`.

For correctness gates, add `--expect-*` flags. The script exits non-zero on any failure:

```bash
python scripts/verify_xlsx.py /tmp/wb.xlsx \
    --expect-sheets "Dashboard,Detail,Assumptions" \
    --expect-min-rows "Detail=20" \
    --expect-charts "Dashboard>=1" \
    --expect-no-empty-sheets
```

If a check fails, fix the workbook (`add_chart.py`, `set_values.py`, `add_formula.py`) and rerun. Don't paper over the failure by relaxing the expectation unless the user agreed.

Beyond `verify_xlsx`, do one **focused visual repair pass**: open the file mentally — does the Dashboard fit on a screen? Are headers clipped? Are number formats applied where money is shown? Fix obvious defects, then ship. Don't loop on polish.

---

## Source, PDF, and Attachment Processing

- For PDF / 10-K / 10-Q inputs: use `pypdf` (if available) to extract, then one structured-extraction script that produces a dict / JSON. Avoid repeated `rg` / `grep` passes over the same text.
- Source notes stay compact: file name, section/table label, enough context to audit the number. Don't paste large PDF excerpts into the workbook unless requested.
- Other bundled Python libs you can lean on: `pandas`, `numpy`, `python-docx`, `reportlab`.

---

## Quick Script Surface

All scripts under `scripts/` accept `--help`. CLIs are stable.

### `build_xlsx.py` — Create a new workbook

```bash
python scripts/build_xlsx.py --out /tmp/wb.xlsx --sheet-name "Summary"
# --overwrite to replace an existing file
```

### `add_sheet.py` — Add a sheet to an existing workbook

```bash
python scripts/add_sheet.py /tmp/wb.xlsx --name "Assumptions"
# --position 0 to insert as first tab
# --if-exists error|ignore|rename  (default: error)
```

### `set_values.py` — Write cells (three input shapes)

```bash
# 1) Sparse cell map
python scripts/set_values.py /tmp/wb.xlsx --sheet Dashboard \
    --cells '{"A1": "Revenue", "B1": 1200, "C1": "=B1*1.1"}'

# 2) Dense 2D rows starting at an origin cell
python scripts/set_values.py /tmp/wb.xlsx --sheet Detail \
    --rows '[["Name","Qty"],["Widget",10],["Gadget",7]]' --start A1

# 3) CSV import
python scripts/set_values.py /tmp/wb.xlsx --sheet Imported \
    --csv ./data.csv --start A2
```

A leading `=` in a string is preserved as a formula. Numbers / booleans pass through as native types.

### `add_formula.py` — Single-cell or fill-range formulas with templates

```bash
# Single cell
python scripts/add_formula.py /tmp/wb.xlsx --sheet Detail \
    --cell D2 --formula "=SUM(A2:C2)"

# Fill down: {row} is substituted per row (D2→D11)
python scripts/add_formula.py /tmp/wb.xlsx --sheet Detail \
    --fill-range D2:D11 --formula "=SUM(A{row}:C{row})"

# Fill across: {col} is substituted per column (B12→E12)
python scripts/add_formula.py /tmp/wb.xlsx --sheet Detail \
    --fill-range B12:E12 --formula "=SUM({col}2:{col}11)"
```

Tokens: `{row}` → current row number, `{col}` → current column letter.

### `format_cells.py` — Font / fill / alignment / number format / border

```bash
# Header row
python scripts/format_cells.py /tmp/wb.xlsx --sheet Dashboard --range A1:F1 \
    --bold --bg-color 1F2937 --font-color FFFFFF --align center

# Currency
python scripts/format_cells.py /tmp/wb.xlsx --sheet Dashboard --range D2:D100 \
    --number-format "\$#,##0.00"

# Percentage
python scripts/format_cells.py /tmp/wb.xlsx --sheet Dashboard --range E2:E100 \
    --number-format "0.00%"

# Outline border
python scripts/format_cells.py /tmp/wb.xlsx --sheet Dashboard --range A1:F10 \
    --border thin
```

Hex colors are 6-digit RGB (no leading `#`). Setting `--bold` preserves existing font size.

### `add_chart.py` — Bar / line / pie charts

```bash
# Bar with categories in column A, data in column B
python scripts/add_chart.py /tmp/wb.xlsx --sheet Sales \
    --type bar --data B1:B13 --categories A2:A13 \
    --titles-from-data --anchor D2 --title "Monthly Revenue"

# Line with multiple series (each column = a series)
python scripts/add_chart.py /tmp/wb.xlsx --sheet KPI \
    --type line --data B1:D13 --categories A2:A13 \
    --titles-from-data --anchor F2

# Pie
python scripts/add_chart.py /tmp/wb.xlsx --sheet Mix \
    --type pie --data B2:B7 --categories A2:A7 --anchor D2
```

Include the header row in `--data` when passing `--titles-from-data` so the first row becomes the series legend.

### `csv_to_xlsx.py` — Import a CSV as a sheet

```bash
# New workbook (sheet name defaults to CSV stem)
python scripts/csv_to_xlsx.py ./sales.csv --out /tmp/wb.xlsx

# Append to existing workbook
python scripts/csv_to_xlsx.py ./data.csv --workbook /tmp/wb.xlsx \
    --sheet "Imported" --header-row --auto-fit

# Coerce numeric-looking strings into int/float
python scripts/csv_to_xlsx.py ./prices.csv --out /tmp/wb.xlsx --coerce-numbers

# Custom delimiter (.psv / .tsv)
python scripts/csv_to_xlsx.py ./pipe.psv --out /tmp/wb.xlsx --delimiter "|"
```

`--header-row` styles row 1 as bold. `--auto-fit` sets column widths via a character-count heuristic (capped 6–60). `--coerce-numbers` is opt-in so identifiers (`"007"`, `"01234"`) stay as strings by default.

### `verify_xlsx.py` — Structural audit + assertions

See **Verification Workflow** above.

---

## Common pitfalls

- **Forgetting the `=` prefix in formulas** → `add_formula.py` rejects this loudly. `set_values.py --cells` would silently store `"SUM(A2:C2)"` as text — always check the leading `=`.
- **Sheet names with `/` or `?` or longer than 31 chars** → Excel rejects on open. `csv_to_xlsx.py` auto-truncates to 31; for other scripts, pre-trim the name yourself.
- **Chart `--data` excluding header but `--titles-from-data` set** → first data row becomes the legend label. Match `--data` range to whether you pass `--titles-from-data`.
- **Pie chart with multi-column data** → only the first series is rendered. Pies want a single column of values + a single column of categories.
- **Filling formulas with absolute refs** → `{row}` / `{col}` template substitution is purely textual. `=SUM($A$2:$A$10)` stays the same on every fill — that's what you want for a fixed range; use `=SUM(A{row}:E{row})` for a per-row sum.
- **`format_cells.py --bold` alone** does NOT change font size. Pass `--font-size N` if you also want a size bump.

---

## Workflow template

Typical end-to-end for a new dashboard workbook:

```bash
WB=/tmp/<task-id>/dashboard.xlsx

# 1. Create
python scripts/build_xlsx.py --out "$WB" --sheet-name Dashboard

# 2. Add detail / assumption sheets
python scripts/add_sheet.py "$WB" --name Detail
python scripts/add_sheet.py "$WB" --name Assumptions

# 3. Populate inputs first
python scripts/set_values.py "$WB" --sheet Assumptions \
    --rows '[["Growth rate", 0.07], ["Tax rate", 0.21]]' --start A1

python scripts/set_values.py "$WB" --sheet Detail \
    --csv ./source.csv --start A1

# 4. Cross-sheet formulas after inputs exist
python scripts/add_formula.py "$WB" --sheet Detail \
    --fill-range D2:D100 --formula "=B{row}*(1+Assumptions!\$B\$1)"

# 5. Dashboard summary
python scripts/set_values.py "$WB" --sheet Dashboard \
    --cells '{"A1":"Total Revenue","B1":"=SUM(Detail!D:D)","A2":"Avg Margin","B2":"=AVERAGE(Detail!E:E)"}'

# 6. Format
python scripts/format_cells.py "$WB" --sheet Dashboard --range A1:B2 \
    --bold --number-format "\$#,##0"

# 7. Chart
python scripts/add_chart.py "$WB" --sheet Detail \
    --type bar --data D1:D101 --categories A2:A101 \
    --titles-from-data --anchor F2 --title "Revenue"

# 8. Verify
python scripts/verify_xlsx.py "$WB" \
    --expect-sheets "Dashboard,Detail,Assumptions" \
    --expect-charts "Detail>=1" \
    --expect-no-empty-sheets
```
