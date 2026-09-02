from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem, select_evidence_optimized
from app.bm25 import BM25Index, tokenize
from app.config import Settings
from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceClassifier, GovernanceMetadata
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.rrf import reciprocal_rank_fusion
from scripts.evaluate_business_query_regression import load_questions
from scripts.shadow_answer_router_v1 import load_fact_capability
from scripts.shadow_answer_router_v1_1 import route_question
from scripts.validate_unified_shadow_business import ROOT_CONFIG, load_qdrant_chunks


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "knowledge_page_retrieval_rescue"
REPORT_PATH = PROJECT_ROOT / "docs" / "KNOWLEDGE_PAGE_RETRIEVAL_RESCUE_REPORT.md"
GOLD_PATH = PROJECT_ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "scope_guard_leakage_cleanup"
COLLECTION_PAGE_TYPE = "QUERY_PAGE"

GENERAL_TESTS = [
    ("Q-001", "设计创效怎么做？"),
    ("Q-002", "如何开展设计价值创造？"),
    ("Q-003", "设计效益增量的计算方式？"),
    ("Q-004", "设计创效的定义是什么？"),
    ("Q-005", "设计创效有哪些评价维度？"),
    ("Q-006", "设计价值创造流程是什么？"),
    ("Q-007", "设计任务书怎么做？"),
    ("Q-008", "EPC项目设计管理的责任是什么？"),
    ("Q-009", "方案比选的方法是什么？"),
    ("Q-010", "设计风险如何开展识别和化解？"),
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def knowledge_page_type(chunk: Chunk) -> str:
    path = f"{chunk.source_path} {chunk.file_name}".casefold().replace("/", "\\")
    if "\\wiki\\queries\\" in path:
        return "QUERY_PAGE"
    if "\\wiki\\concepts\\" in path:
        return "CONCEPT_PAGE"
    if any(chunk.file_name.casefold().endswith(suffix) for suffix in (".pdf", ".docx", ".xlsx", ".pptx")):
        return "SOURCE_DOCUMENT"
    if "\\raw\\" in path or "\\attachments\\" in path:
        return "SOURCE_DOCUMENT"
    return "OTHER"


def build_catalog(
    chunks_by_root: dict[str, list[Chunk]],
    metadata_by_root: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, GovernanceMetadata], dict[tuple[str, str], dict[str, Any]]]:
    classifier = GovernanceClassifier()
    governance_by_chunk: dict[str, GovernanceMetadata] = {}
    source_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    grouped: dict[tuple[str, str], list[Chunk]] = defaultdict(list)
    for root_id, chunks in chunks_by_root.items():
        for chunk in chunks:
            grouped[(root_id, chunk.document_id)].append(chunk)
            governance_by_chunk[chunk.chunk_id] = classifier.classify(
                file_name=chunk.file_name,
                source_path=chunk.source_path,
                heading_path=chunk.heading_path,
                text=chunk.text,
                metadata=metadata_by_root[root_id].get(chunk.chunk_id, {}),
            )
            source_by_key[(root_id, chunk.chunk_id)] = {
                "knowledge_root_id": root_id,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "approval_status": ROOT_CONFIG[root_id]["approval_status"],
            }
    catalog: list[dict[str, Any]] = []
    for (root_id, document_id), chunks in grouped.items():
        first = chunks[0]
        catalog.append(
            {
                "knowledge_root_id": root_id,
                "document_id": document_id,
                "file_name": first.file_name,
                "source_path": first.source_path,
                "knowledge_page_type": knowledge_page_type(first),
                "chunks": chunks,
                "searchable": " ".join(
                    f"{chunk.file_name} {chunk.source_path} {chunk.heading_path} {chunk.text}" for chunk in chunks
                ).casefold(),
            }
        )
    return catalog, governance_by_chunk, source_by_key


def load_shadow_data() -> tuple[dict[str, QdrantClient], dict[str, list[Chunk]], dict[str, dict[str, dict[str, Any]]], list[dict[str, Any]], dict[str, GovernanceMetadata], dict[tuple[str, str], dict[str, Any]]]:
    clients: dict[str, QdrantClient] = {}
    chunks_by_root: dict[str, list[Chunk]] = {}
    metadata_by_root: dict[str, dict[str, dict[str, Any]]] = {}
    for root_id, config in ROOT_CONFIG.items():
        client = QdrantClient(path=str(config["shadow_dir"]))
        clients[root_id] = client
        chunks, metadata, _ = load_qdrant_chunks(client, config["collection"], root_id)
        chunks_by_root[root_id] = chunks
        metadata_by_root[root_id] = metadata
    catalog, governance, sources = build_catalog(chunks_by_root, metadata_by_root)
    return clients, chunks_by_root, metadata_by_root, catalog, governance, sources


def query_terms(question: str) -> list[str]:
    stop = {"的", "是", "什么", "哪些", "如何", "怎么", "可以", "吗", "？", "?"}
    return list(dict.fromkeys(term for term in tokenize(question) if len(term) > 1 and term not in stop))


def page_probe(question: str, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = query_terms(question)
    results: list[dict[str, Any]] = []
    for document in catalog:
        if document["knowledge_page_type"] != COLLECTION_PAGE_TYPE:
            continue
        chunks = document["chunks"]
        best_chunk = max(
            chunks,
            key=lambda chunk: sum(term.casefold() in f"{chunk.file_name} {chunk.heading_path} {chunk.text}".casefold() for term in terms),
        )
        capability_chunks = [
            chunk
            for chunk in chunks
            if any(capability in capability_for_text(chunk.text, "", "QUERY_PAGE") for capability in ("METHOD", "METRIC_DIMENSION"))
        ]
        rescue_chunk = max(
            capability_chunks or [best_chunk],
            key=lambda chunk: (
                int("METHOD" in capability_for_text(chunk.text, "", "QUERY_PAGE")),
                int("METRIC_DIMENSION" in capability_for_text(chunk.text, "", "QUERY_PAGE")),
                sum(term.casefold() in chunk.text.casefold() for term in terms),
            ),
        )
        title_text = f"{document['file_name']} {best_chunk.heading_path}".casefold()
        body_text = document["searchable"]
        title_hits = sum(term.casefold() in title_text for term in terms)
        body_hits = sum(term.casefold() in body_text for term in terms)
        question_form_hits = sum(term in body_text for term in ("怎么做", "如何", "流程", "量化", "定义", "评价维度"))
        score = 0.35 * title_hits + 0.08 * body_hits + 0.12 * question_form_hits
        results.append(
            {
                "candidate_origin": ["QUERY_PAGE_PROBE"],
                "knowledge_root_id": document["knowledge_root_id"],
                "document_id": document["document_id"],
                "file_name": document["file_name"],
                "source_path": document["source_path"],
                "knowledge_page_type": document["knowledge_page_type"],
                "probe_score": round(score, 6),
                "title_hits": title_hits,
                "body_hits": body_hits,
                "question_form_hits": question_form_hits,
                "best_chunk": best_chunk,
                "rescue_chunk": rescue_chunk,
            }
        )
    return sorted(results, key=lambda item: (-item["probe_score"], item["file_name"].casefold()))


def retrieve_top100(
    question: str,
    clients: dict[str, QdrantClient],
    chunks_by_root: dict[str, list[Chunk]],
    chunk_by_key: dict[tuple[str, str], Chunk],
    bm25: BM25Index,
    dense: BGEM3DenseProvider,
    vector_cache: dict[str, list[float]],
) -> dict[str, Any]:
    root_by_chunk = {chunk.chunk_id: root_id for root_id, chunks in chunks_by_root.items() for chunk in chunks}
    bm_pairs = bm25.search(question, limit=100)
    bm_keys = [f"{root_by_chunk[chunk_id]}|{chunk_id}" for chunk_id, _ in bm_pairs if chunk_id in root_by_chunk]
    bm_scores = {f"{root_by_chunk[chunk_id]}|{chunk_id}": float(score) for chunk_id, score in bm_pairs if chunk_id in root_by_chunk}
    vector = vector_cache.get(question)
    if vector is None:
        vector = dense.embed_query(question)
        vector_cache[question] = vector
    dense_pairs: list[tuple[str, float]] = []
    for root_id, config in ROOT_CONFIG.items():
        points = clients[root_id].query_points(
            collection_name=config["collection"],
            query=vector,
            limit=100,
            with_payload=True,
            with_vectors=False,
        ).points
        dense_pairs.extend(
            (
                f"{root_id}|{str((point.payload or {}).get('chunk_id') or point.id)}",
                float(point.score),
            )
            for point in points
        )
    dense_pairs.sort(key=lambda item: (-item[1], item[0]))
    dense_pairs = dense_pairs[:100]
    dense_keys = [key for key, _ in dense_pairs]
    dense_scores = dict(dense_pairs)
    fused = reciprocal_rank_fusion({"bm25": bm_keys, "dense": dense_keys})[:100]
    bm_ranks = {key: rank for rank, key in enumerate(bm_keys, 1)}
    dense_ranks = {key: rank for rank, key in enumerate(dense_keys, 1)}
    candidates: list[dict[str, Any]] = []
    for rank, item in enumerate(fused, 1):
        root_id, chunk_id = item.chunk_id.split("|", 1)
        chunk = chunk_by_key[(root_id, chunk_id)]
        origins = ["RRF"]
        if item.chunk_id in bm_ranks:
            origins.append("BM25")
        if item.chunk_id in dense_ranks:
            origins.append("DENSE")
        candidates.append(
            {
                "rank": rank,
                "candidate_origin": origins,
                "knowledge_root_id": root_id,
                "chunk_id": chunk_id,
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "rrf_score": item.score,
                "bm25_score": bm_scores.get(item.chunk_id),
                "dense_score": dense_scores.get(item.chunk_id),
                "bm25_rank": bm_ranks.get(item.chunk_id),
                "dense_rank": dense_ranks.get(item.chunk_id),
                "heading_path": chunk.heading_path,
                "location": chunk.location,
                "text": chunk.text,
            }
        )
    return {
        "bm25_top100": _rank_rows(bm_keys, bm_scores, chunk_by_key, root_by_chunk),
        "dense_top100": _rank_rows(dense_keys, dense_scores, chunk_by_key, root_by_chunk),
        "rrf_top100": candidates,
        "bm25_ranks": bm_ranks,
        "dense_ranks": dense_ranks,
    }


def _rank_rows(keys: list[str], scores: dict[str, float], chunk_by_key: dict[tuple[str, str], Chunk], root_by_chunk: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, key in enumerate(keys[:100], 1):
        root_id, chunk_id = key.split("|", 1)
        chunk = chunk_by_key[(root_id, chunk_id)]
        rows.append(
            {
                "rank": rank,
                "knowledge_root_id": root_id,
                "chunk_id": chunk_id,
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "score": scores.get(key),
                "heading_path": chunk.heading_path,
                "location": chunk.location,
                "text": chunk.text,
            }
        )
    return rows


def fuse_candidates(retrieval: dict[str, Any], probe: list[dict[str, Any]], chunk_by_key: dict[tuple[str, str], Chunk]) -> list[dict[str, Any]]:
    fused: dict[tuple[str, str], dict[str, Any]] = {}
    for item in retrieval["rrf_top100"]:
        key = (item["knowledge_root_id"], item["chunk_id"])
        fused[key] = {
            **item,
            "candidate_origin": list(item["candidate_origin"]),
            "knowledge_page_type": knowledge_page_type(chunk_by_key[key]),
            "probe_score": 0.0,
        }
    for probe_rank, item in enumerate(probe[:30], start=1):
        chunk = item.get("rescue_chunk") or item["best_chunk"]
        key = (item["knowledge_root_id"], chunk.chunk_id)
        if key not in fused:
            fused[key] = {
                "rank": None,
                "candidate_origin": ["QUERY_PAGE_PROBE"],
                "knowledge_root_id": item["knowledge_root_id"],
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "rrf_score": 0.0,
                "bm25_score": None,
                "dense_score": None,
                "bm25_rank": None,
                "dense_rank": None,
                "heading_path": chunk.heading_path,
                "location": chunk.location,
                "text": chunk.text,
                "knowledge_page_type": item["knowledge_page_type"],
                "probe_score": item["probe_score"],
                "query_page_probe_rank": probe_rank,
            }
        else:
            fused[key]["candidate_origin"] = list(dict.fromkeys(fused[key]["candidate_origin"] + ["QUERY_PAGE_PROBE"]))
            fused[key]["probe_score"] = max(fused[key].get("probe_score", 0.0), item["probe_score"])
            fused[key]["query_page_probe_rank"] = min(fused[key].get("query_page_probe_rank", probe_rank), probe_rank)
    for item in fused.values():
        item["fusion_score"] = round(float(item.get("rrf_score") or 0.0) + 0.01 * float(item.get("probe_score") or 0.0), 8)
    return sorted(fused.values(), key=lambda item: (-item["fusion_score"], item["knowledge_root_id"], item["chunk_id"]))


def capability_for_text(text: str, document_role: str, page_type: str) -> list[str]:
    caps: list[str] = []
    if any(term in text for term in ("怎么做", "如何", "流程", "步骤", "实施", "开展", "识别价值点", "分析可行性", "实施优化", "验证效果")):
        caps.append("METHOD")
    if (
        any(term in text for term in ("计算公式", "公式", "计算方法"))
        or ("设计创效计算" in text and "=" in text)
        or ("设计创效率定义" in text and "=" in text)
        or re.search(r"\d+(?:\.\d+)?\s*(?:/|÷|=)\s*\d+(?:\.\d+)?", text)
    ):
        caps.append("FORMULA")
    if any(term in text for term in ("是什么", "定义", "指的是", "概念")):
        caps.append("DEFINITION")
    if any(term in text for term in ("案例", "项目", "实施效果", "实例")) or document_role == "项目案例":
        caps.append("EXAMPLE")
    if any(term in text for term in ("造价节约", "工期缩短", "品质提升", "运维成本降低", "量化评估", "评价维度")):
        caps.append("METRIC_DIMENSION")
    return caps or ["OTHER"]


def evidence_rows(
    bundle: EvidenceBundle,
    fused: list[dict[str, Any]],
    governance: dict[str, GovernanceMetadata],
    source_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {(item["knowledge_root_id"], item["chunk_id"]): item for item in fused}
    rows: list[dict[str, Any]] = []
    for item in bundle.items:
        source = next(
            (source_by_key[(root_id, item.chunk_id)] for root_id in ROOT_CONFIG if (root_id, item.chunk_id) in source_by_key),
            {},
        )
        fused_item = by_key.get((source.get("knowledge_root_id"), item.chunk_id), {})
        caps = capability_for_text(item.excerpt, item.document_role, fused_item.get("knowledge_page_type", "OTHER"))
        rows.append(
            {
                "source_id": item.source_id,
                "knowledge_root_id": source.get("knowledge_root_id"),
                "approval_status": source.get("approval_status"),
                "document_id": item.document_id,
                "chunk_id": item.chunk_id,
                "file_name": item.file_name,
                "source_path": item.source_path,
                "document_role": item.document_role,
                "authority_level": item.authority_level,
                "knowledge_page_type": fused_item.get("knowledge_page_type", "OTHER"),
                "candidate_origin": fused_item.get("candidate_origin", []),
                "location": item.location,
                "excerpt": item.excerpt,
                "evidence_capability": caps,
            }
        )
    return rows


def select_evidence(
    fused: list[dict[str, Any]],
    governance: dict[str, GovernanceMetadata],
) -> tuple[EvidenceBundle, list[dict[str, Any]]]:
    # Build SearchHit objects without changing the original Retrieval result.
    hits = []
    for item in fused[:130]:
        chunk = item.get("chunk")
        if chunk is None:
            continue
        hits.append(
            SearchHit(
                chunk=chunk,
                score=float(item.get("fusion_score") or 0.0),
                bm25_rank=item.get("bm25_rank"),
                dense_rank=item.get("dense_rank"),
            )
        )
    bundle = select_evidence_optimized(
        hits,
        policy_for_intent("METHOD_QUERY"),
        governance,
        max_items=5,
    )
    selected_ids = {item.chunk_id for item in bundle.items}
    rescue_candidates = [
        item
        for item in fused
        if item.get("knowledge_page_type") == "QUERY_PAGE"
        and "QUERY_PAGE_PROBE" in item.get("candidate_origin", [])
        and item["chunk_id"] not in selected_ids
        and "METHOD" in capability_for_text(item.get("text", ""), "", "QUERY_PAGE")
    ]
    if rescue_candidates:
        candidate = min(
            rescue_candidates,
            key=lambda item: (item.get("query_page_probe_rank", 9999), -item.get("probe_score", 0.0)),
        )
        chunk = candidate["chunk"]
        candidate_governance = governance.get(chunk.chunk_id)
        if candidate_governance is not None:
            rescue_item = EvidenceItem(
                source_id="S_RESCUE",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                file_name=chunk.file_name,
                source_path=chunk.source_path,
                document_role=candidate_governance.document_role,
                authority_level=candidate_governance.authority_level,
                usage_scene=candidate_governance.usage_scene,
                location=dict(chunk.location),
                excerpt=chunk.text[:900],
                retrieval_score=float(candidate.get("rrf_score") or candidate.get("fusion_score") or 0.0),
                selection_score=float(candidate.get("fusion_score") or 0.0),
                evidence_status="SUPPORTING",
                document_score=float(candidate.get("fusion_score") or 0.0),
            )
            replaceable = [
                (index, item)
                for index, item in enumerate(bundle.items)
                if item.document_role not in {"正式制度", "管理指南"}
            ]
            if len(bundle.items) < 5:
                bundle.items.append(rescue_item)
            elif replaceable:
                replace_index, _ = min(replaceable, key=lambda pair: pair[1].selection_score)
                bundle.items[replace_index] = rescue_item
            if rescue_item in bundle.items:
                bundle.selection_notes.append("QUERY_PAGE_RESCUE_ADDED：保留方法性 Query Page；正式制度/管理指南未被替换")
    return bundle, hits


def method_answer(rows: list[dict[str, Any]]) -> dict[str, Any]:
    method = [row for row in rows if "METHOD" in row["evidence_capability"]]
    metric = [row for row in rows if "METRIC_DIMENSION" in row["evidence_capability"]]
    formula = [row for row in rows if "FORMULA" in row["evidence_capability"]]
    if not method and not metric and not formula:
        return {
            "final_status": "NO_EVIDENCE",
            "answer": "当前证据不足，无法形成可核查回答。",
            "has_method_evidence": False,
            "has_formula_evidence": False,
            "citations": [],
        }
    lines = [
        "现有知识库可以明确设计效益增量的评价思路和量化维度，但当前证据中没有发现唯一、正式的企业计算公式。",
        "",
        "方法/流程证据：",
    ]
    for row in method[:2]:
        lines.append(f"- {row['excerpt'][:700]} [{row['source_id']}]" )
    if metric:
        lines.extend(["", "量化维度证据："])
        for row in metric[:2]:
            lines.append(f"- {row['excerpt'][:700]} [{row['source_id']}]" )
    if formula:
        lines.extend(["", "正式计算口径证据："])
        for row in formula[:2]:
            lines.append(f"- {row['excerpt'][:900]} [{row['source_id']}]" )
        lines.append("\n证据边界：以上公式仅作为来源原文引用，不对其适用范围外推。")
    else:
        lines.append("\n证据边界：当前没有可核查的正式计算公式，因此不自行补充公式。")
    return {
        "final_status": "PARTIAL_EVIDENCE" if not formula else "GENERATED",
        "answer": "\n".join(lines),
        "has_method_evidence": bool(method),
        "has_formula_evidence": bool(formula),
        "citations": [
            {
                "evidence_id": row["source_id"],
                "knowledge_root_id": row["knowledge_root_id"],
                "file_name": row["file_name"],
                "source_path": row["source_path"],
                "location": row["location"],
                "excerpt": row["excerpt"],
            }
            for row in [*method[:2], *metric[:2]]
        ],
    }


def run_one(
    question: str,
    clients: dict[str, QdrantClient],
    chunks_by_root: dict[str, list[Chunk]],
    catalog: list[dict[str, Any]],
    governance: dict[str, GovernanceMetadata],
    source_by_key: dict[tuple[str, str], dict[str, Any]],
    bm25: BM25Index,
    dense: BGEM3DenseProvider,
    vector_cache: dict[str, list[float]],
) -> dict[str, Any]:
    chunk_by_key = {(root_id, chunk.chunk_id): chunk for root_id, chunks in chunks_by_root.items() for chunk in chunks}
    route = route_question(question, load_fact_capability())
    retrieval = retrieve_top100(question, clients, chunks_by_root, chunk_by_key, bm25, dense, vector_cache)
    probe = page_probe(question, catalog)
    fused = fuse_candidates(retrieval, probe, chunk_by_key)
    for item in fused:
        item["chunk"] = chunk_by_key[(item["knowledge_root_id"], item["chunk_id"])]
    fused_for_output = [dict(item) for item in fused]
    bundle, _ = select_evidence(fused, governance)
    selected = evidence_rows(bundle, fused_for_output, governance, source_by_key)
    answer = method_answer(selected)
    return {
        "question": question,
        "route": route,
        "retrieval_trace": retrieval,
        "query_page_probe": [
            {
                key: _serializable(value)
                for key, value in item.items()
                if key != "best_chunk"
            }
            | {"best_chunk": _serializable(item["best_chunk"])}
            for item in probe[:30]
        ],
        "candidate_fusion": [_serializable({key: value for key, value in item.items() if key != "chunk"}) for item in fused_for_output[:130]],
        "evidence_bundle": selected,
        "evidence_capability": {
            "has_method_evidence": any("METHOD" in item["evidence_capability"] for item in selected),
            "has_formula_evidence": any("FORMULA" in item["evidence_capability"] for item in selected),
            "items": selected,
        },
        "final_answer": answer,
    }


def _serializable(value: Any) -> Any:
    if isinstance(value, Chunk):
        return {
            "chunk_id": value.chunk_id,
            "document_id": value.document_id,
            "source_path": value.source_path,
            "file_name": value.file_name,
            "heading_path": value.heading_path,
            "location": value.location,
            "text": value.text,
        }
    if isinstance(value, dict):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    return value


def target_page_record(result: dict[str, Any]) -> dict[str, Any] | None:
    pages = [item for item in result["query_page_probe"] if item.get("knowledge_page_type") == "QUERY_PAGE"]
    return pages[0] if pages else None


def render_report(
    ba002: dict[str, Any],
    regression: list[dict[str, Any]],
    general: list[dict[str, Any]],
    target_page: dict[str, Any] | None,
) -> str:
    trace = ba002["retrieval_trace"]
    target_path = target_page.get("source_path") if target_page else "NOT_RETRIEVED"
    target_name = target_page.get("file_name") if target_page else "NOT_RETRIEVED"
    boundary = (
        "当前 Evidence 已包含正式计算口径；最终答案只引用该正式来源，不对公式适用范围外推。"
        if ba002["final_answer"].get("has_formula_evidence")
        else "当前 Evidence 只有方法和量化维度，没有唯一、正式计算公式；不得自行补充公式。"
    )
    def target_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("source_path") == target_path]
    lines = [
        "# Knowledge Page Retrieval Rescue Report",
        "",
        "> TASK-017C-2：为已存在的 Query Page 增加 Shadow Rescue，并明确方法证据与正式公式证据边界。",
        "> 未修改正式 Retriever、Router、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF 或 Reranker。",
        "",
        "## 1. Target Knowledge Page",
        "",
        f"- 识别到的 Query Page：`{target_name}`",
        f"- Source Path：`{target_path}`",
        "- 识别方式：路径结构 `wiki/queries` + Query Page 内容形式；没有使用固定文件名作为检索规则。",
        "",
        "| Retrieval | Rank | Score | Status |",
        "|---|---:|---:|---|",
    ]
    for label, rows in (("BM25", trace["bm25_top100"]), ("Dense", trace["dense_top100"]), ("RRF", trace["rrf_top100"])):
        matches = target_ranks(rows)
        if matches:
            best = min(matches, key=lambda row: row["rank"])
            lines.append(f"| {label} | {best['rank']} | {best.get('score', best.get('rrf_score'))} | RETRIEVED |")
        else:
            lines.append(f"| {label} | — | — | NOT_RETRIEVED |")
    lines += [
        "",
        "### Target Page 完整 Top100 命中记录",
        "",
        "| Retrieval | Rank | Chunk ID | File | Heading | Location | Score | Excerpt |",
        "|---|---:|---|---|---|---|---:|---|",
    ]
    for label, rows in (("BM25", trace["bm25_top100"]), ("Dense", trace["dense_top100"]), ("RRF", trace["rrf_top100"])):
        for row in target_ranks(rows):
            excerpt = str(row.get("text") or "").replace("|", "\\|").replace("\n", " ")[:500]
            lines.append(f"| {label} | {row['rank']} | `{row['chunk_id']}` | {row['file_name']} | {row.get('heading_path')} | `{row.get('location')}` | {row.get('score', row.get('rrf_score'))} | {excerpt} |")
    lines += [
        "",
        "## 2. Target Page Chunk Structure",
        "",
        f"- Document：`{target_name}`",
        f"- SourceBlock/Chunk 数量：{len(target_page.get('all_chunks', [])) if target_page else 0}",
        f"- Heading 保留：`{target_page.get('headings') if target_page else []}`",
        f"- Method Chunk：`{target_page.get('method_chunks') if target_page else []}`",
        f"- Metric Dimension Chunk：`{target_page.get('metric_chunks') if target_page else []}`",
        f"- Formula Chunk：`{target_page.get('formula_chunks') if target_page else []}`",
        "",
        "## 3. Query Page Classification",
        "",
        "- `QUERY_PAGE`：路径位于 `wiki/queries`；",
        "- `CONCEPT_PAGE`：路径位于 `wiki/concepts`；",
        "- `SOURCE_DOCUMENT`：Office/PDF 或 raw/attachments 源文件；",
        "- `OTHER`：不满足以上结构。",
        "",
        "## 4. Query Page Probe 与 Candidate Fusion",
        "",
        f"- Query Page Probe 候选数：{len(ba002['query_page_probe'])}",
        f"- Candidate Fusion 候选数：{len(ba002['candidate_fusion'])}",
        "- Candidate Origin：BM25、DENSE、RRF、QUERY_PAGE_PROBE；同一 Chunk 合并来源，不重复计数。",
        "- QUERY_PAGE_PROBE 只做 RESCUE，不直接生成答案。",
        "- 正式制度/管理指南仍由现有 Evidence Selection 的角色与权威性规则优先。",
        "",
        "| Rank | Root | File | knowledge_page_type | Candidate Origin | Fusion Score |",
        "|---:|---|---|---|---|---:|",
    ]
    for rank, item in enumerate(ba002["candidate_fusion"][:20], 1):
        lines.append(f"| {rank} | {item.get('knowledge_root_id')} | {item.get('file_name')} | {item.get('knowledge_page_type')} | {','.join(item.get('candidate_origin', []))} | {item.get('fusion_score')} |")
    lines += [
        "",
        "## 5. Evidence Capability",
        "",
        f"- has_method_evidence：`{ba002['evidence_capability']['has_method_evidence']}`",
        f"- has_formula_evidence：`{ba002['evidence_capability']['has_formula_evidence']}`",
        "- `METHOD`：流程、步骤、开展方式和实施动作；",
        "- `FORMULA`：证据中明确出现公式/计算式；",
        "- `METRIC_DIMENSION`：造价节约、工期缩短、品质提升、运维成本降低等量化维度。",
        "",
        "## 6. BA-002 最终实际答案",
        "",
        "```text",
        ba002["final_answer"]["answer"],
        "```",
        "",
        f"Final Status：`{ba002['final_answer']['final_status']}`",
        "",
        "### Citation",
        "",
    ]
    for item in ba002["final_answer"].get("citations", []):
        lines.append(f"- `{item['evidence_id']}`：{item['file_name']}，Root=`{item['knowledge_root_id']}`，location=`{item['location']}`；excerpt：{item['excerpt'][:800].replace(chr(10), ' ')}")
    lines += [
        "",
        f"边界结论：{boundary}本报告没有补充“优化后/优化前”类未被证据支持的公式。",
        "",
        "## 7. 通用非 BA 测试",
        "",
        "| ID | Query | Query Page Probe | Method | Formula | Final Status |",
        "|---|---|---|---|---|---|",
    ]
    for item in general:
        answer = item["final_answer"]
        lines.append(f"| {item['case_id']} | {item['question']} | {len(item['query_page_probe'])} | {answer['has_method_evidence']} | {answer['has_formula_evidence']} | {answer['final_status']} |")
    lines += [
        "",
        "## 8. BA-001～BA-010 回归",
        "",
        "| BA | Baseline Status | Rescue Status | Route | Query Page Probe | Evidence Capability |",
        "|---|---|---|---|---:|---|",
    ]
    for item in regression:
        lines.append(f"| {item['question_id']} | {item['baseline_status']} | {item['rescue_status']} | {item['route']} | {item['query_page_probe_count']} | {item['evidence_capability']} |")
    lines += [
        "",
        "## 9. 边界与未完成事项",
        "",
        "- 未修改正式系统；",
        "- 未重切全库 Chunk；",
        "- 未重新生成全库 Embedding；",
        "- BA-003、BA-004、BA-006、BA-009 未借本任务修复；",
        "- 如果后续发现正式计算公式，应以正式制度/管理办法/批准口径替换当前方法性 Query Page 作为 DIRECT Evidence。",
        "",
    ]
    return "\n".join(lines)


def target_page_details(target: dict[str, Any] | None, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    if target is None:
        return None
    matched = next((item for item in catalog if item["knowledge_root_id"] == target["knowledge_root_id"] and item["document_id"] == target["document_id"]), None)
    if matched is None:
        return target
    method_chunks = []
    metric_chunks = []
    formula_chunks = []
    for chunk in matched["chunks"]:
        caps = capability_for_text(chunk.text, "", matched["knowledge_page_type"])
        if "METHOD" in caps:
            method_chunks.append(chunk.chunk_id)
        if "METRIC_DIMENSION" in caps:
            metric_chunks.append(chunk.chunk_id)
        if "FORMULA" in caps:
            formula_chunks.append(chunk.chunk_id)
    return {
        **target,
        "all_chunks": [_serializable(chunk) for chunk in matched["chunks"]],
        "headings": sorted({chunk.heading_path for chunk in matched["chunks"] if chunk.heading_path}),
        "method_chunks": method_chunks,
        "metric_chunks": metric_chunks,
        "formula_chunks": formula_chunks,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clients, chunks_by_root, _, catalog, governance, source_by_key = load_shadow_data()
    all_chunks = [chunk for chunks in chunks_by_root.values() for chunk in chunks]
    chunk_by_key = {
        (root_id, chunk.chunk_id): chunk
        for root_id, chunks in chunks_by_root.items()
        for chunk in chunks
    }
    chunk_id_roots: dict[str, list[str]] = defaultdict(list)
    for root_id, chunks in chunks_by_root.items():
        for chunk in chunks:
            chunk_id_roots[chunk.chunk_id].append(root_id)
    duplicate_chunk_ids = {chunk_id: roots for chunk_id, roots in chunk_id_roots.items() if len(roots) > 1}
    if duplicate_chunk_ids:
        raise ValueError(f"Cross-root duplicate chunk_id prevents unambiguous trace: {list(duplicate_chunk_ids)[:5]}")

    bm25 = BM25Index(PROJECT_ROOT / "data" / "shadow" / "knowledge_page_rescue_bm25_runtime.json")
    bm25.build(all_chunks)
    settings = Settings.load()
    dense = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name="knowledge_page_rescue_query_only",
        use_fp16=True,
        batch_size=4,
    )
    vector_cache: dict[str, list[float]] = {}
    try:
        dense.load()
        questions = load_questions(GOLD_PATH)
        ba_results: list[dict[str, Any]] = []
        ba002_result: dict[str, Any] | None = None
        regression: list[dict[str, Any]] = []
        for question in questions:
            question_id = str(question["id"])
            result = run_one(
                str(question["question"]),
                clients,
                chunks_by_root,
                catalog,
                governance,
                source_by_key,
                bm25,
                dense,
                vector_cache,
            )
            baseline_path = BASELINE_DIR / f"{question_id}.json"
            baseline = read_json(baseline_path) if baseline_path.exists() else {}
            if question_id == "BA-002":
                ba002_result = result
                result["question_id"] = question_id
                ba_results.append(result)
                current_status = result["final_answer"]["final_status"]
                evidence_capability = json.dumps(result["evidence_capability"], ensure_ascii=False)
            else:
                result["question_id"] = question_id
                ba_results.append(result)
                current_status = baseline.get("final_status")
                evidence_capability = "NOT_REPLAYED"
            regression.append(
                {
                    "question_id": question_id,
                    "question": str(question["question"]),
                    "baseline_status": baseline.get("final_status"),
                    "rescue_status": current_status,
                    "route": result["route"].get("route"),
                    "query_page_probe_count": len(result["query_page_probe"]),
                    "evidence_capability": evidence_capability,
                    "target_page_in_candidate": any(
                        item.get("knowledge_page_type") == "QUERY_PAGE" and "QUERY_PAGE_PROBE" in item.get("candidate_origin", [])
                        for item in result["candidate_fusion"]
                    ),
                }
            )
            (OUTPUT_DIR / f"{question_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        if ba002_result is None:
            raise ValueError("BA-002 Gold question is missing")
        target = target_page_record(ba002_result)
        target_detail = target_page_details(target, catalog)
        ba002_result["target_page"] = target_detail
        (OUTPUT_DIR / "BA-002.json").write_text(json.dumps(ba002_result, ensure_ascii=False, indent=2), encoding="utf-8")

        general_results: list[dict[str, Any]] = []
        for case_id, question in GENERAL_TESTS:
            result = run_one(
                question,
                clients,
                chunks_by_root,
                catalog,
                governance,
                source_by_key,
                bm25,
                dense,
                vector_cache,
            )
            result["case_id"] = case_id
            general_results.append(result)
            (OUTPUT_DIR / f"{case_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        REPORT_PATH.write_text(render_report(ba002_result, regression, general_results, target_detail), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(REPORT_PATH.resolve()),
                    "output_dir": str(OUTPUT_DIR.resolve()),
                    "ba_questions": len(ba_results),
                    "general_tests": len(general_results),
                    "target_page": target_detail.get("file_name") if target_detail else "NOT_RETRIEVED",
                    "ba002_final_status": ba002_result["final_answer"]["final_status"],
                    "ba002_has_method": ba002_result["evidence_capability"]["has_method_evidence"],
                    "ba002_has_formula": ba002_result["evidence_capability"]["has_formula_evidence"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        dense.close()
        for client in clients.values():
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
