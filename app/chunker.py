from __future__ import annotations

import math
import re
import uuid

from .domain import Chunk, SourceBlock


def estimate_tokens(text: str) -> int:
    """A conservative local estimate; no tokenizer download is needed for chunking."""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_words = re.findall(r"[A-Za-z0-9_./:-]+", text)
    latin = sum(max(1, math.ceil(len(word) / 4)) for word in latin_words)
    punctuation = len(re.findall(r"[，。；：、,.!?;:]", text)) // 3
    return max(1, cjk + latin + punctuation)


def _split_oversized_unit(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text]
    parts = [part.strip() for part in re.split(r"(?<=[。！？；.!?;])", text) if part.strip()]
    if len(parts) <= 1:
        parts = [text[i : i + 1_600] for i in range(0, len(text), 1_600)]

    result: list[str] = []
    current: list[str] = []
    for part in parts:
        if current and estimate_tokens("\n".join(current + [part])) > max_tokens:
            result.append("\n".join(current))
            current = []
        if estimate_tokens(part) > max_tokens:
            result.extend(_split_oversized_unit(part[: len(part) // 2], max_tokens))
            result.extend(_split_oversized_unit(part[len(part) // 2 :], max_tokens))
        else:
            current.append(part)
    if current:
        result.append("\n".join(current))
    return result


def _tail_within_budget(parts: list[str], budget: int) -> list[str]:
    tail: list[str] = []
    for part in reversed(parts):
        if estimate_tokens("\n".join([part, *tail])) > budget:
            break
        tail.insert(0, part)
    return tail


def split_text(
    text: str, target_tokens: int = 450, max_tokens: int = 800, overlap_tokens: int = 80
) -> list[str]:
    """Split on paragraph/sentence boundaries while retaining a small local overlap."""
    text = text.strip()
    if not text:
        return []
    units = [
        piece
        for paragraph in re.split(r"\n\s*\n", text)
        for piece in _split_oversized_unit(paragraph.strip(), max_tokens)
        if piece.strip()
    ]
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and estimate_tokens(candidate) > target_tokens:
            chunks.append("\n\n".join(current))
            current = _tail_within_budget(current, overlap_tokens)
        if current and estimate_tokens("\n\n".join([*current, unit])) > max_tokens:
            chunks.append("\n\n".join(current))
            current = []
        current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_blocks(blocks: list[SourceBlock]) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0
    for block_number, block in enumerate(blocks):
        for part_number, text in enumerate(split_text(block.text)):
            chunk_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{block.document_id}|{block_number}|{part_number}|{block.heading_path}|{text[:120]}",
                )
            )
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=block.document_id,
                    ordinal=ordinal,
                    source_path=block.source_path,
                    file_name=block.file_name,
                    text=text,
                    heading_path=block.heading_path,
                    location=block.location or {},
                )
            )
            ordinal += 1
    return chunks
