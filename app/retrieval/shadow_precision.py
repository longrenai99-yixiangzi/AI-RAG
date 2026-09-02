from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceMetadata, governance_boost


INTENT_ORDER = (
    "TEMPLATE_QUERY",
    "POLICY_QUERY",
    "CASE_QUERY",
    "METHOD_QUERY",
    "DISCIPLINE_QUERY",
)

INTENT_PHRASES = {
    "POLICY_QUERY": (
        "制度",
        "规定",
        "规范",
        "要求",
        "办法",
        "审查",
        "评审",
        "变更",
        "标准",
        "管理流程",
        "管理指南",
    ),
    "CASE_QUERY": (
        "案例",
        "经验",
        "复盘",
        "总结",
        "项目实践",
        "创效",
        "述职",
    ),
    "METHOD_QUERY": (
        "如何",
        "怎么",
        "方法",
        "步骤",
        "编制",
        "策划",
        "流程",
        "工作计划",
    ),
    "TEMPLATE_QUERY": (
        "模板",
        "表单",
        "表格",
        "清单",
        "任务书",
        "栏目",
    ),
    "DISCIPLINE_QUERY": (
        "建筑",
        "结构",
        "机电",
        "暖通",
        "给排水",
        "电气",
        "景观",
        "室内",
        "幕墙",
        "BIM",
        "EPC",
        "专业",
        "深化设计",
    ),
}

KNOWLEDGE_TYPE_BY_INTENT = {
    "POLICY_QUERY": "制度",
    "CASE_QUERY": "案例",
    "METHOD_QUERY": "方法",
    "TEMPLATE_QUERY": "模板",
}

BOARD_TERMS = {
    "设计管理": ("设计管理", "设计策划", "设计评审"),
    "技术管理": ("技术管理", "技术工作", "技术标准"),
    "科技管理": ("科技管理", "科技创新", "数字化", "成果推广"),
}

DISCIPLINE_TERMS = {
    "建筑": ("建筑",),
    "结构": ("结构",),
    "机电": ("机电", "暖通", "给排水", "电气"),
    "BIM": ("BIM",),
    "EPC": ("EPC",),
}

METADATA_WEIGHTS = {
    "board": 0.18,
    "knowledge_type": 0.42,
    "discipline": 0.30,
}

FUSION_WEIGHTS = {
    "rrf": 0.45,
    "reranker": 0.40,
    "metadata": 0.10,
    "document_type": 0.05,
    "governance": 0.0,
}


@dataclass(slots=True)
class PrecisionIntent:
    question: str
    question_type: str
    knowledge_type: str | None
    metadata_hints: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    matched_terms: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class OptimizedRanking:
    hits: list[SearchHit]
    score_by_chunk: dict[str, float]
    component_by_chunk: dict[str, dict[str, float]]


def analyze_precision_intent(question: str) -> PrecisionIntent:
    normalized = question.strip()
    scores: dict[str, float] = {intent: 0.0 for intent in INTENT_ORDER}
    matched_terms: dict[str, list[str]] = {intent: [] for intent in INTENT_ORDER}
    for intent, phrases in INTENT_PHRASES.items():
        for phrase in phrases:
            if phrase in normalized:
                scores[intent] += 1.0 + min(len(phrase), 6) * 0.04
                matched_terms[intent].append(phrase)

    # Short question forms add semantic intent evidence without an LLM call.
    if normalized.startswith(("如何", "怎么", "怎样", "哪些", "应当")):
        scores["METHOD_QUERY"] += 0.8
    if "哪些要求" in normalized or "有什么要求" in normalized:
        scores["POLICY_QUERY"] += 0.7
    if "案例" in normalized or "经验" in normalized or "复盘" in normalized:
        scores["CASE_QUERY"] += 0.8

    question_type = max(
        INTENT_ORDER,
        key=lambda intent: (scores[intent], -INTENT_ORDER.index(intent)),
    )
    if scores[question_type] == 0:
        question_type = "DISCIPLINE_QUERY" if any(
            phrase in normalized for phrase in INTENT_PHRASES["DISCIPLINE_QUERY"]
        ) else "METHOD_QUERY"

    metadata_hints: dict[str, str] = {}
    for board, terms in BOARD_TERMS.items():
        if any(term in normalized for term in terms):
            metadata_hints["board"] = board
            break
    knowledge_type = KNOWLEDGE_TYPE_BY_INTENT.get(question_type)
    if knowledge_type:
        metadata_hints["knowledge_type"] = knowledge_type
    for discipline, terms in DISCIPLINE_TERMS.items():
        if any(term in normalized for term in terms):
            metadata_hints["discipline"] = discipline
            break

    return PrecisionIntent(
        question=normalized,
        question_type=question_type,
        knowledge_type=knowledge_type,
        metadata_hints=metadata_hints,
        scores=scores,
        matched_terms={key: value for key, value in matched_terms.items() if value},
    )


def metadata_soft_boost(metadata: dict[str, Any], intent: PrecisionIntent) -> float:
    if not intent.metadata_hints:
        return 0.0
    total = sum(METADATA_WEIGHTS[field] for field in intent.metadata_hints)
    matched = sum(
        METADATA_WEIGHTS[field]
        for field, expected in intent.metadata_hints.items()
        if metadata.get(field) == expected
    )
    return matched / total if total else 0.0


def document_type_boost(chunk: Chunk, intent: PrecisionIntent) -> float:
    searchable = f"{chunk.file_name} {chunk.heading_path} {chunk.text[:800]}".casefold()
    score = 0.0
    if intent.question_type == "POLICY_QUERY":
        if any(term.casefold() in searchable for term in ("制度", "规范", "标准", "指南", "办法", "流程")):
            score += 1.0
        if any(term.casefold() in searchable for term in ("项目总结", "总结", "述职", "培训")):
            score -= 0.75
        if chunk.file_name.casefold().endswith(".pptx") and any(
            term.casefold() in searchable for term in ("总结", "述职", "培训")
        ):
            score -= 0.35
    elif intent.question_type == "CASE_QUERY":
        if any(term.casefold() in searchable for term in ("案例", "项目", "复盘", "经验", "总结")):
            score += 1.0
    elif intent.question_type == "METHOD_QUERY":
        if any(term.casefold() in searchable for term in ("方法", "指南", "流程", "手册", "任务书", "计划")):
            score += 0.8
        if "述职" in searchable:
            score -= 0.5
    elif intent.question_type == "TEMPLATE_QUERY":
        if any(term.casefold() in searchable for term in ("模板", "表格", "清单", "任务书", "表单")):
            score += 1.0
        if chunk.file_name.casefold().endswith((".xlsx", ".docx")):
            score += 0.25
    elif intent.question_type == "DISCIPLINE_QUERY":
        if any(value.casefold() in searchable for value in intent.metadata_hints.values()):
            score += 0.8
    return max(-1.0, min(1.0, score))


def optimize_ranking(
    candidates: list[SearchHit],
    metadata_by_chunk: dict[str, dict[str, Any]],
    intent: PrecisionIntent,
    *,
    final_limit: int = 5,
    weights: dict[str, float] | None = None,
    governance_by_chunk: dict[str, GovernanceMetadata] | None = None,
) -> OptimizedRanking:
    if not candidates:
        return OptimizedRanking([], {}, {})
    rrf_scores = _normalize([hit.score for hit in candidates])
    reranker_scores = _normalize(
        [hit.reranker_score if hit.reranker_score is not None else 0.0 for hit in candidates]
    )
    score_by_chunk: dict[str, float] = {}
    component_by_chunk: dict[str, dict[str, float]] = {}
    fusion_weights = weights or FUSION_WEIGHTS
    for index, hit in enumerate(candidates):
        metadata_score = metadata_soft_boost(
            metadata_by_chunk.get(hit.chunk.chunk_id, {}), intent
        )
        type_score = document_type_boost(hit.chunk, intent)
        governance_score = (
            governance_boost(
                governance_by_chunk[hit.chunk.chunk_id], intent.question_type
            )
            if governance_by_chunk and hit.chunk.chunk_id in governance_by_chunk
            else 0.0
        )
        combined = (
            fusion_weights["rrf"] * rrf_scores[index]
            + fusion_weights["reranker"] * reranker_scores[index]
            + fusion_weights["metadata"] * metadata_score
            + fusion_weights["document_type"] * type_score
            + fusion_weights.get("governance", 0.0) * governance_score
        )
        score_by_chunk[hit.chunk.chunk_id] = combined
        component_by_chunk[hit.chunk.chunk_id] = {
            "rrf": rrf_scores[index],
            "reranker": reranker_scores[index],
            "metadata": metadata_score,
            "document_type": type_score,
            "governance": governance_score,
            "combined": combined,
        }
    ordered = sorted(
        candidates,
        key=lambda hit: (-score_by_chunk[hit.chunk.chunk_id], hit.chunk.chunk_id),
    )
    return OptimizedRanking(
        hits=ordered[:final_limit],
        score_by_chunk=score_by_chunk,
        component_by_chunk=component_by_chunk,
    )


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high <= low:
        return [0.5] * len(values)
    return [(value - low) / (high - low) for value in values]
