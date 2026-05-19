#!/usr/bin/env python3
"""Create a new empty .xlsx workbook.

The companion scripts (``add_sheet``, ``set_values``, ``add_chart``,
``add_formula``, ``format_cells``, ``verify_xlsx``) mutate the workbook
file in place after it has been created here.

Examples
--------

  # Bare workbook with a default Sheet
  python build_xlsx.py --out /tmp/wb.xlsx

  # First sheet renamed to "Summary"
  python build_xlsx.py --out /tmp/wb.xlsx --sheet-name Summary

  # Overwrite an existing file
  python build_xlsx.py --out /tmp/wb.xlsx --overwrite
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - guarded by skill requires.python
    print(
        "Error: openpyxl is not installed. Run: pip install openpyxl",
        file=sys.stderr,
    )
    sys.exit(2)


def build_xlsx(out: Path, sheet_name: str = "Sheet1", overwrite: bool = False) -> Path:
    """Create a new workbook at ``out`` with a single sheet."""
    if out.exists() and not overwrite:
        raise FileExistsError(
            f"{out} already exists. Pass --overwrite to replace it."
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    if ws is None:
        # openpyxl always creates an active sheet for a new workbook, but
        # keep this guard so the type-checker is satisfied and any
        # forward-compat change surfaces a clear error.
        raise RuntimeError("openpyxl produced a workbook without an active sheet")
    ws.title = sheet_name
    wb.save(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="Path to write the .xlsx file")
    parser.add_argument(
        "--sheet-name",
        default="Sheet1",
        help="Name of the initial sheet (default: Sheet1)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    args = parser.parse_args(argv)

    try:
        path = build_xlsx(args.out, args.sheet_name, args.overwrite)
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Created {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
