from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.domain import SearchHit
from app.ingestion.metadata.governance import GovernanceMetadata

from .answer_policy import AnswerPolicy


@dataclass(slots=True)
class EvidenceItem:
    source_id: str
    chunk_id: str
    document_id: str
    file_name: str
    source_path: str
    document_role: str
    authority_level: str
    usage_scene: str
    location: dict[str, Any]
    excerpt: str
    retrieval_score: float
    selection_score: float
    evidence_status: str
    document_score: float = 0.0


@dataclass(slots=True)
class EvidenceBundle:
    items: list[EvidenceItem] = field(default_factory=list)
    status: str = "NO_EVIDENCE"
    selection_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentAggregate:
    document_id: str
    file_name: str
    source_path: str
    document_role: str
    authority_level: str
    usage_scene: str
    chunk_count: int
    highest_score: float
    document_score: float
    hits: list[SearchHit] = field(default_factory=list)


def select_evidence(
    hits: Sequence[SearchHit],
    policy: AnswerPolicy,
    governance_by_chunk: Mapping[str, GovernanceMetadata],
    *,
    max_items: int = 5,
    max_items_per_document: int = 2,
) -> EvidenceBundle:
    if not hits:
        return EvidenceBundle(status="NO_EVIDENCE", selection_notes=["没有可用检索结果"])

    ranked: list[tuple[float, int, SearchHit, GovernanceMetadata]] = []
    for index, hit in enumerate(hits):
        governance = governance_by_chunk.get(hit.chunk.chunk_id)
        if governance is None:
            governance = GovernanceMetadata(
                document_role="其他",
                authority_level="UNKNOWN",
                usage_scene="其他",
                source="missing",
                rule="missing",
                confidence=0.0,
            )
        role_score = 1.0 if governance.document_role in policy.preferred_roles else 0.0
        knowledge_score = 0.5 if policy.evidence_mode == "evidence_only" else 0.0
        location_score = 0.15 if hit.chunk.location else 0.0
        rank_score = 1.0 / (index + 1)
        selection_score = 0.55 * rank_score + 0.25 * role_score + 0.10 * knowledge_score + location_score
        status = "DIRECT" if role_score else "SUPPORTING"
        ranked.append((selection_score, index, hit, governance))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2].chunk.chunk_id))
    selected: list[EvidenceItem] = []
    seen_chunks: set[str] = set()
    document_counts: dict[str, int] = {}
    for selection_score, _, hit, governance in ranked:
        chunk = hit.chunk
        if chunk.chunk_id in seen_chunks:
            continue
        if document_counts.get(chunk.document_id, 0) >= max_items_per_document:
            continue
        seen_chunks.add(chunk.chunk_id)
        document_counts[chunk.document_id] = document_counts.get(chunk.document_id, 0) + 1
        selected.append(
            EvidenceItem(
                source_id=f"S{len(selected) + 1}",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                file_name=chunk.file_name,
                source_path=chunk.source_path,
                document_role=governance.document_role,
                authority_level=governance.authority_level,
                usage_scene=governance.usage_scene,
                location=dict(chunk.location),
                excerpt=chunk.text[:900],
                retrieval_score=float(hit.score),
                selection_score=float(selection_score),
                evidence_status="DIRECT" if governance.document_role in policy.preferred_roles else "SUPPORTING",
            )
        )
        if len(selected) >= max_items:
            break

    notes: list[str] = []
    if not selected:
        notes.append("候选结果存在，但没有通过文档多样性与证据选择规则")
    if selected and not any(item.evidence_status == "DIRECT" for item in selected):
        notes.append("没有命中该回答策略的首选文档角色，结果仅作为补充证据")
    return EvidenceBundle(
        items=selected,
        status="SELECTED" if selected else "INSUFFICIENT",
        selection_notes=notes,
    )


def select_evidence_optimized(
    hits: Sequence[SearchHit],
    policy: AnswerPolicy,
    governance_by_chunk: Mapping[str, GovernanceMetadata],
    *,
    max_items: int = 5,
    max_items_per_document: int = 2,
) -> EvidenceBundle:
    """File-level aggregation plus authority-aware, role-diverse selection."""

    aggregates = _aggregate_documents(hits, governance_by_chunk, policy)
    if not aggregates:
        return EvidenceBundle(status="NO_EVIDENCE", selection_notes=["没有可用检索结果"])

    ordered = sorted(
        aggregates.values(),
        key=lambda item: (-item.document_score, item.document_id),
    )
    selected_documents = _select_diverse_documents(ordered, max_items)
    selected: list[EvidenceItem] = []
    for document in selected_documents:
        document_hits = sorted(
            document.hits,
            key=lambda hit: (
                -(hit.reranker_score if hit.reranker_score is not None else hit.score),
                hit.chunk.chunk_id,
            ),
        )
        for hit in document_hits[:max_items_per_document]:
            governance = governance_by_chunk.get(hit.chunk.chunk_id)
            if governance is None:
                continue
            direct = governance.document_role in policy.preferred_roles
            selected.append(
                EvidenceItem(
                    source_id=f"S{len(selected) + 1}",
                    chunk_id=hit.chunk.chunk_id,
                    document_id=hit.chunk.document_id,
                    file_name=hit.chunk.file_name,
                    source_path=hit.chunk.source_path,
                    document_role=governance.document_role,
                    authority_level=governance.authority_level,
                    usage_scene=governance.usage_scene,
                    location=dict(hit.chunk.location),
                    excerpt=hit.chunk.text[:900],
                    retrieval_score=float(hit.score),
                    selection_score=float(document.document_score),
                    evidence_status="DIRECT" if direct else "SUPPORTING",
                    document_score=float(document.document_score),
                )
            )
            if len(selected) >= max_items:
                break
        if len(selected) >= max_items:
            break

    roles = {item.document_role for item in selected}
    notes = [
        f"文件级聚合文档数：{len(aggregates)}",
        f"选择文档数：{len(selected_documents)}",
    ]
    if len(roles) > 1:
        notes.append("已执行角色多样性选择")
    return EvidenceBundle(
        items=selected,
        status="SELECTED" if selected else "INSUFFICIENT",
        selection_notes=notes,
    )


def _aggregate_documents(
    hits: Sequence[SearchHit],
    governance_by_chunk: Mapping[str, GovernanceMetadata],
    policy: AnswerPolicy,
) -> dict[str, DocumentAggregate]:
    grouped: dict[str, DocumentAggregate] = {}
    raw_scores = [
        hit.reranker_score if hit.reranker_score is not None else hit.score
        for hit in hits
    ]
    low = min(raw_scores) if raw_scores else 0.0
    high = max(raw_scores) if raw_scores else 1.0
    for index, hit in enumerate(hits):
        governance = governance_by_chunk.get(hit.chunk.chunk_id)
        if governance is None:
            continue
        raw_score = raw_scores[index]
        normalized_score = (
            (raw_score - low) / (high - low) if high > low else 0.5
        )
        aggregate = grouped.get(hit.chunk.document_id)
        if aggregate is None:
            aggregate = DocumentAggregate(
                document_id=hit.chunk.document_id,
                file_name=hit.chunk.file_name,
                source_path=hit.chunk.source_path,
                document_role=governance.document_role,
                authority_level=governance.authority_level,
                usage_scene=governance.usage_scene,
                chunk_count=0,
                highest_score=normalized_score,
                document_score=0.0,
            )
            grouped[hit.chunk.document_id] = aggregate
        aggregate.chunk_count += 1
        aggregate.highest_score = max(aggregate.highest_score, normalized_score)
        aggregate.hits.append(hit)

    for aggregate in grouped.values():
        role_score = _authority_role_score(aggregate.document_role, policy)
        chunk_support = min(1.0, aggregate.chunk_count / 3.0)
        aggregate.document_score = (
            0.55 * aggregate.highest_score
            + 0.25 * role_score
            + 0.20 * chunk_support
        )
    return grouped


def _select_diverse_documents(
    ordered: list[DocumentAggregate],
    limit: int,
) -> list[DocumentAggregate]:
    if not ordered:
        return []
    selected: list[DocumentAggregate] = [ordered[0]]
    selected_roles = {ordered[0].document_role}
    for candidate in ordered[1:]:
        if len(selected) >= limit:
            break
        if candidate.document_role not in selected_roles:
            selected.append(candidate)
            selected_roles.add(candidate.document_role)
            break
    for candidate in ordered[1:]:
        if len(selected) >= limit:
            break
        if candidate.document_id not in {item.document_id for item in selected}:
            selected.append(candidate)
    return selected


def _authority_role_score(role: str, policy: AnswerPolicy) -> float:
    if role in policy.preferred_roles:
        return max(0.55, 1.0 - 0.12 * policy.preferred_roles.index(role))
    return {
        "正式制度": 0.45,
        "管理指南": 0.40,
        "标准模板": 0.35,
        "项目案例": 0.30,
        "培训材料": 0.15,
        "汇报材料": 0.08,
    }.get(role, 0.0)
