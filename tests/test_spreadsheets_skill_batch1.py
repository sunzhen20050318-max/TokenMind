"""Tests for spreadsheets skill batch 1: build_xlsx / add_sheet / set_values."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

SKILL_DIR = Path(__file__).resolve().parent.parent / "tokenmind" / "skills" / "spreadsheets" / "scripts"


def _load_script(path: Path):
    """Import a CLI script as a module so we can call its functions directly."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build_xlsx():
    return _load_script(SKILL_DIR / "build_xlsx.py")


@pytest.fixture(scope="module")
def add_sheet():
    return _load_script(SKILL_DIR / "add_sheet.py")


@pytest.fixture(scope="module")
def set_values():
    return _load_script(SKILL_DIR / "set_values.py")


# --- build_xlsx ---------------------------------------------------------------


def test_build_xlsx_creates_file_with_default_sheet(tmp_path, build_xlsx):
    out = tmp_path / "wb.xlsx"
    result = build_xlsx.build_xlsx(out)
    assert result == out
    assert out.is_file()
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Sheet1"]


def test_build_xlsx_custom_sheet_name(tmp_path, build_xlsx):
    out = tmp_path / "named.xlsx"
    build_xlsx.build_xlsx(out, sheet_name="Summary")
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Summary"]


def test_build_xlsx_refuses_to_clobber(tmp_path, build_xlsx):
    out = tmp_path / "wb.xlsx"
    build_xlsx.build_xlsx(out)
    with pytest.raises(FileExistsError):
        build_xlsx.build_xlsx(out, overwrite=False)


def test_build_xlsx_overwrite_flag(tmp_path, build_xlsx):
    out = tmp_path / "wb.xlsx"
    build_xlsx.build_xlsx(out)
    # No error when --overwrite is set
    build_xlsx.build_xlsx(out, sheet_name="Replaced", overwrite=True)
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Replaced"]


def test_build_xlsx_creates_parent_dirs(tmp_path, build_xlsx):
    out = tmp_path / "nested" / "deeper" / "wb.xlsx"
    build_xlsx.build_xlsx(out)
    assert out.is_file()


# --- add_sheet ---------------------------------------------------------------


def _make_wb(tmp_path: Path) -> Path:
    out = tmp_path / "wb.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Sheet1"
    wb.save(out)
    return out


def test_add_sheet_appends_by_default(tmp_path, add_sheet):
    wb_path = _make_wb(tmp_path)
    final = add_sheet.add_sheet(wb_path, "Detail")
    assert final == "Detail"
    wb = openpyxl.load_workbook(wb_path)
    assert wb.sheetnames == ["Sheet1", "Detail"]


def test_add_sheet_inserts_at_position(tmp_path, add_sheet):
    wb_path = _make_wb(tmp_path)
    add_sheet.add_sheet(wb_path, "Cover", position=0)
    wb = openpyxl.load_workbook(wb_path)
    assert wb.sheetnames == ["Cover", "Sheet1"]


def test_add_sheet_duplicate_default_errors(tmp_path, add_sheet):
    wb_path = _make_wb(tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        add_sheet.add_sheet(wb_path, "Sheet1")


def test_add_sheet_duplicate_ignore(tmp_path, add_sheet):
    wb_path = _make_wb(tmp_path)
    final = add_sheet.add_sheet(wb_path, "Sheet1", if_exists="ignore")
    assert final == "Sheet1"
    wb = openpyxl.load_workbook(wb_path)
    # Still just one sheet
    assert wb.sheetnames == ["Sheet1"]


def test_add_sheet_duplicate_rename(tmp_path, add_sheet):
    wb_path = _make_wb(tmp_path)
    final = add_sheet.add_sheet(wb_path, "Sheet1", if_exists="rename")
    assert final == "Sheet1 (2)"
    wb = openpyxl.load_workbook(wb_path)
    assert "Sheet1 (2)" in wb.sheetnames


def test_add_sheet_missing_workbook_raises(tmp_path, add_sheet):
    with pytest.raises(FileNotFoundError):
        add_sheet.add_sheet(tmp_path / "nope.xlsx", "X")


# --- set_values --------------------------------------------------------------


def test_set_values_cells_map(tmp_path, set_values):
    wb_path = _make_wb(tmp_path)
    count = set_values.set_cells(
        wb_path,
        "Sheet1",
        {"A1": "Revenue", "B1": 1200, "C1": "=B1*1.1"},
    )
    assert count == 3
    wb = openpyxl.load_workbook(wb_path)
    ws = wb["Sheet1"]
    assert ws["A1"].value == "Revenue"
    assert ws["B1"].value == 1200
    # Formula stays as a formula string in openpyxl
    assert ws["C1"].value == "=B1*1.1"


def test_set_values_rows_2d(tmp_path, set_values):
    wb_path = _make_wb(tmp_path)
    count = set_values.set_rows(
        wb_path,
        "Sheet1",
        [["Name", "Qty"], ["Widget", 10], ["Gadget", 7]],
        start="A1",
    )
    assert count == 6
    wb = openpyxl.load_workbook(wb_path)
    ws = wb["Sheet1"]
    assert ws["A1"].value == "Name"
    assert ws["B1"].value == "Qty"
    assert ws["A2"].value == "Widget"
    assert ws["B2"].value == 10
    assert ws["B3"].value == 7


def test_set_values_rows_with_offset_start(tmp_path, set_values):
    wb_path = _make_wb(tmp_path)
    set_values.set_rows(
        wb_path,
        "Sheet1",
        [["a", "b"], ["c", "d"]],
        start="C5",
    )
    wb = openpyxl.load_workbook(wb_path)
    ws = wb["Sheet1"]
    assert ws["C5"].value == "a"
    assert ws["D5"].value == "b"
    assert ws["C6"].value == "c"
    assert ws["D6"].value == "d"


def test_set_values_missing_sheet_raises(tmp_path, set_values):
    wb_path = _make_wb(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        set_values.set_cells(wb_path, "Nope", {"A1": 1})


def test_set_values_invalid_cell_ref_raises(tmp_path, set_values):
    wb_path = _make_wb(tmp_path)
    with pytest.raises(Exception):  # openpyxl raises ValueError on bad ref
        set_values.set_cells(wb_path, "Sheet1", {"not-a-ref": 1})


# --- end-to-end CLI smoke ----------------------------------------------------


def test_cli_smoke(tmp_path):
    """Round-trip the actual CLI scripts via subprocess to catch arg-parsing bugs."""
    wb_path = tmp_path / "cli.xlsx"

    # 1. build
    r = subprocess.run(
        [sys.executable, str(SKILL_DIR / "build_xlsx.py"), "--out", str(wb_path), "--sheet-name", "Main"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    # 2. add a sheet
    r = subprocess.run(
        [sys.executable, str(SKILL_DIR / "add_sheet.py"), str(wb_path), "--name", "Detail"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    # 3. write some cells
    r = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "set_values.py"),
            str(wb_path),
            "--sheet",
            "Main",
            "--cells",
            json.dumps({"A1": "Total", "B1": 42}),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    wb = openpyxl.load_workbook(wb_path)
    assert wb.sheetnames == ["Main", "Detail"]
    ws = wb["Main"]
    assert ws["A1"].value == "Total"
    assert ws["B1"].value == 42
