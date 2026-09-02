from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


BOARD_VALUES = ("设计管理", "技术管理", "科技管理")
KNOWLEDGE_TYPE_VALUES = ("制度", "案例", "方法", "模板", "会议资料", "培训资料")
DISCIPLINE_VALUES = ("建筑", "结构", "机电", "BIM", "EPC")
DOCUMENT_ROLE_VALUES = (
    "正式制度",
    "管理指南",
    "标准模板",
    "项目案例",
    "培训材料",
    "汇报材料",
    "其他",
)
AUTHORITY_LEVEL_VALUES = ("L1", "L2", "L3", "L4", "L5", "L6", "UNKNOWN")
USAGE_SCENE_VALUES = (
    "制度执行",
    "管理指导",
    "标准复用",
    "项目复盘",
    "模板填报",
    "培训学习",
    "汇报交流",
    "专业设计",
    "其他",
)
METADATA_REVIEW_STATUSES = ("AUTO", "NEEDS_REVIEW", "MANUAL", "REJECTED")
REQUIRED_FIELDS = ("file_type", "file_name", "source_path", "sha256", "parse_status")
CLASSIFICATION_FIELDS = ("board", "knowledge_type", "discipline")


@dataclass(slots=True)
class MetadataRecord:
    file_type: str
    file_name: str
    source_path: str
    sha256: str
    parse_status: str
    board: str | None = None
    knowledge_type: str | None = None
    discipline: str | None = None
    document_role: str | None = None
    authority_level: str | None = None
    usage_scene: str | None = None
    metadata_source: dict[str, str] = field(default_factory=dict)
    metadata_rule: dict[str, str] = field(default_factory=dict)
    metadata_confidence: dict[str, float] = field(default_factory=dict)
    metadata_review_status: str = "NEEDS_REVIEW"
    schema_version: str = "metadata.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MetadataRecord":
        fields = {
            field_name: value[field_name]
            for field_name in (
                "file_type",
                "file_name",
                "source_path",
                "sha256",
                "parse_status",
            )
            if field_name in value
        }
        return cls(
            **fields,
            board=value.get("board"),
            knowledge_type=value.get("knowledge_type"),
            discipline=value.get("discipline"),
            document_role=value.get("document_role"),
            authority_level=value.get("authority_level"),
            usage_scene=value.get("usage_scene"),
            metadata_source=dict(value.get("metadata_source") or {}),
            metadata_rule=dict(value.get("metadata_rule") or {}),
            metadata_confidence=dict(value.get("metadata_confidence") or {}),
            metadata_review_status=value.get("metadata_review_status", "NEEDS_REVIEW"),
            schema_version=value.get("schema_version", "metadata.v1"),
        )
