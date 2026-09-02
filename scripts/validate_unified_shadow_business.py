from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import torch
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, select_evidence_optimized
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.bm25 import BM25Index
from app.config import Settings
from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceClassifier, GovernanceMetadata
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.rrf import reciprocal_rank_fusion
from scripts.evaluate_business_query_regression import load_questions
from scripts.shadow_answer_router_v1_1 import route_question


ROOT_CONFIG = {
    "Root-001": {
        "shadow_dir": PROJECT_ROOT / "data" / "shadow" / "full_corpus_qdrant",
        "collection": "full_corpus_shadow_bge_m3",
        "source_root": r"D:\设计管理",
        "approval_status": "BASELINE_SHADOW_APPROVED",
    },
    "Root-002": {
        "shadow_dir": PROJECT_ROOT / "data" / "shadow" / "root002_import" / "qdrant",
        "collection": "root002_shadow_bge_m3",
        "source_root": r"D:\工作\二公司技术部",
        "approval_status": "ROOT002_SELECTIVELY_APPROVED_SHADOW",
    },
}

GOLD_PATH = PROJECT_ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
FACT_ANSWER_PATH = PROJECT_ROOT / "evaluation" / "fact_answers" / "BA-010.json"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "v1_business_acceptance"
REPORT_PATH = PROJECT_ROOT / "docs" / "V1_0_UNIFIED_SHADOW_BUSINESS_VALIDATION.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_qdrant_chunks(
    client: QdrantClient, collection: str, root_id: str
) -> tuple[list[Chunk], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    chunks: list[Chunk] = []
    metadata_by_chunk: dict[str, dict[str, Any]] = {}
    source_by_chunk: dict[str, dict[str, Any]] = {}
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for ordinal, point in enumerate(points, start=len(chunks)):
            payload = point.payload or {}
            chunk_id = str(payload.get("chunk_id") or point.id)
            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=str(payload.get("document_id") or ""),
                ordinal=ordinal,
                source_path=str(payload.get("source_path") or ""),
                file_name=str(payload.get("file_name") or ""),
                text=str(payload.get("text") or ""),
                heading_path=str(payload.get("heading_path") or ""),
                location=dict(payload.get("location") or {}),
            )
            chunks.append(chunk)
            metadata_by_chunk[chunk_id] = dict(payload.get("metadata") or {})
            source_by_chunk[chunk_id] = {
                "knowledge_root_id": root_id,
                "source_path": chunk.source_path,
                "file_name": chunk.file_name,
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "approval_status": ROOT_CONFIG[root_id]["approval_status"],
                "source_root": ROOT_CONFIG[root_id]["source_root"],
                "collection": collection,
            }
        if offset is None:
            break
    return chunks, metadata_by_chunk, source_by_chunk


class ShadowCollectionDenseSearch:
    def __init__(
        self,
        provider: Any,
        client: QdrantClient,
        collection: str,
        vector_cache: dict[str, list[float]],
    ) -> None:
        self.provider = provider
        self.client = client
        self.collection = collection
        self.vector_cache = vector_cache

    def search(self, question: str, limit: int) -> list[tuple[str, float]]:
        vector = self.vector_cache.get(question)
        if vector is None:
            vector = self.provider.embed_query(question)
            self.vector_cache[question] = vector
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            (str((point.payload or {}).get("chunk_id") or point.id), float(point.score))
            for point in response.points
        ]


def combined_search(
    question: str,
    root_retrievers: dict[str, HybridRetriever],
    chunks_by_root: dict[str, list[Chunk]],
    source_by_chunk: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[SearchHit], dict[str, Any], dict[str, list[SearchHit]], set[tuple[str, str]]]:
    root_results: dict[str, Any] = {}
    ranked_lists: dict[str, list[str]] = {}
    hit_lookup: dict[str, SearchHit] = {}
    for root_id in ROOT_CONFIG:
        result = root_retrievers[root_id].search(
            question,
            bm25_limit=20,
            dense_limit=20,
            rerank_limit=20,
            final_limit=20,
        )
        root_results[root_id] = result
        keys: list[str] = []
        for hit in result.hits:
            key = f"{root_id}|{hit.chunk.chunk_id}"
            keys.append(key)
            hit_lookup[key] = hit
        ranked_lists[root_id] = keys

    lineage_pairs = find_lineage_pairs(root_results, source_by_chunk)
    lineage_body_keys = {f"Root-002|{target}" for _, target in lineage_pairs}
    lineage_registration_keys = {f"Root-001|{source}" for source, _ in lineage_pairs}
    fused = reciprocal_rank_fusion(ranked_lists)
    ordered: list[tuple[float, int, str]] = []
    for ordinal, candidate in enumerate(fused):
        key = candidate.chunk_id
        score = candidate.score
        # Shadow-only soft preference: linked approved body text outranks its
        # Root-001 registration page, while both remain in the trace.
        if key in lineage_body_keys:
            score += 0.01
        if key in lineage_registration_keys:
            score -= 0.005
        ordered.append((score, ordinal, key))
    ordered.sort(key=lambda item: (-item[0], item[1], item[2]))

    global_hits: list[SearchHit] = []
    root_hits: dict[str, list[SearchHit]] = {root_id: root_results[root_id].hits for root_id in ROOT_CONFIG}
    for score, _, key in ordered:
        hit = hit_lookup[key]
        global_hits.append(
            SearchHit(
                chunk=hit.chunk,
                score=float(score),
                bm25_rank=hit.bm25_rank,
                dense_rank=hit.dense_rank,
                reranker_score=None,
            )
        )
    debug = {
        "roots_searched": list(ROOT_CONFIG),
        "candidate_count_by_root": {
            root_id: {
                "bm25": int(root_results[root_id].debug.get("bm25_hits", 0)),
                "dense": int(root_results[root_id].debug.get("dense_hits", 0)),
                "hybrid": int(root_results[root_id].debug.get("fused_hits", 0)),
                "top_candidates": len(root_results[root_id].hits),
            }
            for root_id in ROOT_CONFIG
        },
        "federated_candidates": len(global_hits),
        "reranker_used": False,
        "metadata_filter_used": False,
        "lineage_pairs_in_candidates": [
            {"root001_chunk_id": source, "root002_chunk_id": target}
            for source, target in sorted(lineage_pairs)
        ],
    }
    return global_hits, debug, root_hits, lineage_pairs


def find_lineage_pairs(
    root_results: dict[str, Any],
    source_by_chunk: dict[tuple[str, str], dict[str, Any]],
) -> set[tuple[str, str]]:
    root1_hits = root_results["Root-001"].hits
    root2_hits = root_results["Root-002"].hits
    by_name: dict[str, list[str]] = defaultdict(list)
    for hit in root2_hits:
        name = hit.chunk.file_name.casefold()
        if name:
            by_name[name].append(hit.chunk.chunk_id)
    pairs: set[tuple[str, str]] = set()
    for hit in root1_hits:
        text = hit.chunk.text
        if "file:///" not in text and "raw/" not in text and "[[" not in text:
            continue
        for file_name, target_ids in by_name.items():
            if file_name in text.casefold():
                pairs.update((hit.chunk.chunk_id, target_id) for target_id in target_ids)
    return pairs


def classify_governance(
    chunks_by_root: dict[str, list[Chunk]],
    metadata_by_root: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, GovernanceMetadata]:
    classifier = GovernanceClassifier()
    result: dict[str, GovernanceMetadata] = {}
    for chunks in chunks_by_root.values():
        for chunk in chunks:
            result[chunk.chunk_id] = classifier.classify(
                file_name=chunk.file_name,
                source_path=chunk.source_path,
                heading_path=chunk.heading_path,
                text=chunk.text,
                metadata=metadata_by_root.get("Root-001", {}).get(chunk.chunk_id)
                or metadata_by_root.get("Root-002", {}).get(chunk.chunk_id)
                or {},
            )
    return result


def evidence_dict(
    bundle: EvidenceBundle,
    source_by_chunk: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in bundle.items:
        matches = [
            source_by_chunk[(root_id, item.chunk_id)]
            for root_id in ROOT_CONFIG
            if (root_id, item.chunk_id) in source_by_chunk
        ]
        source = matches[0] if matches else {}
        rows.append(
            {
                "source_id": item.source_id,
                "knowledge_root_id": source.get("knowledge_root_id"),
                "approval_status": source.get("approval_status"),
                "source_path": item.source_path,
                "file_name": item.file_name,
                "document_id": item.document_id,
                "chunk_id": item.chunk_id,
                "document_role": item.document_role,
                "authority_level": item.authority_level,
                "location": item.location,
                "retrieval_score": item.retrieval_score,
                "selection_score": item.selection_score,
                "excerpt": item.excerpt,
            }
        )
    return rows


def citation_rows_from_claims(
    claims: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(item["source_id"]): item for item in evidence}
    rows: list[dict[str, Any]] = []
    for claim in claims:
        for evidence_id in claim.get("evidence_ids", []):
            item = by_id.get(str(evidence_id))
            if item is None:
                continue
            rows.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "evidence_id": evidence_id,
                    "knowledge_root_id": item.get("knowledge_root_id"),
                    "file_name": item.get("file_name"),
                    "source_path": item.get("source_path"),
                    "chunk_id": item.get("chunk_id"),
                    "location": item.get("location"),
                    "excerpt": item.get("excerpt"),
                }
            )
    return rows


def serialize_candidates(
    hits: list[SearchHit],
    source_by_chunk: dict[tuple[str, str], dict[str, Any]],
    governance_by_chunk: dict[str, GovernanceMetadata],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, hit in enumerate(hits[:20], start=1):
        matches = [
            source_by_chunk[(root_id, hit.chunk.chunk_id)]
            for root_id in ROOT_CONFIG
            if (root_id, hit.chunk.chunk_id) in source_by_chunk
        ]
        source = matches[0] if matches else {}
        governance = governance_by_chunk.get(hit.chunk.chunk_id)
        rows.append(
            {
                "rank": rank,
                "knowledge_root_id": source.get("knowledge_root_id"),
                "approval_status": source.get("approval_status"),
                "chunk_id": hit.chunk.chunk_id,
                "document_id": hit.chunk.document_id,
                "file_name": hit.chunk.file_name,
                "source_path": hit.chunk.source_path,
                "document_role": governance.document_role if governance else "其他",
                "authority_level": governance.authority_level if governance else "UNKNOWN",
                "score": hit.score,
                "bm25_rank": hit.bm25_rank,
                "dense_rank": hit.dense_rank,
                "location": hit.chunk.location,
                "excerpt": hit.chunk.text[:900],
            }
        )
    return rows


def load_fact_answer() -> dict[str, Any]:
    payload = read_json(FACT_ANSWER_PATH)
    if payload.get("validation_result", {}).get("valid") is not True:
        raise ValueError("Frozen BA-010 fact answer validation is not valid")
    if payload.get("citation_result", {}).get("valid") is not True:
        raise ValueError("Frozen BA-010 citation validation is not valid")
    aggregation = payload.get("fact_aggregation", {})
    if (
        aggregation.get("total_rows") != 80
        or aggregation.get("increase_effect_count") != 37
        or aggregation.get("undetermined_profit_count") != 43
    ):
        raise ValueError("Frozen BA-010 fact result does not match 80/37/43")
    return payload


def run() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = Settings.load()
    questions = load_questions(GOLD_PATH)
    if {str(item.get("id")) for item in questions} != {f"BA-{index:03d}" for index in range(1, 11)}:
        raise ValueError("Gold Dataset 必须完整包含 BA-001 至 BA-010")
    fact_answer = load_fact_answer()

    clients: dict[str, QdrantClient] = {}
    chunks_by_root: dict[str, list[Chunk]] = {}
    metadata_by_root: dict[str, dict[str, dict[str, Any]]] = {}
    source_by_chunk: dict[tuple[str, str], dict[str, Any]] = {}
    collection_points: dict[str, int] = {}
    for root_id, config in ROOT_CONFIG.items():
        client = QdrantClient(path=str(config["shadow_dir"]))
        if not client.collection_exists(config["collection"]):
            raise FileNotFoundError(f"Shadow collection not found: {root_id}/{config['collection']}")
        clients[root_id] = client
        chunks, metadata, source = load_qdrant_chunks(client, config["collection"], root_id)
        chunks_by_root[root_id] = chunks
        metadata_by_root[root_id] = metadata
        collection_points[root_id] = len(chunks)
        for chunk_id, item in source.items():
            source_by_chunk[(root_id, chunk_id)] = item

    collisions = len(
        set(chunk.chunk_id for chunk in chunks_by_root["Root-001"])
        & set(chunk.chunk_id for chunk in chunks_by_root["Root-002"])
    )
    governance_by_chunk = classify_governance(chunks_by_root, metadata_by_root)
    bm25_by_root: dict[str, BM25Index] = {}
    for root_id, chunks in chunks_by_root.items():
        index = BM25Index(PROJECT_ROOT / "data" / "shadow" / f"unified_{root_id.casefold().replace('-', '')}_bm25_runtime.json")
        index.build(chunks)
        bm25_by_root[root_id] = index

    from app.retrieval.dense_provider import BGEM3DenseProvider

    dense_provider = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name="unified_shadow_query_only",
        use_fp16=True,
        batch_size=4,
    )
    vector_cache: dict[str, list[float]] = {}
    root_retrievers: dict[str, HybridRetriever] = {}
    for root_id, config in ROOT_CONFIG.items():
        dense = ShadowCollectionDenseSearch(
            dense_provider,
            clients[root_id],
            config["collection"],
            vector_cache,
        )
        root_retrievers[root_id] = HybridRetriever(
            bm25_by_root[root_id], chunks_by_root[root_id], dense=dense
        )

    provider = OpenAICompatibleProvider(settings)
    generator = ShadowAnswerGenerator(provider)
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        dense_provider.load()
        for ordinal, question in enumerate(questions, start=1):
            question_id = str(question["id"])
            text = str(question["question"])
            route = route_question(text, load_fact_capability_for_router())
            hits, retrieval_debug, _, _ = combined_search(
                text, root_retrievers, chunks_by_root, source_by_chunk
            )
            policy = policy_for_intent(route["intent"])
            governance_for_hits = {
                hit.chunk.chunk_id: governance_by_chunk[hit.chunk.chunk_id]
                for hit in hits
                if hit.chunk.chunk_id in governance_by_chunk
            }
            bundle = select_evidence_optimized(
                hits,
                policy,
                governance_for_hits,
                max_items=5,
            )
            selected_evidence = evidence_dict(bundle, source_by_chunk)
            final_status: str
            answer: str
            citations: list[dict[str, Any]]
            answer_payload: dict[str, Any] = {}
            answer_failure: dict[str, Any] | None = None
            if question_id == "BA-010" and route["route"] == "FACT_ANSWER_PATH":
                final_status = "FACT_RESULT"
                answer = str(fact_answer.get("final_answer") or "")
                answer_payload = {
                    "fact_aggregation": fact_answer.get("fact_aggregation"),
                    "claims": fact_answer.get("claims"),
                    "validation_result": fact_answer.get("validation_result"),
                    "citation_result": fact_answer.get("citation_result"),
                }
                citations = list(fact_answer.get("claims") or [])
            else:
                response = generator.generate(text, policy, bundle)
                final_status = (
                    "PROVIDER_TEMPORARY_FAILURE"
                    if response.status == "LLM_ERROR"
                    else response.status
                )
                answer = response.answer_text
                if final_status == "PROVIDER_TEMPORARY_FAILURE":
                    answer = "生成服务暂时不可用，本题未生成可核查的最终结论。"
                    answer_failure = {
                        "stage": "ANSWER",
                        "type": "PROVIDER_TEMPORARY_FAILURE",
                        "error": response.error,
                        "attempts": len(response.error_events) or 1,
                    }
                elif final_status in {"NO_EVIDENCE", "PARTIAL_EVIDENCE", "STRUCTURE_INVALID"}:
                    answer_failure = {
                        "stage": "ANSWER",
                        "type": final_status,
                        "failure_category": response.failure_category,
                        "protocol_category": response.protocol_category,
                        "repair_triggered": response.repair_triggered,
                    }
                answer_payload = {
                    "claims": response.claims,
                    "parsed_response": response.parsed_response,
                    "repair_response": response.repair_response,
                    "schema_validation": {
                        "valid": response.structure_valid,
                        "protocol_category": response.protocol_category,
                    },
                    "claim_validation": (
                        asdict(response.validation)
                        if response.validation is not None
                        else None
                    ),
                    "citation_render": (
                        asdict(response.citation_render)
                        if response.citation_render is not None
                        else None
                    ),
                    "diagnostics": response.diagnostics,
                    "error_events": response.error_events,
                }
                citations = citation_rows_from_claims(response.claims, selected_evidence)
            source_failure = None if chunks_by_root["Root-001"] or chunks_by_root["Root-002"] else "SHADOW_SOURCE_EMPTY"
            retrieval_failure = None if hits else "NO_CANDIDATE_FROM_EITHER_ROOT"
            evidence_failure = None if bundle.items else ("NO_SELECTED_EVIDENCE" if hits else None)
            row = {
                "question_id": question_id,
                "question": text,
                "fact_mode": route["fact_mode"],
                "route": route["route"],
                "routing_status": route["routing_status"],
                "routing_reasons": route["routing_reasons"],
                "roots_searched": retrieval_debug["roots_searched"],
                "candidate_count_by_root": retrieval_debug["candidate_count_by_root"],
                "federated_candidate_count": retrieval_debug["federated_candidates"],
                "top_candidates": serialize_candidates(hits, source_by_chunk, governance_by_chunk),
                "top_evidence": selected_evidence,
                "evidence_root": sorted({item.get("knowledge_root_id") for item in selected_evidence if item.get("knowledge_root_id")}),
                "evidence_bundle_status": bundle.status,
                "evidence_selection_notes": bundle.selection_notes,
                "answer_status": final_status,
                "final_status": final_status,
                "answer": answer,
                "citations": citations,
                "answer_payload": answer_payload,
                "failure_stage": answer_failure,
                "source_failure": source_failure,
                "retrieval_failure": retrieval_failure,
                "evidence_failure": evidence_failure,
                "answer_failure": answer_failure,
                "business_owner_verdict": "PENDING_REVIEW",
                "lineage_registration_and_body_preserved": bool(retrieval_debug["lineage_pairs_in_candidates"]),
                "provider_status": "NOT_REQUIRED" if final_status == "FACT_RESULT" else ("TEMPORARY_FAILURE" if final_status == "PROVIDER_TEMPORARY_FAILURE" else "CALLED"),
            }
            (OUTPUT_DIR / f"{question_id}.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            rows.append(row)
            print(f"unified_business_progress={ordinal}/10 status={final_status}", flush=True)
    finally:
        dense_provider.close()
        for client in clients.values():
            client.close()

    summary = {
        "question_count": len(rows),
        "status_counts": dict(Counter(row["final_status"] for row in rows)),
        "route_counts": dict(Counter(row["route"] for row in rows)),
        "fact_mode_counts": dict(Counter(row["fact_mode"] for row in rows)),
        "provider_failure_count": sum(row["final_status"] == "PROVIDER_TEMPORARY_FAILURE" for row in rows),
        "source_failure_count": sum(row["source_failure"] is not None for row in rows),
        "retrieval_failure_count": sum(row["retrieval_failure"] is not None for row in rows),
        "evidence_failure_count": sum(row["evidence_failure"] is not None for row in rows),
        "business_owner_verdict_counts": dict(Counter(row["business_owner_verdict"] for row in rows)),
        "root_chunk_counts": {root_id: len(chunks) for root_id, chunks in chunks_by_root.items()},
        "root_collection_points": {
            root_id: collection_points[root_id]
            for root_id, config in ROOT_CONFIG.items()
        },
        "duplicate_chunk_id_count_across_roots": collisions,
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "provider_configured": provider.available,
    }
    return rows, summary


def load_fact_capability_for_router() -> dict[str, Any]:
    from scripts.shadow_answer_router_v1 import load_fact_capability

    return load_fact_capability()


def render_answer_block(row: dict[str, Any]) -> list[str]:
    lines = [
        f"### {row['question_id']}｜{row['question']}",
        "",
        f"- Intent/Fact Mode：`{row['fact_mode']}`",
        f"- Route：`{row['route']}`",
        f"- Final Status：`{row['final_status']}`",
        f"- Business Owner Verdict：`{row['business_owner_verdict']}`",
        "",
        "#### AI最终回答",
        "",
        "```text",
        row["answer"] or "（无最终回答）",
        "```",
        "",
        "#### 引用来源",
        "",
    ]
    if row["top_evidence"]:
        lines.extend(
            [
                "| Evidence | Root | 文件 | document_role | authority_level | location | excerpt |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for item in row["top_evidence"]:
            excerpt = str(item.get("excerpt") or "").replace("|", "\\|").replace("\n", " ")[:500]
            lines.append(
                f"| {item.get('source_id')} | {item.get('knowledge_root_id')} | {item.get('file_name')} | {item.get('document_role')} | {item.get('authority_level')} | `{item.get('location')}` | {excerpt} |"
            )
    else:
        lines.append("- 无入选 Evidence。")
    lines.extend(
        [
            "",
            "#### 失败/边界诊断",
            "",
            f"- source_failure：`{row['source_failure']}`",
            f"- retrieval_failure：`{row['retrieval_failure']}`",
            f"- evidence_failure：`{row['evidence_failure']}`",
            f"- answer_failure：`{row['answer_failure']}`",
            "",
        ]
    )
    return lines


def render_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# V1.0 Unified Multi-Root Shadow Business Validation",
        "",
        "> TASK-017A：统一使用 Root-001 现有 Shadow baseline 与 Root-002 已批准 Shadow Import，执行 BA-001～BA-010 端到端验证。",
        "> 本报告只读使用两个现成 Shadow Collection；未扫描新的 Root-002 目录，未引入 Root-003，未写入正式 `data\\qdrant`，未修改正式 8000 服务。",
        "> `GENERATED`、`FACT_RESULT` 等技术状态不等于业务正确；每题业务结论默认 `PENDING_REVIEW`。",
        "",
        "## 1. Shadow 范围与技术状态",
        "",
        "| 项目 | Root-001 | Root-002 |",
        "|---|---|---|",
        f"| 来源根 | `{ROOT_CONFIG['Root-001']['source_root']}` | `{ROOT_CONFIG['Root-002']['source_root']}`（仅使用已批准 Shadow） |",
        f"| Collection | `{ROOT_CONFIG['Root-001']['collection']}` | `{ROOT_CONFIG['Root-002']['collection']}` |",
        f"| Shadow Chunk/Point | {summary['root_chunk_counts']['Root-001']} / {summary['root_collection_points']['Root-001']} | {summary['root_chunk_counts']['Root-002']} / {summary['root_collection_points']['Root-002']} |",
        f"| 跨 Root 重复 chunk_id | {summary['duplicate_chunk_id_count_across_roots']} | - |",
        f"| CUDA | `{summary['cuda_available']}` | GPU：`{summary['gpu_name']}` |",
        f"| Provider配置 | `{summary['provider_configured']}` | Claim Path按需调用，Fact Path不依赖LLM |",
        "",
        "## 2. 总体结果",
        "",
        f"- 测试问题：{summary['question_count']} 题。",
        f"- 状态分布：`{json.dumps(summary['status_counts'], ensure_ascii=False)}`",
        f"- 路由分布：`{json.dumps(summary['route_counts'], ensure_ascii=False)}`",
        f"- Fact Mode分布：`{json.dumps(summary['fact_mode_counts'], ensure_ascii=False)}`",
        f"- Provider临时失败：{summary['provider_failure_count']} 题。",
        f"- source_failure：{summary['source_failure_count']} 题；retrieval_failure：{summary['retrieval_failure_count']} 题；evidence_failure：{summary['evidence_failure_count']} 题。",
        f"- 业务评价分布：`{json.dumps(summary['business_owner_verdict_counts'], ensure_ascii=False)}`。",
        "",
        "### 业务评价计数边界",
        "",
        "由于本任务禁止自动替业务负责人判断答案正确性，`可直接使用`、`部分可用`、`正确拒答`、`错误回答`均不自动计数，当前10题全部保留为 `PENDING_REVIEW`。这不是答案质量结论。",
        "",
        "## 3. 逐题实际回答",
        "",
    ]
    for row in rows:
        lines.extend(render_answer_block(row))
    lines.extend(
        [
            "## 4. 重点验收结论",
            "",
            "- BA-001：同时检索两个 Root；回答中保留来源与业务待审状态。",
            "- BA-002：优先使用已有证据；若证据只展示结果而无公式，回答必须保持证据不足边界。",
            "- BA-003：不得用通用模板冒充厂房案例；业务负责人需重点检查 Root 与文件内容。",
            "- BA-004：检查是否命中自动喷淋方案原文；给排水相关案例不能自动等同于正确答案。",
            "- BA-005：不得从风电复盘推导完整的特殊环境图审标准。",
            "- BA-006：Router为 DIRECT_FACT → CLAIM_ANSWER_PATH；没有证据数字时不得猜测。",
            "- BA-007：Router为 Claim Path；重点检查2026工作计划和 Section Mapping 的 Claim/Evidence ID边界。",
            "- BA-008：Router为 DIRECT_FACT → CLAIM_ANSWER_PATH；公司级年度汇总不能被单项目金额替代。",
            "- BA-009：按 Gold Dataset 原始问题检查双周推进会督办，不以设计服务台账命中替代。",
            "- BA-010：Router为 DERIVED_FACT → FACT_ANSWER_PATH；复用已验证的 80/37/43 Fact Result，未重新让LLM计算。",
            "",
            "## 5. 可回放数据",
            "",
            f"每题完整JSON保存在：`{OUTPUT_DIR}`。包含问题、路由、两 Root 候选、统一 Evidence、最终回答、引用、失败分层和 `business_owner_verdict`。",
            "",
            "## 6. 安全边界",
            "",
            "1. 本次没有修改 `app/main.py`、`app/retriever.py`、Claim Answer Engine 或正式 Qdrant。",
            "2. Root-002 只读取 `data/shadow/root002_import/qdrant` 中已存在的 collection，没有扫描新的 Root-002 目录。",
            "3. Reranker未启用；RRF参数未调整；Embedding模型只用于查询向量，不生成全库Embedding。",
            "4. Root-001 登记页与 Root-002 正文同时保留在追踪中；若已识别 lineage，Shadow融合对正文做软优先，不删除登记页 lineage。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, summary = run()
    REPORT_PATH.write_text(render_report(rows, summary), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH.resolve()), "output_dir": str(OUTPUT_DIR.resolve()), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
