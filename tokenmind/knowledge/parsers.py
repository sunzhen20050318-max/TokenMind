"""Rich document parsers for the knowledge base.

Per-format extractors that preserve more structure than naive
``zipfile + itertext`` does — tables stay as ``cell | cell`` rows, PPTX
slides stay numbered, DOCX paragraphs keep their heading level. When a
``VLMConfig`` is provided, complex PDF pages and embedded Office images
get captioned by a vision-language model; without it the parsers
degrade cleanly to text-only extraction.

The legacy ``.doc`` / ``.ppt`` binary formats are converted to their
modern ZIP-based counterparts via the locally-installed LibreOffice
(``soffice``) — no Docker daemon required. Conversion fails fast with a
clear error when LibreOffice isn't on the system.
"""

from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from loguru import logger

from tokenmind.utils.office import find_soffice


@dataclass
class VLMConfig:
    """Vision-language model client configuration for parsing-time image captioning."""

    model: str
    api_key: str
    api_base: str | None = None
    timeout: int = 30
    max_dim: int = 1280


@dataclass
class ParsedPage:
    page_num: int
    content: str
    tokens_used: int = 0
    method: str = "text"


@dataclass
class ParsedDocument:
    file_name: str
    file_type: str
    pages: list[ParsedPage] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(p.tokens_used for p in self.pages)

    def as_text(self) -> str:
        return "\n\n".join(p.content for p in self.pages if p.content.strip())


class LegacyOfficeConversionError(RuntimeError):
    """Raised when ``.doc`` / ``.ppt`` cannot be converted to the modern format."""


# Office images smaller than this byte threshold are ignored (likely icons /
# bullets / decorative artwork that VLM has nothing meaningful to say about).
_MIN_OFFICE_IMAGE_BYTES = 5 * 1024  # 5KB
# Approximate per-segment character cap for DOCX paging.
_DOCX_SEGMENT_CHAR_LIMIT = 1000


# ---------------------------------------------------------------------------
# VLM image captioning
# ---------------------------------------------------------------------------

def _caption_image(
    image_bytes: bytes,
    vlm: VLMConfig,
    *,
    context_hint: str = "",
    strict_filtering: bool = True,
) -> tuple[str | None, int]:
    """Send a single image to the configured VLM, return ``(caption, tokens)``.

    ``strict_filtering=True`` (PPT mode) tells the model to drop decorative
    images outright by returning a sentinel that we map to ``None``. The
    non-strict mode (DOCX) keeps weak captions to maximise recall on inline
    diagrams.
    """
    try:
        from PIL import Image
        from openai import OpenAI
    except ImportError as exc:
        logger.warning("VLM dependencies missing: {}", exc)
        return None, 0

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((vlm.max_dim, vlm.max_dim))
        buf = io.BytesIO()
        save_format = "PNG" if img.mode in {"RGBA", "P"} else "JPEG"
        img.convert("RGB" if save_format == "JPEG" else img.mode).save(buf, format=save_format)
        data_url = (
            f"data:image/{save_format.lower()};base64,"
            f"{base64.b64encode(buf.getvalue()).decode('ascii')}"
        )
    except Exception:
        logger.exception("Failed to preprocess image for VLM")
        return None, 0

    if strict_filtering:
        instructions = (
            "你是文档解析助手。请用中文描述图片中的有用信息（图表数据、文字、"
            "示意图含义）。如果图片是纯装饰、logo、模糊背景或无可识别内容，"
            "只回复 SKIP。"
        )
    else:
        instructions = (
            "你是文档解析助手。请用中文简洁描述图片中的内容、表格或图表数据，"
            "重点提取文字与数值信息。"
        )

    user_prompt = instructions
    if context_hint:
        user_prompt = f"{instructions}\n\n上下文：{context_hint}"

    try:
        client = OpenAI(
            api_key=vlm.api_key,
            base_url=vlm.api_base or None,
            timeout=vlm.timeout,
        )
        resp = client.chat.completions.create(
            model=vlm.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            max_tokens=800,
        )
        text = (resp.choices[0].message.content or "").strip()
        tokens = getattr(resp.usage, "total_tokens", 0) if resp.usage else 0
        if strict_filtering and text.upper() == "SKIP":
            return None, tokens
        if not text:
            return None, tokens
        return text, tokens
    except Exception as exc:
        logger.warning("VLM call failed: {}", exc)
        return None, 0


# ---------------------------------------------------------------------------
# Legacy format conversion via local LibreOffice
# ---------------------------------------------------------------------------

def _convert_legacy_to_modern(source: Path, target_ext: str) -> Path:
    """Convert ``.doc`` → ``.docx`` (or ``.ppt`` → ``.pptx``) using local
    LibreOffice. Returns the path to the converted file inside a tempdir.

    Raises ``LegacyOfficeConversionError`` if LibreOffice isn't installed or
    the conversion fails.
    """
    soffice = find_soffice()
    if not soffice:
        raise LegacyOfficeConversionError(
            "LibreOffice (soffice) not found. Install LibreOffice to enable "
            ".doc / .ppt parsing, or upload the document in the modern "
            "format (.docx / .pptx)."
        )

    target_format = target_ext.lstrip(".")  # 'docx' or 'pptx'
    out_dir = Path(tempfile.mkdtemp(prefix="tm-legacy-conv-"))
    try:
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                target_format,
                "--outdir",
                str(out_dir),
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise LegacyOfficeConversionError(
            f"LibreOffice timed out converting {source.name}"
        ) from exc

    if result.returncode != 0:
        raise LegacyOfficeConversionError(
            f"LibreOffice failed to convert {source.name}: "
            f"{(result.stderr or result.stdout or '').strip()[:400]}"
        )

    converted = out_dir / f"{source.stem}.{target_format}"
    if not converted.exists():
        raise LegacyOfficeConversionError(
            f"LibreOffice produced no output for {source.name}"
        )
    return converted


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _pdf_page_is_complex(text: str, image_count: int) -> bool:
    """Heuristic: a page benefits from VLM captioning when it has images and
    little extractable text. Mirrors smart-document-parser's
    ``_check_pdf_complexity`` minus the fitz-specific bbox math (we don't
    have per-image bounding boxes from pypdf)."""
    text = (text or "").strip()
    if not text and image_count > 0:
        return True
    if image_count > 0 and len(text) < 800:
        return True
    return False


def _render_pdf_page_to_image(path: Path, page_num: int, dpi: int = 100) -> bytes | None:
    """Render a single PDF page (1-indexed) to PNG bytes via pdf2image.
    Returns ``None`` when pdf2image / poppler is unavailable."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning("pdf2image not available — skipping VLM render")
        return None
    try:
        images = convert_from_path(
            str(path),
            dpi=dpi,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            return None
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("pdf2image failed on page {} of {}: {}", page_num, path.name, exc)
        return None


def parse_pdf(path: Path, vlm: VLMConfig | None = None) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    doc = ParsedDocument(file_name=path.name, file_type="pdf")

    for index, page in enumerate(reader.pages):
        page_num = index + 1
        raw_text = (page.extract_text() or "").strip()
        image_count = len(getattr(page, "images", []) or [])

        if vlm and _pdf_page_is_complex(raw_text, image_count):
            png_bytes = _render_pdf_page_to_image(path, page_num)
            if png_bytes:
                caption, tokens = _caption_image(
                    png_bytes,
                    vlm,
                    context_hint=raw_text[:200],
                    strict_filtering=False,
                )
                if caption:
                    content = f"--- Page {page_num} ---\n{caption}"
                    if raw_text:
                        content = f"{content}\n\n[原始文本]\n{raw_text}"
                    doc.pages.append(
                        ParsedPage(
                            page_num=page_num,
                            content=content,
                            tokens_used=tokens,
                            method="vlm",
                        )
                    )
                    continue

        # Text-only fallback (also the default when no VLM is configured).
        if raw_text:
            doc.pages.append(
                ParsedPage(
                    page_num=page_num,
                    content=f"--- Page {page_num} ---\n{raw_text}",
                    method="text",
                )
            )

    return doc


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _extract_table_text(table: Any) -> str:
    """Render a DOCX table as ``cell | cell`` rows. Supports nested tables."""
    rows_text: list[str] = []
    for row in table.rows:
        cells_text: list[str] = []
        for cell in row.cells:
            paragraph_text = "\n".join(
                p.text.strip() for p in cell.paragraphs if p.text.strip()
            )
            for nested in getattr(cell, "tables", []) or []:
                nested_str = _extract_table_text(nested)
                if nested_str:
                    paragraph_text = (
                        f"{paragraph_text}\n{nested_str}" if paragraph_text else nested_str
                    )
            cells_text.append(paragraph_text)
        if any(cells_text):
            rows_text.append(" | ".join(cells_text))
    return "\n".join(rows_text)


def parse_docx(path: Path, vlm: VLMConfig | None = None) -> ParsedDocument:
    from docx import Document
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph

    doc_obj = Document(str(path))
    result = ParsedDocument(file_name=path.name, file_type="docx")

    # Pre-index image relationship blobs so we can resolve inline embed IDs
    # without re-scanning the package each time.
    rid_to_blob: dict[str, bytes] = {}
    if vlm:
        for rel in doc_obj.part.rels.values():
            if "image" in rel.target_ref:
                try:
                    rid_to_blob[rel.rId] = rel.target_part.blob
                except Exception:
                    continue

    structure: list[dict[str, Any]] = []
    pending_image_caches: dict[str, tuple[str, bytes]] = {}

    def _collect_inline_images(xml_str: str, ctx_hint: str) -> None:
        if not vlm or 'embed="' not in xml_str:
            return
        for part in xml_str.split('embed="')[1:]:
            rid = part.split('"', 1)[0]
            blob = rid_to_blob.get(rid)
            if not blob or len(blob) < _MIN_OFFICE_IMAGE_BYTES:
                continue
            task_id = f"img_{len(pending_image_caches)}"
            pending_image_caches[task_id] = (ctx_hint, blob)
            structure.append({"type": "img", "id": task_id})

    for element in doc_obj.element.body:
        tag = element.tag.split("}")[-1]

        if tag == "p":
            para = Paragraph(element, doc_obj)
            text = para.text.strip()
            if text:
                style_name = (para.style.name or "").lower()
                if "heading" in style_name:
                    level_str = para.style.name.replace("Heading", "").strip()
                    level = int(level_str) if level_str.isdigit() else 2
                    structure.append({"type": "text", "val": f"{'#' * level} {text}"})
                else:
                    structure.append({"type": "text", "val": text})
            _collect_inline_images(element.xml, text[:50] if text else "Word document image")

        elif tag == "tbl":
            table = DocxTable(element, doc_obj)
            table_text = _extract_table_text(table)
            if table_text:
                structure.append({"type": "text", "val": table_text})
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        _collect_inline_images(
                            para._element.xml,
                            (para.text or "Word table image")[:50],
                        )

    captions: dict[str, tuple[str | None, int]] = {}
    if pending_image_caches and vlm:
        for task_id, (ctx_hint, blob) in pending_image_caches.items():
            captions[task_id] = _caption_image(
                blob, vlm, context_hint=ctx_hint, strict_filtering=False
            )

    chunk: list[str] = []
    chunk_chars = 0
    chunk_tokens = 0
    segment_num = 1

    def _flush() -> None:
        nonlocal chunk, chunk_chars, chunk_tokens, segment_num
        if not chunk:
            return
        body = "\n\n".join(chunk)
        result.pages.append(
            ParsedPage(
                page_num=segment_num,
                content=f"--- Segment {segment_num} ---\n{body}",
                tokens_used=chunk_tokens,
                method="docx",
            )
        )
        chunk = []
        chunk_chars = 0
        chunk_tokens = 0
        segment_num += 1

    for item in structure:
        if item["type"] == "text":
            piece = item["val"]
        else:
            caption, tokens = captions.get(item["id"], (None, 0))
            if not caption:
                continue
            piece = f"\n> **[图片内容]**:\n{caption}\n"
            chunk_tokens += tokens
        chunk.append(piece)
        chunk_chars += len(piece)
        if chunk_chars > _DOCX_SEGMENT_CHAR_LIMIT:
            _flush()

    _flush()
    return result


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------

def parse_pptx(path: Path, vlm: VLMConfig | None = None) -> ParsedDocument:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    result = ParsedDocument(file_name=path.name, file_type="pptx")

    for i, slide in enumerate(prs.slides):
        page_num = i + 1
        parts: list[str] = []
        pending_images: list[tuple[str, bytes]] = []

        title_shape = slide.shapes.title if slide.shapes.title else None
        if title_shape and title_shape.text:
            parts.append(f"## {title_shape.text.strip()}")

        sorted_shapes = sorted(slide.shapes, key=lambda s: (s.top or 0, s.left or 0))
        for shape in sorted_shapes:
            if title_shape is not None and shape == title_shape:
                continue
            if getattr(shape, "has_text_frame", False):
                text = shape.text_frame.text.strip()
                if text:
                    parts.append(text)
            if vlm and shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    blob = shape.image.blob
                except Exception:
                    blob = None
                if blob and len(blob) >= _MIN_OFFICE_IMAGE_BYTES:
                    pending_images.append(
                        (
                            f"PPT Slide {page_num}: " + " ".join(parts[-3:]),
                            blob,
                        )
                    )

        page_tokens = 0
        for ctx_hint, blob in pending_images:
            caption, tokens = _caption_image(
                blob, vlm, context_hint=ctx_hint, strict_filtering=True
            ) if vlm else (None, 0)
            page_tokens += tokens
            if caption:
                parts.append(f"\n{caption}\n")

        body = "\n".join(parts)
        result.pages.append(
            ParsedPage(
                page_num=page_num,
                content=f"--- Slide {page_num} ---\n{body}",
                tokens_used=page_tokens,
                method="pptx",
            )
        )

    return result


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def parse_xlsx(path: Path) -> ParsedDocument:
    from openpyxl import load_workbook

    wb = load_workbook(filename=str(path), data_only=True, read_only=True)
    result = ParsedDocument(file_name=path.name, file_type="xlsx")
    try:
        for sheet_index, sheet_name in enumerate(wb.sheetnames):
            ws = wb[sheet_name]
            lines: list[str] = []
            for row in ws.iter_rows(values_only=True):
                if not row:
                    continue
                cells = [str(c) if c is not None else "" for c in row]
                if any(cell.strip() for cell in cells):
                    lines.append(" | ".join(cells))
            if not lines:
                continue
            body = "\n".join(lines)
            result.pages.append(
                ParsedPage(
                    page_num=sheet_index + 1,
                    content=f"--- Sheet: {sheet_name} ---\n{body}",
                    method="xlsx",
                )
            )
    finally:
        wb.close()
    return result


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

# Extensions we have first-class structured parsers for. Everything else
# (txt, md, json, …) falls back to plain UTF-8 reading.
_RICH_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}


def can_parse(suffix: str) -> bool:
    return suffix.lower() in _RICH_SUFFIXES


def extract_document_text(path: Path, vlm: VLMConfig | None = None) -> str:
    """Top-level dispatch used by ``KnowledgeService``. Returns concatenated
    text suitable for chunking + embedding."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, vlm).as_text()
    if suffix == ".docx":
        return parse_docx(path, vlm).as_text()
    if suffix == ".doc":
        converted = _convert_legacy_to_modern(path, ".docx")
        try:
            return parse_docx(converted, vlm).as_text()
        finally:
            _cleanup_legacy_conversion(converted)
    if suffix == ".pptx":
        return parse_pptx(path, vlm).as_text()
    if suffix == ".ppt":
        converted = _convert_legacy_to_modern(path, ".pptx")
        try:
            return parse_pptx(converted, vlm).as_text()
        finally:
            _cleanup_legacy_conversion(converted)
    if suffix in {".xlsx", ".xls"}:
        # ``.xls`` is the old OLE binary format that openpyxl can't read; do a
        # soffice conversion first.
        if suffix == ".xls":
            converted = _convert_legacy_to_modern(path, ".xlsx")
            try:
                return parse_xlsx(converted).as_text()
            finally:
                _cleanup_legacy_conversion(converted)
        return parse_xlsx(path).as_text()
    return path.read_text(encoding="utf-8", errors="ignore")


def _cleanup_legacy_conversion(converted: Path) -> None:
    try:
        converted.unlink(missing_ok=True)
        converted.parent.rmdir()
    except OSError:
        pass
