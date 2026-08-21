from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import yaml

from .domain import Chunk, ParsedDocument


ENTITY_NAMESPACE = uuid.UUID("2f73f455-6e16-4e43-9d7c-9c4f20bb9d2d")
FACT_FIELDS = {
    "项目名称": "PROJECT_NAME",
    "项目类型": "PROJECT_TYPE",
    "所在地": "LOCATION",
    "建设单位": "OWNER",
    "实施单位": "IMPLEMENTING_ORGANIZATION",
    "设计单位": "DESIGN_ORGANIZATION",
    "EPC牵头单位": "EPC_LEAD_ORGANIZATION",
    "项目经理": "PROJECT_MANAGER",
    "设计经理": "DESIGN_MANAGER",
    "当前阶段": "PROJECT_STAGE",
}


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    value = yaml.safe_load("\n".join(lines[1:end])) or {}
    return value if isinstance(value, dict) else {}


def _entity_path(path: str) -> bool:
    folded = path.replace("\\", "/").casefold()
    return "/wiki/entities/" in folded or folded.endswith("/wiki/entities")


def _heading(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else fallback


def _aliases(frontmatter: dict[str, Any]) -> list[str]:
    value = frontmatter.get("aliases", frontmatter.get("别名", []))
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def extract_entity_facts(
    document: ParsedDocument,
    chunks: list[Chunk],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not _entity_path(document.source_path):
        return [], []
    text = "\n".join(block.text for block in document.blocks)
    try:
        raw_text = Path(document.source_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw_text = text
    frontmatter = _frontmatter(raw_text)
    canonical = _heading(text, Path(document.file_name).stem)
    entity_id = str(uuid.uuid5(ENTITY_NAMESPACE, canonical.casefold()))
    description = next(
        (line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "-", "*", "---"))),
        "",
    )
    entities = [{
        "entity_id": entity_id,
        "entity_type": "PROJECT" if "项目" in canonical else "ENTITY",
        "canonical_name": canonical,
        "aliases": _aliases(frontmatter),
        "description": description,
        "source_document_id": document.document_id,
    }]
    facts: list[dict[str, Any]] = []
    for line in text.splitlines():
        for label, predicate in FACT_FIELDS.items():
            match = re.search(
                rf"(?:^|[-*]\s*)(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*[:：]\s*(.+?)\s*$",
                line,
            )
            if not match:
                continue
            object_text = match.group(1).strip().strip("`*_ ")
            if not object_text or object_text in {"待核实", "未知", "无"}:
                continue
            evidence = next((chunk for chunk in chunks if object_text in chunk.text or label in chunk.text), None)
            if evidence is None:
                continue
            facts.append({
                "fact_id": str(uuid.uuid4()),
                "subject_entity_id": entity_id,
                "predicate": predicate,
                "object_text": object_text,
                "evidence_chunk_id": evidence.chunk_id,
                "confidence": 0.5,
                "review_status": "AUTO",
            })
    return entities, facts
