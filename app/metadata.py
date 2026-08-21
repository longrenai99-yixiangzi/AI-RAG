from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


METADATA_FIELDS = (
    "board",
    "knowledge_type",
    "discipline",
    "building_type",
    "project_stage",
    "topic",
    "document_level",
    "source_organization",
    "publish_date",
    "project_name",
)
MULTI_FIELDS = {"topic"}
FRONTMATTER_ALIASES = {
    "板块": "board",
    "知识类型": "knowledge_type",
    "专业": "discipline",
    "业态": "building_type",
    "项目阶段": "project_stage",
    "主题": "topic",
    "文档层级": "document_level",
    "发布单位": "source_organization",
    "发布日期": "publish_date",
    "项目名称": "project_name",
}


@lru_cache(maxsize=8)
def load_metadata_rules(path: str | Path) -> dict[str, Any]:
    rules_path = Path(path)
    if not rules_path.exists():
        return {"fields": {}, "intent_keywords": {}, "projects": []}
    payload = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def empty_metadata() -> dict[str, Any]:
    return {field: [] if field in MULTI_FIELDS else None for field in METADATA_FIELDS}


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


def _as_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _keyword_matches(haystack: str, keywords: list[str]) -> bool:
    folded = haystack.casefold()
    return any(keyword.casefold() in folded for keyword in keywords if keyword)


def _field_matches(field_rules: dict[str, Any], haystack: str) -> list[str]:
    values: list[tuple[int, str]] = []
    for value, config in (field_rules.get("values") or {}).items():
        if isinstance(config, dict):
            keywords = [str(item) for item in config.get("keywords", [])]
        else:
            keywords = [str(item) for item in (config or [])]
        matched_lengths = [len(keyword) for keyword in keywords if keyword and keyword.casefold() in haystack]
        if matched_lengths:
            values.append((max(matched_lengths), str(value)))
    return [value for _, value in sorted(values, key=lambda item: (-item[0], item[1]))]


def _project_match(projects: list[Any], haystack: str) -> str | None:
    matches: list[tuple[int, str]] = []
    folded = haystack.casefold()
    for item in projects:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        keywords = [str(x) for x in item.get("keywords", [])]
        for keyword in keywords:
            if keyword and keyword.casefold() in folded:
                matches.append((len(keyword), value))
    return max(matches, default=(0, ""))[1] or None


def infer_metadata(
    path: Path,
    text: str,
    rules_path: str | Path,
) -> dict[str, Any]:
    """Infer retrieval metadata without making it a factual assertion."""
    rules = load_metadata_rules(rules_path)
    result = empty_metadata()
    front = _frontmatter(text)
    title = path.stem
    haystack = "\n".join((str(path), title, text[:120_000])).casefold()

    for field in METADATA_FIELDS:
        front_value = None
        for key, value in front.items():
            if key == field or FRONTMATTER_ALIASES.get(str(key)) == field:
                front_value = value
                break
        if front_value is not None:
            values = _as_values(front_value)
            result[field] = values if field in MULTI_FIELDS else (values[0] if values else None)
            continue
        if field in ("publish_date", "project_name"):
            continue
        matches = _field_matches((rules.get("fields") or {}).get(field, {}), haystack)
        if field in MULTI_FIELDS:
            result[field] = matches
        elif matches:
            result[field] = matches[0]

    if not result["document_level"]:
        result["document_level"] = _path_level(path)
    if not result["publish_date"]:
        result["publish_date"] = _date_match(haystack)
    if not result["project_name"]:
        result["project_name"] = _project_match(rules.get("projects", []), haystack)

    return result


def _path_level(path: Path) -> str | None:
    folded = "/".join(path.parts).casefold()
    for value, keywords in {
        "原始资料": ("/raw/", "原始资料"),
        "正式知识": ("/wiki/", "正式知识", "规则库"),
        "项目经验": ("项目经验", "项目案例"),
        "模板": ("/templates/", "模板库"),
    }.items():
        if any(keyword.casefold() in folded for keyword in keywords):
            return value
    return None


def _date_match(text: str) -> str | None:
    match = re.search(r"(?<!\d)(20\d{2})[年./-](\d{1,2})(?:[月./-](\d{1,2}))?", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}" + (f"-{int(day):02d}" if day else "")


def metadata_for_block(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key in METADATA_FIELDS}
