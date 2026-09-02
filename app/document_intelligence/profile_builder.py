from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from app.domain import Chunk
from app.ingestion.metadata.governance import GovernanceMetadata


SCOPE_TERMS = {
    "board": ("设计管理", "技术管理", "科技管理"),
    "discipline": ("建筑", "结构", "机电", "暖通", "给排水", "电气", "景观", "室内", "幕墙", "BIM", "EPC"),
    "building_type": ("住宅", "公建", "医院", "学校", "厂房", "数据中心", "商业", "办公", "城市更新"),
    "project_stage": ("投标", "设计策划", "方案设计", "初步设计", "施工图设计", "深化设计", "施工实施", "竣工总结"),
}

TOPIC_TERMS = (
    "设计管理",
    "设计评审",
    "设计变更",
    "设计策划",
    "设计任务书",
    "设计计划",
    "专业接口",
    "EPC",
    "BIM",
    "设计创效",
    "施工图",
    "深化设计",
    "项目复盘",
    "经验总结",
    "知识治理",
    "质量检查",
    "版本管理",
    "设计交付",
    "标准",
    "模板",
    "培训",
    "成果总结",
)


@dataclass(slots=True)
class DocumentProfile:
    document_id: str
    document_name: str
    source_path: str
    file_type: str
    sha256: str
    profile_version: str
    document_role: str
    authority_level: str
    usage_scene: str
    scope: dict[str, list[str]]
    contains_topics: list[str]
    not_for: list[str]
    related_documents: list[dict[str, Any]]
    profile_source: str
    profile_confidence: float
    profile_review_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_profile(
    *,
    document_id: str,
    document_name: str,
    source_path: str,
    file_type: str,
    sha256: str,
    chunks: Sequence[Chunk],
    metadata: Mapping[str, Any],
    governance: GovernanceMetadata,
) -> DocumentProfile:
    text = "\n".join(
        [document_name, source_path]
        + [chunk.heading_path for chunk in chunks]
        + [chunk.text[:4_000] for chunk in chunks[:8]]
    )
    scope = _build_scope(text, metadata)
    topics = _build_topics(text)
    not_for = _build_not_for(governance, scope, text)
    confidence = _profile_confidence(governance, scope, topics)
    return DocumentProfile(
        document_id=document_id,
        document_name=document_name,
        source_path=source_path,
        file_type=file_type,
        sha256=sha256,
        profile_version="document-profile.v1",
        document_role=governance.document_role,
        authority_level=governance.authority_level,
        usage_scene=governance.usage_scene,
        scope=scope,
        contains_topics=topics,
        not_for=not_for,
        related_documents=[],
        profile_source="rule+metadata+governance",
        profile_confidence=confidence,
        profile_review_status="NEEDS_REVIEW" if confidence < 0.8 else "AUTO",
    )


def link_related_documents(
    profiles: Sequence[DocumentProfile],
) -> list[DocumentProfile]:
    groups: dict[str, list[DocumentProfile]] = {}
    for profile in profiles:
        for project_name in profile.scope.get("project_name", []):
            groups.setdefault(project_name, []).append(profile)
    for group in groups.values():
        if len(group) < 2:
            continue
        for profile in group:
            related = [
                {
                    "document_id": other.document_id,
                    "relation": "related_to",
                    "confidence": 0.78,
                    "evidence": f"scope.project_name={group_name}",
                }
                for group_name in profile.scope.get("project_name", [])
                for other in group
                if other.document_id != profile.document_id
            ]
            profile.related_documents = _dedupe_related(related)[:8]
    return list(profiles)


def _build_scope(text: str, metadata: Mapping[str, Any]) -> dict[str, list[str]]:
    scope: dict[str, list[str]] = {}
    for field, terms in SCOPE_TERMS.items():
        values = [term for term in terms if term in text]
        if values:
            scope[field] = list(dict.fromkeys(values))
    for field in ("board", "discipline", "building_type", "project_stage"):
        value = metadata.get(field)
        if value and field not in scope:
            scope[field] = [str(value)]
    project_names = _project_names(text)
    if project_names:
        scope["project_name"] = project_names
    return scope


def _project_names(text: str) -> list[str]:
    candidates: list[str] = []
    for part in text.replace("\\", "/").split("/"):
        cleaned = part.strip()
        if "项目" in cleaned and 2 <= len(cleaned) <= 60:
            candidates.append(cleaned.rsplit(".", 1)[0])
    return list(dict.fromkeys(candidates))[:5]


def _build_topics(text: str) -> list[str]:
    return [term for term in TOPIC_TERMS if term in text][:12]


def _build_not_for(
    governance: GovernanceMetadata,
    scope: Mapping[str, list[str]],
    text: str,
) -> list[str]:
    limitations: list[str] = []
    explicit_terms = ("仅供参考", "仅用于培训", "不作为正式", "不替代", "不适用于")
    for term in explicit_terms:
        if term in text:
            limitations.append(f"原文包含限制语句：{term}")
    if governance.document_role in {"项目案例", "培训材料", "汇报材料"}:
        limitations.append("不作为正式制度条款")
    if governance.document_role == "项目案例" and scope.get("project_name"):
        limitations.append("不自动外推到其他项目")
    if governance.authority_level not in {"L1", "L2"}:
        limitations.append("重要制度结论需结合正式制度或管理指南核验")
    return list(dict.fromkeys(limitations))


def _profile_confidence(
    governance: GovernanceMetadata,
    scope: Mapping[str, list[str]],
    topics: Sequence[str],
) -> float:
    score = governance.confidence
    if scope:
        score += 0.04
    if topics:
        score += 0.04
    return min(0.98, round(score, 3))


def _dedupe_related(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        document_id = str(value["document_id"])
        if document_id in seen:
            continue
        seen.add(document_id)
        result.append(value)
    return result
