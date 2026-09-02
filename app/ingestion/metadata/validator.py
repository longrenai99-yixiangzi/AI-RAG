from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.ingestion.metadata.schema import (
    BOARD_VALUES,
    AUTHORITY_LEVEL_VALUES,
    CLASSIFICATION_FIELDS,
    DISCIPLINE_VALUES,
    DOCUMENT_ROLE_VALUES,
    KNOWLEDGE_TYPE_VALUES,
    METADATA_REVIEW_STATUSES,
    REQUIRED_FIELDS,
    USAGE_SCENE_VALUES,
)


@dataclass(slots=True)
class MetadataValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_metadata(metadata: Mapping[str, Any]) -> MetadataValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in metadata:
            errors.append(f"缺少必填字段：{field_name}")
            continue
        value = metadata[field_name]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"必填字段为空：{field_name}")

    file_type = metadata.get("file_type")
    if isinstance(file_type, str) and file_type and not file_type.startswith("."):
        errors.append("file_type 必须使用带点的小写扩展名")

    sha256 = metadata.get("sha256")
    if isinstance(sha256, str) and sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        errors.append("sha256 必须是 64 位十六进制字符串")

    _validate_enum(metadata, "board", BOARD_VALUES, errors, warnings)
    _validate_enum(metadata, "knowledge_type", KNOWLEDGE_TYPE_VALUES, errors, warnings)
    _validate_enum(metadata, "discipline", DISCIPLINE_VALUES, errors, warnings)
    _validate_enum(metadata, "document_role", DOCUMENT_ROLE_VALUES, errors, warnings)
    _validate_enum(metadata, "authority_level", AUTHORITY_LEVEL_VALUES, errors, warnings)
    _validate_enum(metadata, "usage_scene", USAGE_SCENE_VALUES, errors, warnings)

    for field_name in CLASSIFICATION_FIELDS:
        if metadata.get(field_name) is None:
            warnings.append(f"企业分类字段未识别：{field_name}")

    for field_name in ("metadata_source", "metadata_rule", "metadata_confidence"):
        if field_name not in metadata or not isinstance(metadata[field_name], dict):
            errors.append(f"治理字段必须是对象：{field_name}")
    review_status = metadata.get("metadata_review_status")
    if review_status not in METADATA_REVIEW_STATUSES:
        errors.append(f"无效的 metadata_review_status：{review_status}")

    confidence = metadata.get("metadata_confidence")
    if isinstance(confidence, dict):
        for field_name, value in confidence.items():
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                errors.append(f"metadata_confidence 超出范围：{field_name}")

    return MetadataValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _validate_enum(
    metadata: Mapping[str, Any],
    field_name: str,
    allowed: tuple[str, ...],
    errors: list[str],
    warnings: list[str],
) -> None:
    value = metadata.get(field_name)
    if value is None or value == "":
        return
    if value not in allowed:
        errors.append(f"{field_name} 不在允许枚举中：{value}")
