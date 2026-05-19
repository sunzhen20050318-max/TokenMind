"""Tests for tokenmind.utils.office cross-platform soffice resolver."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tokenmind.utils import office as office_helper
from tokenmind.utils.office import (
    augmented_path_append,
    find_soffice,
    soffice_install_dir,
)


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """``find_soffice`` is lru_cached; we need a clean slate per test."""
    find_soffice.cache_clear()
    yield
    find_soffice.cache_clear()


# --- find_soffice -----------------------------------------------------------


def test_find_soffice_returns_path_when_on_PATH(monkeypatch):
    monkeypatch.setattr(office_helper.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    assert find_soffice() == "/usr/bin/soffice"


def test_find_soffice_checks_soffice_exe_on_windows(monkeypatch):
    """shutil.which on Windows resolves ``soffice.exe`` only."""
    def which(name):
        return r"C:\Program Files\LibreOffice\program\soffice.exe" if name == "soffice.exe" else None
    monkeypatch.setattr(office_helper.shutil, "which", which)
    found = find_soffice()
    assert found is not None
    assert found.endswith("soffice.exe")


def test_find_soffice_falls_back_to_macos_dmg(monkeypatch, tmp_path):
    """When ``shutil.which`` finds nothing, fall back to known install paths."""
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)

    fake_mac = tmp_path / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    fake_mac.parent.mkdir(parents=True)
    fake_mac.write_text("#!/bin/sh\necho stub")

    monkeypatch.setattr(
        office_helper,
        "_KNOWN_LOCATIONS",
        (str(fake_mac),),
    )
    assert find_soffice() == str(fake_mac)


def test_find_soffice_falls_back_to_windows_program_files(monkeypatch, tmp_path):
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)

    fake_win = tmp_path / "Program Files" / "LibreOffice" / "program" / "soffice.exe"
    fake_win.parent.mkdir(parents=True)
    fake_win.write_bytes(b"")  # exists is what matters

    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", (str(fake_win),))
    assert find_soffice() == str(fake_win)


def test_find_soffice_returns_none_when_nothing_works(monkeypatch):
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)
    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", ())
    assert find_soffice() is None


# --- soffice_install_dir ----------------------------------------------------


def test_soffice_install_dir_returns_parent(monkeypatch, tmp_path):
    fake_path = tmp_path / "soffice"
    fake_path.write_text("stub")
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: str(fake_path))
    assert soffice_install_dir() == str(tmp_path)


def test_soffice_install_dir_none_when_missing(monkeypatch):
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)
    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", ())
    assert soffice_install_dir() is None


# --- augmented_path_append --------------------------------------------------


def test_augmented_path_append_noop_when_on_PATH(monkeypatch):
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: "/usr/bin/soffice")
    assert augmented_path_append("") == ""
    assert augmented_path_append("/existing") == "/existing"


def test_augmented_path_append_injects_dir_when_only_fallback(monkeypatch, tmp_path):
    fake = tmp_path / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    fake.parent.mkdir(parents=True)
    fake.write_text("stub")
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)
    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", (str(fake),))
    result = augmented_path_append("")
    assert result == str(fake.parent)


def test_augmented_path_append_preserves_existing(monkeypatch, tmp_path):
    fake = tmp_path / "fake-mac" / "soffice"
    fake.parent.mkdir(parents=True)
    fake.write_text("stub")
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)
    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", (str(fake),))
    result = augmented_path_append("/custom/bin")
    parts = result.split(os.pathsep)
    assert "/custom/bin" in parts
    assert str(fake.parent) in parts


def test_augmented_path_append_no_duplicates(monkeypatch, tmp_path):
    """Don't add the soffice dir twice if it's already in the existing PATH."""
    fake = tmp_path / "fake-mac" / "soffice"
    fake.parent.mkdir(parents=True)
    fake.write_text("stub")
    monkeypatch.setattr(office_helper.shutil, "which", lambda _: None)
    monkeypatch.setattr(office_helper, "_KNOWN_LOCATIONS", (str(fake),))
    # Pre-populate "existing" with the same dir
    existing = str(fake.parent)
    result = augmented_path_append(existing)
    # Should equal existing (no duplicate appended)
    assert result.count(existing) == 1
