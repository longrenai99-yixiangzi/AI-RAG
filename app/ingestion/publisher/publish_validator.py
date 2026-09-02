from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ingestion.metadata.validator import validate_metadata
from app.ingestion.publisher.staging_reader import STAGING_SCHEMA_VERSION, StagingDocument


@dataclass(slots=True)
class PublishValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_publish_input(staging: StagingDocument) -> PublishValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if staging.schema_version != STAGING_SCHEMA_VERSION:
        errors.append(f"不支持的 Staging Schema：{staging.schema_version}")
    if not staging.status:
        errors.append("Staging status 不能为空")
    if staging.status in {"read_error", "encoding_error"}:
        errors.append(f"状态不可发布：{staging.status}")
    if staging.error:
        errors.append(f"Staging 包含错误：{staging.error}")

    metadata_result = validate_metadata(staging.metadata)
    errors.extend(f"Metadata：{error}" for error in metadata_result.errors)
    warnings.extend(f"Metadata：{warning}" for warning in metadata_result.warnings)

    chunk_ids: set[str] = set()
    for index, chunk in enumerate(staging.chunks):
        chunk_id = str(chunk.get("chunk_id", ""))
        if not chunk_id:
            errors.append(f"Chunk[{index}] 缺少 chunk_id")
        elif chunk_id in chunk_ids:
            errors.append(f"Chunk ID 重复：{chunk_id}")
        chunk_ids.add(chunk_id)
        if not str(chunk.get("text", "")).strip():
            warnings.append(f"Chunk[{index}] 文本为空：{chunk_id}")
        if not chunk.get("location"):
            errors.append(f"Chunk[{index}] 缺少 location：{chunk_id}")

        chunk_metadata = chunk.get("metadata") or staging.metadata
        chunk_metadata_result = validate_metadata(chunk_metadata)
        errors.extend(
            f"Chunk[{index}] Metadata：{error}" for error in chunk_metadata_result.errors
        )

    if staging.status == "parsed" and not staging.chunks:
        errors.append("parsed Staging 不包含任何 Chunk")
    if staging.status == "empty" and staging.chunks:
        errors.append("empty Staging 不应包含 Chunk")

    return PublishValidationResult(valid=not errors, errors=errors, warnings=warnings)
