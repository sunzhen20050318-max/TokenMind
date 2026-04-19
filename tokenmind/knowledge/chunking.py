from __future__ import annotations

from collections.abc import Iterable
from typing import Callable


SENTENCE_ENDINGS = "。！？!?；;."
CLOSING_PUNCTUATION = "\"'”’）】」』》"


def _split_sentences(text: str) -> list[str]:
    clean = text.strip()
    if not clean:
        return []

    sentences: list[str] = []
    start = 0

    for index, char in enumerate(clean):
        if char == "\n":
            sentence = clean[start:index].strip()
            if sentence:
                sentences.append(sentence)
            start = index + 1
            continue

        if char not in SENTENCE_ENDINGS:
            continue

        end = index + 1
        while end < len(clean) and clean[end] in CLOSING_PUNCTUATION:
            end += 1

        sentence = clean[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end

    tail = clean[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _split_fragment(text: str, size: int) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= size:
        return [clean]

    fragments: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            preferred = max(
                clean.rfind(separator, start, end)
                for separator in ("，", "、", ",", " ", "：", ":", "（", "(")
            )
            if preferred > start:
                end = preferred + 1
        fragment = clean[start:end].strip()
        if fragment:
            fragments.append(fragment)
        start = end
    return fragments


def _split_oversized_paragraph(paragraph: str, size: int) -> list[str]:
    sentences = _split_sentences(paragraph)
    if not sentences:
        return _split_fragment(paragraph, size)

    units: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        chunk = current.strip()
        if chunk:
            units.append(chunk)
        current = ""

    for sentence in sentences:
        if len(sentence) > size:
            flush()
            units.extend(_split_fragment(sentence, size))
            continue

        candidate = f"{current}{sentence}" if current else sentence
        if current and len(candidate) > size:
            flush()
            current = sentence
        else:
            current = candidate

    flush()
    return units


def _prepare_units(text: str, size: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= size:
            units.append(paragraph)
            continue
        units.extend(_split_oversized_paragraph(paragraph, size))
    return units


def _tail_units(buffer: Iterable[str], overlap: int) -> list[str]:
    if overlap <= 0:
        return []

    tail: list[str] = []
    total = 0
    for unit in reversed(list(buffer)):
        next_len = len(unit) if not tail else len(unit) + 2
        if tail and total + next_len > overlap:
            break
        tail.insert(0, unit)
        total += next_len
        if total >= overlap:
            break
    return tail


def _build_chunks_from_units(units: list[str], size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        chunk = "\n\n".join(current).strip()
        if chunk:
            chunks.append(chunk)
        overlap_units = _tail_units(current, overlap)
        current = overlap_units
        current_len = sum(len(unit) for unit in current) + max(0, len(current) - 1) * 2

    for unit in units:
        unit_len = len(unit)
        next_len = unit_len if current_len == 0 else current_len + 2 + unit_len
        if current and next_len > size:
            flush()
            next_len = unit_len if current_len == 0 else current_len + 2 + unit_len
            if current and next_len > size:
                current = [unit]
                current_len = unit_len
                flush()
                continue

        current.append(unit)
        current_len = next_len

    if current:
        chunk = "\n\n".join(current).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _average_embedding(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    length = len(vectors[0])
    if length == 0:
        return []
    totals = [0.0] * length
    count = 0
    for vector in vectors:
        if len(vector) != length:
            continue
        count += 1
        for index, value in enumerate(vector):
            totals[index] += value
    if count == 0:
        return []
    return [value / count for value in totals]


def _prepare_sentence_units(text: str, size: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        sentences = _split_sentences(paragraph)
        if not sentences:
            units.extend(_split_fragment(paragraph, size))
            continue
        for sentence in sentences:
            if len(sentence) <= size:
                units.append(sentence)
            else:
                units.extend(_split_fragment(sentence, size))
    return units


def semantic_chunks(
    text: str,
    embed_texts: Callable[[list[str]], list[list[float]]],
    *,
    size: int = 900,
    overlap: int = 120,
    similarity_threshold: float = 0.72,
    min_chunk_chars: int = 80,
) -> list[str]:
    clean = text.strip()
    if not clean:
        return []

    units = _prepare_sentence_units(clean, size)
    if len(units) <= 1:
        return _build_chunks_from_units(units, size, overlap)

    embeddings = embed_texts(units)
    if len(embeddings) != len(units) or any(not vector for vector in embeddings):
        return _build_chunks_from_units(units, size, overlap)

    semantic_units: list[str] = []
    current_units = [units[0]]
    current_vectors = [embeddings[0]]

    def flush() -> None:
        nonlocal current_units, current_vectors
        chunk = "".join(current_units).strip()
        if chunk:
            semantic_units.append(chunk)
        current_units = []
        current_vectors = []

    for unit, vector in zip(units[1:], embeddings[1:], strict=False):
        current_text = "".join(current_units).strip()
        current_vector = _average_embedding(current_vectors)
        similarity = _cosine_similarity(current_vector, vector)
        candidate = f"{current_text}{unit}" if current_text else unit
        should_split = len(candidate) > size or (
            current_text
            and len(current_text) >= min_chunk_chars
            and similarity < similarity_threshold
        ) or (
            current_text
            and len(current_units) >= 2
            and similarity < similarity_threshold
        )
        if should_split:
            flush()
        current_units.append(unit)
        current_vectors.append(vector)

    flush()
    if overlap <= 0 or len(semantic_units) <= 1:
        return semantic_units

    overlapped_chunks: list[str] = []
    for index, chunk in enumerate(semantic_units):
        if index == 0:
            overlapped_chunks.append(chunk)
            continue
        tail = semantic_units[index - 1][-overlap:].strip()
        candidate = f"{tail}\n\n{chunk}".strip() if tail else chunk
        overlapped_chunks.append(candidate if len(candidate) <= size else chunk)
    return overlapped_chunks


def simple_chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    clean = text.strip()
    if not clean:
        return []

    units = _prepare_units(clean, size)
    return _build_chunks_from_units(units, size, overlap)
