from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain import SearchHit


@dataclass(slots=True)
class ContextBundle:
    context_text: str
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_context(hits: list[SearchHit], max_characters: int = 12_000) -> ContextBundle:
    parts: list[str] = []
    sources: dict[str, dict[str, Any]] = {}
    total = 0
    for index, hit in enumerate(hits, start=1):
        source_id = f"S{index}"
        chunk = hit.chunk
        record = {
            "id": source_id,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "file_name": chunk.file_name,
            "source_path": chunk.source_path,
            "heading_path": chunk.heading_path,
            "location": dict(chunk.location),
            "excerpt": chunk.text[:900],
        }
        part = (
            f"[{source_id}]\n文件：{chunk.file_name}\n"
            f"章节：{chunk.heading_path or '未识别章节'}\n"
            f"位置：{chunk.location}\n证据：\n{chunk.text[:1_600]}"
        )
        if total + len(part) > max_characters:
            break
        parts.append(part)
        sources[source_id] = record
        total += len(part)
    return ContextBundle(context_text="\n\n---\n\n".join(parts), sources=sources)
