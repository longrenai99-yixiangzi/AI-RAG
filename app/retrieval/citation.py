from __future__ import annotations

from typing import Any

from app.retrieval.context_builder import ContextBundle


def build_citations(bundle: ContextBundle) -> list[dict[str, Any]]:
    """Return only citations for evidence actually included in the context."""

    return list(bundle.sources.values())


def validate_citations(
    citations: list[dict[str, Any]], bundle: ContextBundle
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    allowed = set(bundle.sources)
    seen: set[str] = set()
    for citation in citations:
        source_id = citation.get("id")
        if source_id not in allowed:
            errors.append(f"来源不在 Context 中：{source_id}")
        if source_id in seen:
            errors.append(f"来源重复：{source_id}")
        seen.add(source_id)
        if not citation.get("file_name") or not citation.get("source_path"):
            errors.append(f"来源缺少文件信息：{source_id}")
        if not citation.get("location"):
            errors.append(f"来源缺少 location：{source_id}")
    return not errors, errors
