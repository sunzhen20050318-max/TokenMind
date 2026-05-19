#!/usr/bin/env python3
"""Render a .pptx to per-slide PNGs (and optionally PDF) for visual QA.

Pipeline: LibreOffice headless converts the deck to PDF, then pdf2image
turns each page into a PNG. Mirrors the approach used by the documents
skill's ``render_docx.py``.

Required:
  - ``soffice`` binary on PATH (install LibreOffice)
  - ``pdf2image`` Python package
  - ``poppler`` available to pdf2image (brew install poppler / apt install poppler-utils)

Examples
--------

  # Default: per-slide PNGs at 144 DPI into <pptx-name>_render/
  python render_deck.py /tmp/deck.pptx

  # Custom output directory + higher DPI
  python render_deck.py /tmp/deck.pptx --output-dir /tmp/qa --dpi 200

  # Keep the intermediate PDF too (useful for archival / debugging)
  python render_deck.py /tmp/deck.pptx --emit-pdf

Output filenames
----------------

  {output_dir}/slide-01.png
  {output_dir}/slide-02.png
  ...
  {output_dir}/{pptx_stem}.pdf  (only with --emit-pdf)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from pdf2image import convert_from_path, pdfinfo_from_path
except ImportError:  # pragma: no cover - guarded by skill requires.python
    print(
        "Error: pdf2image is not installed. Run: pip install pdf2image",
        file=sys.stderr,
    )
    sys.exit(2)


def _ensure_soffice() -> str:
    """Find soffice across macOS / Linux / Windows install locations."""
    # We duplicate the lookup here (instead of importing the shared helper
    # in tokenmind/utils/office.py) so this script stays runnable standalone
    # — `python render_deck.py ...` from anywhere, no PYTHONPATH gymnastics.
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/opt/libreoffice/program/soffice",
        "/snap/bin/libreoffice.soffice",
    ):
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        "soffice (LibreOffice) not found. Install via "
        "'brew install libreoffice' (macOS), 'apt install libreoffice' (Debian/Ubuntu), "
        "or https://www.libreoffice.org/download/ (Windows)."
    )


def _convert_pptx_to_pdf(pptx: Path, work_dir: Path, *, verbose: bool = False) -> Path:
    """Run soffice headless to produce a PDF next to ``work_dir``."""
    soffice = _ensure_soffice()

    # Use isolated user profile to avoid soffice locking issues when run
    # repeatedly or under sandboxed temp dirs.
    with tempfile.TemporaryDirectory(prefix="soffice_profile_") as profile:
        env = {**os.environ}
        cmd = [
            soffice,
            f"-env:UserInstallation={Path(profile).as_uri()}",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--convert-to", "pdf",
            "--outdir", str(work_dir),
            str(pptx),
        ]
        if verbose:
            print(f"$ {' '.join(cmd)}", file=sys.stderr)
        proc = subprocess.run(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"soffice failed (exit {proc.returncode}):\n"
                f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
            )

    pdf_path = work_dir / (pptx.stem + ".pdf")
    if not pdf_path.is_file():
        raise RuntimeError(
            f"soffice did not produce {pdf_path}. stdout: {proc.stdout}"
        )
    return pdf_path


def render_deck(
    pptx: Path,
    output_dir: Path,
    *,
    dpi: int = 144,
    emit_pdf: bool = False,
    verbose: bool = False,
) -> dict:
    """Render the deck. Returns ``{pdf, png_paths, slide_count}``."""
    if not pptx.is_file():
        raise FileNotFoundError(pptx)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="render_deck_") as scratch:
        scratch_dir = Path(scratch)
        pdf_temp = _convert_pptx_to_pdf(pptx, scratch_dir, verbose=verbose)

        info = pdfinfo_from_path(str(pdf_temp))
        page_count = int(info.get("Pages", 0))
        if page_count == 0:
            raise RuntimeError("PDF reports zero pages — soffice conversion silently failed?")

        images = convert_from_path(str(pdf_temp), dpi=dpi)
        png_paths: list[Path] = []
        for i, image in enumerate(images, start=1):
            png_path = output_dir / f"slide-{i:02d}.png"
            image.save(png_path, "PNG")
            png_paths.append(png_path)

        pdf_final: Path | None = None
        if emit_pdf:
            pdf_final = output_dir / pdf_temp.name
            shutil.copy2(pdf_temp, pdf_final)

    return {
        "pdf": str(pdf_final) if pdf_final else None,
        "png_paths": [str(p) for p in png_paths],
        "slide_count": page_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pptx", type=Path, help="Path to the .pptx file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write PNGs (default: <pptx-name>_render/ next to the pptx)",
    )
    parser.add_argument("--dpi", type=int, default=144, help="PNG resolution (default: 144)")
    parser.add_argument("--emit-pdf", action="store_true", help="Also copy the intermediate PDF to the output dir")
    parser.add_argument("--verbose", action="store_true", help="Print the soffice command and stderr on failure")
    args = parser.parse_args(argv)

    if not args.pptx.is_file():
        print(f"Error: pptx not found: {args.pptx}", file=sys.stderr)
        return 1

    output_dir = args.output_dir or args.pptx.parent / f"{args.pptx.stem}_render"

    try:
        result = render_deck(
            args.pptx,
            output_dir,
            dpi=args.dpi,
            emit_pdf=args.emit_pdf,
            verbose=args.verbose,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Rendered {result['slide_count']} slide(s) → {output_dir}")
    for p in result["png_paths"]:
        print(f"  {p}")
    if result["pdf"]:
        print(f"PDF: {result['pdf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
