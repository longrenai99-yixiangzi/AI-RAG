from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.ingestion.metadata.schema import (
    AUTHORITY_LEVEL_VALUES,
    DOCUMENT_ROLE_VALUES,
    USAGE_SCENE_VALUES,
)


RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "knowledge_governance_rules.yaml"


@dataclass(slots=True)
class GovernanceMetadata:
    document_role: str
    authority_level: str
    usage_scene: str
    source: str
    rule: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_role": self.document_role,
            "authority_level": self.authority_level,
            "usage_scene": self.usage_scene,
            "governance_source": self.source,
            "governance_rule": self.rule,
            "governance_confidence": self.confidence,
        }


class GovernanceClassifier:
    """Shadow governance classifier; it only derives ranking metadata."""

    def __init__(self, rules_path: Path = RULES_PATH) -> None:
        self.rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        self.role_priority = {
            str(key): int(value)
            for key, value in self.rules.get("document_role_priority", {}).items()
        }
        self.authority = {
            str(key): str(value)
            for key, value in self.rules.get("authority_level", {}).items()
        }
        self.role_rules = {
            str(role): [str(term) for term in terms]
            for role, terms in self.rules.get("document_role_rules", {}).items()
        }
        self.scene_rules = {
            str(scene): [str(term) for term in terms]
            for scene, terms in self.rules.get("usage_scene_rules", {}).items()
        }

    def classify(
        self,
        *,
        file_name: str,
        source_path: str = "",
        heading_path: str = "",
        text: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> GovernanceMetadata:
        metadata = metadata or {}
        evidence = {
            "file_name": file_name,
            "source_path": source_path,
            "heading_path": heading_path,
            "text": text[:4_000],
        }
        strong_text = " ".join(evidence[key] for key in ("file_name", "source_path", "heading_path"))
        role, role_source, role_term = self._classify_role(strong_text, evidence["text"])
        authority_level = self.authority.get(role, "UNKNOWN")
        usage_scene, scene_term = self._classify_scene(role, strong_text, evidence["text"], metadata)
        confidence = 0.92 if role_term and role_source != "text" else 0.68 if role_term else 0.0
        return GovernanceMetadata(
            document_role=role,
            authority_level=authority_level,
            usage_scene=usage_scene,
            source=role_source,
            rule=role_term or scene_term or "no_match",
            confidence=confidence,
        )

    def classify_payload(self, payload: Mapping[str, Any]) -> GovernanceMetadata:
        return self.classify(
            file_name=str(payload.get("file_name") or ""),
            source_path=str(payload.get("source_path") or ""),
            heading_path=str(payload.get("heading_path") or ""),
            text=str(payload.get("text") or ""),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {},
        )

    def _classify_role(self, strong_text: str, body_text: str) -> tuple[str, str, str | None]:
        for source, haystack in (("file_name_or_path", strong_text), ("text", body_text)):
            if not haystack:
                continue
            matches = [
                (role, term)
                for role in DOCUMENT_ROLE_VALUES
                if role != "其他"
                for term in self.role_rules.get(role, [])
                if term in haystack
            ]
            if matches:
                # Highest document priority wins when a file name contains more than one signal.
                role, term = max(
                    matches,
                    key=lambda item: (self.role_priority.get(item[0], 0), len(item[1])),
                )
                return role, source, term
        return "其他", "unmatched", None

    def _classify_scene(
        self,
        role: str,
        strong_text: str,
        body_text: str,
        metadata: Mapping[str, Any],
    ) -> tuple[str, str | None]:
        role_scene = {
            "正式制度": "制度执行",
            "管理指南": "管理指导",
            "标准模板": "标准复用",
            "项目案例": "项目复盘",
            "培训材料": "培训学习",
            "汇报材料": "汇报交流",
        }.get(role)
        if role_scene:
            return role_scene, role_scene
        haystack = f"{strong_text} {body_text}"
        for scene in USAGE_SCENE_VALUES:
            for term in self.scene_rules.get(scene, []):
                if term in haystack:
                    return scene, term
        knowledge_type = str(metadata.get("knowledge_type") or "")
        if knowledge_type == "培训资料":
            return "培训学习", "knowledge_type_training"
        if knowledge_type == "案例":
            return "项目复盘", "knowledge_type_case"
        return "其他", None


def governance_boost(governance: GovernanceMetadata, question_type: str) -> float:
    """Soft role preference; mismatches are never filtered out."""

    preferences = {
        "POLICY_QUERY": ("正式制度", "管理指南", "标准模板", "项目案例", "培训材料", "汇报材料"),
        "METHOD_QUERY": ("管理指南", "标准模板", "正式制度", "项目案例", "培训材料", "汇报材料"),
        "TEMPLATE_QUERY": ("标准模板", "管理指南", "正式制度", "项目案例", "培训材料", "汇报材料"),
        "CASE_QUERY": ("项目案例", "管理指南", "标准模板", "正式制度", "培训材料", "汇报材料"),
        "DISCIPLINE_QUERY": ("管理指南", "项目案例", "标准模板", "正式制度", "培训材料", "汇报材料"),
    }
    ordered = preferences.get(question_type, preferences["METHOD_QUERY"])
    if governance.document_role in ordered:
        rank = ordered.index(governance.document_role)
        return max(0.0, 1.0 - rank * 0.16)
    return self_priority_score(governance.document_role)


def self_priority_score(role: str) -> float:
    return {
        "正式制度": 0.12,
        "管理指南": 0.10,
        "标准模板": 0.08,
        "项目案例": 0.06,
        "培训材料": 0.03,
        "汇报材料": 0.0,
    }.get(role, 0.0)
