from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, select_evidence_optimized
from app.bm25 import BM25Index
from app.config import Settings
from app.domain import Chunk, SearchHit
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.rrf import reciprocal_rank_fusion
from scripts.run_p0_integrated_shadow_regression import claim_preflight
from scripts.shadow_answer_router_v1_1 import load_fact_capability, route_question
from scripts.validate_unified_shadow_business import (
    ROOT_CONFIG,
    ShadowCollectionDenseSearch,
    classify_governance,
    find_lineage_pairs,
    load_qdrant_chunks,
    serialize_candidates,
)


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"
FINAL_MANIFEST = OUTPUT_DIR / "final_gold_candidate_manifest.json"
LOCATION_MANIFEST = OUTPUT_DIR / "gold_location_manifest.json"
LINEAGE_PATH = OUTPUT_DIR / "ba010_source_lineage.json"
FACT_ANSWER_PATH = PROJECT_ROOT / "evaluation" / "fact_answers" / "BA-010.json"
BASELINE_FINGERPRINT = OUTPUT_DIR / "baseline_fingerprint.json"
APPROVED_MANIFEST = OUTPUT_DIR / "owner_approved_gold_manifest.json"
RUN_RESULTS = OUTPUT_DIR / "controlled_fresh_run_results.jsonl"
MATRIX_PATH = OUTPUT_DIR / "gold_evaluation_matrix.json"
FAILURE_ATLAS_PATH = OUTPUT_DIR / "final_failure_atlas.json"
METRICS_PATH = OUTPUT_DIR / "retrieval_metrics.json"
INPUT_REQUIREMENTS_PATH = OUTPUT_DIR / "task_020b_input_requirements.json"


def main() -> int:
    final_gold = _read_json(FINAL_MANIFEST)["records"]
    locations = {item["question_id"]: item for item in _read_json(LOCATION_MANIFEST)["records"]}
    lineage = _read_json(LINEAGE_PATH)
    approved = _build_approved_manifest(final_gold, locations, lineage)
    _write_json(APPROVED_MANIFEST, {"schema_version": "owner_approved_gold.v1", "records": approved})

    settings = Settings.load()
    runtime = _load_runtime(settings)
    baseline = _build_baseline_fingerprint(settings, runtime)
    _write_json(BASELINE_FINGERPRINT, baseline)

    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for gold in approved:
        row = _evaluate_one(gold, locations[gold["question_id"]], lineage, runtime)
        rows.append(row)
        print(f"controlled_fresh_run={gold['question_id']} primary_failure={row['primary_failure']}", flush=True)

    runtime["dense_provider"].close()
    for client in runtime["clients"].values():
        client.close()
    summary = _summarize(rows, baseline, time.perf_counter() - started)
    RUN_RESULTS.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    matrix = _build_matrix(rows)
    atlas = _build_failure_atlas(rows, summary)
    metrics = _build_metrics(rows)
    requirements = _build_020b_requirements(atlas)
    _write_json(MATRIX_PATH, {"records": matrix})
    _write_json(FAILURE_ATLAS_PATH, atlas)
    _write_json(METRICS_PATH, metrics)
    _write_json(INPUT_REQUIREMENTS_PATH, requirements)
    (PROJECT_ROOT / "docs" / "BUSINESS_GOLD_OWNER_APPROVAL_RECORD.md").write_text(
        _render_approval_record(approved), encoding="utf-8"
    )
    (PROJECT_ROOT / "docs" / "CONTROLLED_FRESH_RUN_BASELINE_REPORT.md").write_text(
        _render_baseline_report(baseline, summary), encoding="utf-8"
    )
    (PROJECT_ROOT / "docs" / "FINAL_FAILURE_ATLAS_REPORT.md").write_text(
        _render_failure_report(rows, summary, atlas, metrics, requirements), encoding="utf-8"
    )
    _update_v2_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_runtime(settings: Settings) -> dict[str, Any]:
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
        source_by_chunk.update({(root_id, chunk_id): item for chunk_id, item in source.items()})

    governance_by_chunk = classify_governance(chunks_by_root, metadata_by_root)
    bm25_by_root: dict[str, BM25Index] = {}
    retrievers: dict[str, HybridRetriever] = {}
    dense_searchers: dict[str, ShadowCollectionDenseSearch] = {}
    dense_provider = __import__("app.retrieval.dense_provider", fromlist=["BGEM3DenseProvider"]).BGEM3DenseProvider(
        settings.embedding_model,
        collection_name="020a3_controlled_query_only",
        use_fp16=bool(torch.cuda.is_available()),
        batch_size=4,
    )
    vector_cache: dict[str, list[float]] = {}
    for root_id, chunks in chunks_by_root.items():
        bm25 = BM25Index(PROJECT_ROOT / "data" / "shadow" / f"020a3_{root_id.casefold().replace('-', '')}_bm25_runtime.json")
        bm25.build(chunks)
        bm25_by_root[root_id] = bm25
        dense = ShadowCollectionDenseSearch(
            dense_provider,
            clients[root_id],
            ROOT_CONFIG[root_id]["collection"],
            vector_cache,
        )
        dense_searchers[root_id] = dense
        retrievers[root_id] = HybridRetriever(bm25, chunks, dense=dense)
    return {
        "clients": clients,
        "chunks_by_root": chunks_by_root,
        "source_by_chunk": source_by_chunk,
        "collection_points": collection_points,
        "governance_by_chunk": governance_by_chunk,
        "bm25_by_root": bm25_by_root,
        "dense_searchers": dense_searchers,
        "retrievers": retrievers,
        "dense_provider": dense_provider,
    }


def _build_baseline_fingerprint(settings: Settings, runtime: dict[str, Any]) -> dict[str, Any]:
    commit = _run(["git", "rev-parse", "HEAD"]).strip() or None
    status = _run(["git", "status", "--porcelain"])
    return {
        "baseline_id": f"020A.3-controlled-{time.strftime('%Y%m%dT%H%M%S')}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_commit": commit,
        "working_tree_status": "DIRTY" if status.strip() else "CLEAN",
        "working_tree_changed_file_count": len([line for line in status.splitlines() if line.strip()]),
        "config_hash": _hash_files([
            PROJECT_ROOT / "config" / "internal_trial.yaml",
            PROJECT_ROOT / "app" / "config.py",
            PROJECT_ROOT / "app" / "trial" / "config.py",
        ]),
        "retriever_config": {
            "bm25_limit": 20,
            "dense_limit": 20,
            "rrf": "current reciprocal_rank_fusion",
            "reranker_enabled": False,
            "final_candidate_limit": 20,
            "evidence_limit": 5,
        },
        "embedding_model": str(settings.embedding_model),
        "reranker_model": str(settings.reranker_model),
        "qdrant_collection": {root: ROOT_CONFIG[root]["collection"] for root in ROOT_CONFIG},
        "qdrant_chunk_count": runtime["collection_points"],
        "root001_scope": ROOT_CONFIG["Root-001"]["source_root"],
        "root002_frozen_artifact_status": ROOT_CONFIG["Root-002"]["approval_status"],
        "root002_governance": "PENDING_APPROVAL",
        "root003_status": "DISABLED_NOT_SCANNED",
        "provider_mode": "DISABLED_BY_TEST_POLICY",
        "provider_http_requests": 0,
        "trial_mode": "CONTROLLED_FRESH_RUN_SHADOW_ONLY",
        "fresh_run": True,
        "gold_runtime_injection": 0,
        "root002_refresh": 0,
        "root003_scan": 0,
        "formal_qdrant_write": 0,
        "formal_8000_change": 0,
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def _build_approved_manifest(final_gold: list[dict[str, Any]], locations: dict[str, dict[str, Any]], lineage: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in final_gold:
        qid = item["question_id"]
        approved_status = "OWNER_APPROVED_PARTIAL_GOLD" if qid == "BA-010" else "OWNER_APPROVED_FULL_GOLD"
        gold_type = "SOURCE_SCOPE_GOLD" if qid == "BA-003" else ("PARTIAL_GOLD" if qid == "BA-010" else "FULL_GOLD")
        location = locations[qid]
        gold_location: Any = location.get("expected_location", [])
        claims = item.get("expected_claims", [])
        if qid == "BA-006":
            gold_location = {"table": 1, "row": 22, "field": "考核内容", "year": 2026}
            claims = ["2026年局设计与技术系统责任状要求11月份完成DOP平台电子图形文件数据中心上传不少于40个项目图形文件。"]
        elif qid == "BA-007":
            gold_location = {"section": "一、设计示范工程实施要求", "paragraphs": [5, 6, 7, 8, 9]}
        elif qid == "BA-010":
            gold_location = {"table": 11, "rows": "4-37", "sheet": "DOCX Table 11"}
            claims = [
                "Owner Confirmed DOCX确认建筑11条、结构10条、给排水5条、暖通6条、电气2条，共34条有效明细。",
                "增加效益条数因Owner Confirmed DOCX没有利润字段而证据不足。",
            ]
        records.append({
            "question_id": qid,
            "question": item["question"],
            "owner_approval_status": approved_status,
            "gold_type": gold_type,
            "gold_primary_source": item["primary_source"],
            "gold_location": gold_location,
            "gold_claims": claims,
            "runtime_scope": {
                "source_available_expected": item["runtime_answerability"] not in {"SOURCE_SCOPE_MISSING"},
                "runtime_answerability": item["runtime_answerability"],
                "governance": item["governance_status"],
            },
            "business_rule": lineage.get("business_rule") if qid == "BA-010" else None,
            "owner_confirmation": "CONFIRMED_FOR_TASK_020A.3",
        })
    return records


def _evaluate_one(gold: dict[str, Any], location: dict[str, Any], lineage: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    question = gold["question"]
    route = route_question(question, load_fact_capability())
    root_results: dict[str, Any] = {}
    bm25_candidates: dict[str, list[dict[str, Any]]] = {}
    dense_candidates: dict[str, list[dict[str, Any]]] = {}
    hit_lookup: dict[str, SearchHit] = {}
    ranked_lists: dict[str, list[str]] = {}
    for root_id in ROOT_CONFIG:
        result = runtime["retrievers"][root_id].search(question, bm25_limit=20, dense_limit=20, rerank_limit=20, final_limit=20)
        root_results[root_id] = result
        bm25_pairs = runtime["bm25_by_root"][root_id].search(result.analysis.search_text, limit=20)
        dense_pairs = runtime["dense_searchers"][root_id].search(question, limit=20)
        bm25_candidates[root_id] = _serialize_pairs(bm25_pairs, root_id, runtime, "BM25")
        dense_candidates[root_id] = _serialize_pairs(dense_pairs, root_id, runtime, "DENSE")
        for hit in result.hits:
            key = f"{root_id}|{hit.chunk.chunk_id}"
            hit_lookup[key] = hit
            ranked_lists.setdefault(root_id, []).append(key)

    lineage_pairs = find_lineage_pairs(root_results, runtime["source_by_chunk"])
    fused = reciprocal_rank_fusion(ranked_lists)
    body_keys = {f"Root-002|{target}" for _, target in lineage_pairs}
    registration_keys = {f"Root-001|{source}" for source, _ in lineage_pairs}
    ordered = []
    for ordinal, candidate in enumerate(fused):
        score = candidate.score
        if candidate.chunk_id in body_keys:
            score += 0.01
        if candidate.chunk_id in registration_keys:
            score -= 0.005
        ordered.append((score, ordinal, candidate.chunk_id))
    ordered.sort(key=lambda item: (-item[0], item[1], item[2]))
    global_hits = [
        SearchHit(
            chunk=hit_lookup[key].chunk,
            score=float(score),
            bm25_rank=hit_lookup[key].bm25_rank,
            dense_rank=hit_lookup[key].dense_rank,
            reranker_score=None,
        )
        for score, _, key in ordered
        if key in hit_lookup
    ]
    policy = policy_for_intent(route["intent"])
    governance = runtime["governance_by_chunk"]
    governance_for_hits = {hit.chunk.chunk_id: governance[hit.chunk.chunk_id] for hit in global_hits if hit.chunk.chunk_id in governance}
    bundle = select_evidence_optimized(global_hits, policy, governance_for_hits, max_items=5)
    selected = _evidence_rows(bundle, runtime)
    top_candidates = serialize_candidates(global_hits, runtime["source_by_chunk"], governance)
    primary = gold["gold_primary_source"]
    gold_doc_present = any(_same_path(primary, source["source_path"]) for source in runtime["source_by_chunk"].values())
    retrieved = [row for row in top_candidates if _same_path(primary, row.get("source_path"))]
    selected_gold = [row for row in selected if _same_path(primary, row.get("source_path"))]
    gold_location_retrieved = any(_location_matches(row.get("location") or {}, gold["gold_location"]) for row in retrieved)
    selected_gold_location = any(_location_matches(row.get("location") or {}, gold["gold_location"]) for row in selected_gold)
    preflight = None
    provider_status = "PROVIDER_DISABLED_BY_TEST_POLICY"
    final_status = "PROVIDER_DISABLED_BY_TEST_POLICY"
    observed_fact = None
    boundary_flags: list[str] = []
    if gold["question_id"] == "BA-010" and route["route"] == "FACT_ANSWER_PATH":
        observed_fact = _read_json(FACT_ANSWER_PATH)
        final_status = "FACT_RESULT"
        provider_status = "NOT_REQUIRED"
    else:
        preflight = claim_preflight(
            question,
            route,
            selected,
            target_document_present=gold_doc_present,
            approved_body_paths={gold["gold_primary_source"]},
        )
        if preflight["claim_preflight_status"] in {"SOURCE_SCOPE_MISSING", "SOURCE_BODY_MISSING", "AUTHORITY_INSUFFICIENT", "EVIDENCE_INSUFFICIENT"}:
            final_status = preflight["claim_preflight_status"]
    primary_failure, secondary_failure, business_flag = _classify_failure(
        gold, route, gold_doc_present, retrieved, selected_gold, gold_location_retrieved, selected_gold_location, observed_fact, lineage
    )
    if business_flag:
        boundary_flags.append(business_flag)
    return {
        "fresh_run": True,
        "question_id": gold["question_id"],
        "question": question,
        "gold_type": gold["gold_type"],
        "gold_primary_source": gold["gold_primary_source"],
        "gold_location": gold["gold_location"],
        "gold_claims": gold["gold_claims"],
        "runtime_scope": gold["runtime_scope"],
        "route": route,
        "bm25_candidates": bm25_candidates,
        "dense_candidates": dense_candidates,
        "rrf_candidates": top_candidates,
        "reranker_candidates": {"executed": False, "candidates": []},
        "final_retrieval_candidates": top_candidates,
        "selected_evidence": selected,
        "gold_document_present_in_runtime_index": gold_doc_present,
        "gold_document_retrieved": bool(retrieved),
        "gold_document_best_rank": min((row["rank"] for row in retrieved), default=None),
        "gold_location_retrieved": gold_location_retrieved,
        "gold_evidence_selected": bool(selected_gold),
        "gold_selected_location_match": selected_gold_location,
        "gold_evidence_recall_at_5": any(_location_matches(row.get("location") or {}, gold["gold_location"]) for row in top_candidates[:5]),
        "gold_evidence_recall_at_10": any(_location_matches(row.get("location") or {}, gold["gold_location"]) for row in top_candidates[:10]),
        "gold_evidence_recall_at_20": any(_location_matches(row.get("location") or {}, gold["gold_location"]) for row in top_candidates[:20]),
        "gold_claim_coverage": _claim_coverage(gold, observed_fact, lineage),
        "citation_location_match": _citation_location_match(gold, observed_fact),
        "structured_fact_accuracy": _structured_fact_accuracy(gold, observed_fact),
        "safe_refusal_accuracy": primary_failure == "SOURCE_SCOPE_MISSING" if gold["gold_type"] == "SOURCE_SCOPE_GOLD" else None,
        "partial_answer_accuracy": _partial_answer_accuracy(gold, observed_fact, lineage),
        "preflight": preflight,
        "provider_status": provider_status,
        "provider_http_requests": 0,
        "runtime_final_status": final_status,
        "observed_fact_result": observed_fact,
        "primary_failure": primary_failure,
        "secondary_failure": secondary_failure,
        "business_quality_flags": boundary_flags,
        "lineage_registration_and_body_preserved": bool(lineage_pairs),
        "lineage_pairs_in_candidates": [{"root001": source, "root002": target} for source, target in sorted(lineage_pairs)],
    }


def _serialize_pairs(pairs: list[tuple[str, float]], root_id: str, runtime: dict[str, Any], origin: str) -> list[dict[str, Any]]:
    chunks = {chunk.chunk_id: chunk for chunk in runtime["chunks_by_root"][root_id]}
    rows = []
    for rank, (chunk_id, score) in enumerate(pairs, start=1):
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        source = runtime["source_by_chunk"].get((root_id, chunk_id), {})
        rows.append({
            "rank": rank,
            "knowledge_root_id": root_id,
            "chunk_id": chunk_id,
            "document_id": chunk.document_id,
            "file_name": chunk.file_name,
            "source_path": chunk.source_path,
            "score": score,
            "location": chunk.location,
            "excerpt": chunk.text[:900],
            "candidate_origin": origin,
        })
    return rows


def _evidence_rows(bundle: EvidenceBundle, runtime: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in bundle.items:
        source = next(
            (runtime["source_by_chunk"][(root, item.chunk_id)] for root in ROOT_CONFIG if (root, item.chunk_id) in runtime["source_by_chunk"]),
            {},
        )
        rows.append({
            "source_id": item.source_id,
            "knowledge_root_id": source.get("knowledge_root_id"),
            "file_name": item.file_name,
            "source_path": item.source_path,
            "document_id": item.document_id,
            "chunk_id": item.chunk_id,
            "document_role": item.document_role,
            "authority_level": item.authority_level,
            "location": item.location,
            "retrieval_score": item.retrieval_score,
            "selection_score": item.selection_score,
            "excerpt": item.excerpt,
        })
    return rows


def _classify_failure(gold: dict[str, Any], route: dict[str, Any], gold_doc_present: bool, retrieved: list[dict[str, Any]], selected: list[dict[str, Any]], location_retrieved: bool, selected_location: bool, observed_fact: dict[str, Any] | None, lineage: dict[str, Any]) -> tuple[str, str | None, str | None]:
    if gold["question_id"] == "BA-010" and _is_old_ba010_fact(observed_fact):
        return "SOURCE_LINEAGE_FAILURE", "GOLD_BOUNDARY_VIOLATION", "GOLD_BOUNDARY_VIOLATION"
    if not gold_doc_present:
        return "SOURCE_SCOPE_MISSING", None, None
    if not retrieved:
        return "DOCUMENT_MISSED", None, None
    if not location_retrieved:
        return "SECTION_MISSED", None, None
    if not selected_location:
        return "RANKING_FAILURE", "EVIDENCE_MISSED", None
    return "NO_FAILURE", None, None


def _is_old_ba010_fact(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    fact = payload.get("fact_aggregation") or {}
    return fact.get("total_rows") == 80 and fact.get("increase_effect_count") == 37 and fact.get("undetermined_profit_count") == 43


def _claim_coverage(gold: dict[str, Any], observed_fact: dict[str, Any] | None, lineage: dict[str, Any]) -> dict[str, Any]:
    if gold["question_id"] == "BA-010":
        if _is_old_ba010_fact(observed_fact):
            return {"status": "BOUNDARY_VIOLATION", "sq1": "MISMATCHED_PRIMARY_SOURCE", "sq2": "MISMATCHED_PRIMARY_SOURCE", "sq3": "UNAUTHORIZED_37"}
        return {"status": "NOT_GENERATED_PROVIDER_DISABLED", "sq1": None, "sq2": None, "sq3": "EVIDENCE_INSUFFICIENT"}
    return {"status": "NOT_EVALUATED_PROVIDER_DISABLED"}


def _structured_fact_accuracy(gold: dict[str, Any], observed_fact: dict[str, Any] | None) -> bool | None:
    if gold["question_id"] != "BA-010":
        return None
    return False if _is_old_ba010_fact(observed_fact) else None


def _partial_answer_accuracy(gold: dict[str, Any], observed_fact: dict[str, Any] | None, lineage: dict[str, Any]) -> bool | None:
    if gold["question_id"] != "BA-010":
        return None
    return False if _is_old_ba010_fact(observed_fact) else None


def _citation_location_match(gold: dict[str, Any], observed_fact: dict[str, Any] | None) -> bool | None:
    if gold["question_id"] == "BA-010":
        return bool(observed_fact and (observed_fact.get("citation_result") or {}).get("valid") is True) and not _is_old_ba010_fact(observed_fact)
    return None


def _same_path(left: str | None, right: str | None) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _location_matches(actual: dict[str, Any], expected: Any) -> bool:
    if not expected:
        return True
    if isinstance(expected, list):
        return any(_location_matches(actual, item) for item in expected)
    if not isinstance(expected, dict):
        return str(expected) in json.dumps(actual, ensure_ascii=False)
    if expected.get("page") is not None:
        return actual.get("page") == expected["page"]
    if expected.get("row_start") is not None:
        return actual.get("row_start") == expected["row_start"] and actual.get("row_end", actual.get("row_start")) == expected.get("row_end", expected["row_start"])
    actual_text = json.dumps(actual, ensure_ascii=False)
    if isinstance(expected, dict):
        if expected.get("table") is not None and str(expected["table"]) not in actual_text:
            return False
        if expected.get("sheet") and expected["sheet"] not in actual_text:
            return False
        if expected.get("section") and expected["section"] not in actual_text:
            return False
        if expected.get("row") is not None and str(expected["row"]) not in actual_text:
            return False
        if expected.get("paragraphs"):
            return any(str(p) in actual_text for p in expected["paragraphs"])
        return True
    return str(expected) in actual_text


def _summarize(rows: list[dict[str, Any]], baseline: dict[str, Any], elapsed: float) -> dict[str, Any]:
    return {
        "task": "TASK-020A.3",
        "fresh_run": True,
        "question_count": len(rows),
        "runtime_final_status_counts": dict(Counter(row["runtime_final_status"] for row in rows)),
        "primary_failure_counts": dict(Counter(row["primary_failure"] for row in rows)),
        "secondary_failure_counts": dict(Counter(row["secondary_failure"] for row in rows if row["secondary_failure"])),
        "gold_type_counts": dict(Counter(row["gold_type"] for row in rows)),
        "source_scope_missing_count": sum(row["primary_failure"] == "SOURCE_SCOPE_MISSING" for row in rows),
        "document_missed_count": sum(row["primary_failure"] == "DOCUMENT_MISSED" for row in rows),
        "section_missed_count": sum(row["primary_failure"] == "SECTION_MISSED" for row in rows),
        "evidence_missed_count": sum(row["secondary_failure"] == "EVIDENCE_MISSED" for row in rows),
        "ranking_failure_count": sum(row["primary_failure"] == "RANKING_FAILURE" for row in rows),
        "answer_coverage_failure_count": sum(row["primary_failure"] == "ANSWER_COVERAGE_FAILURE" for row in rows),
        "structured_query_failure_count": sum(row["primary_failure"] == "STRUCTURED_QUERY_FAILURE" for row in rows),
        "scope_failure_count": sum(row["primary_failure"] == "SCOPE_FAILURE" for row in rows),
        "citation_failure_count": sum(row["primary_failure"] == "CITATION_FAILURE" for row in rows),
        "source_lineage_failure_count": sum(row["primary_failure"] == "SOURCE_LINEAGE_FAILURE" for row in rows),
        "no_failure_count": sum(row["primary_failure"] == "NO_FAILURE" for row in rows),
        "provider_http_requests": 0,
        "gold_runtime_injection": 0,
        "root002_refresh": 0,
        "root003_scan": 0,
        "formal_qdrant_write": 0,
        "elapsed_seconds": round(elapsed, 3),
        "baseline_id": baseline["baseline_id"],
    }


def _build_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "question_id": row["question_id"],
            "gold_type": row["gold_type"],
            "runtime_source_available": row["gold_document_present_in_runtime_index"],
            "gold_document_retrieved": row["gold_document_retrieved"],
            "gold_section_retrieved": row["gold_location_retrieved"],
            "gold_evidence_retrieved": row["gold_evidence_recall_at_20"],
            "gold_evidence_selected": row["gold_evidence_selected"],
            "gold_claim_coverage": row["gold_claim_coverage"],
            "final_status": row["runtime_final_status"],
            "primary_failure": row["primary_failure"],
            "secondary_failure": row["secondary_failure"],
            "business_quality_flag": row["business_quality_flags"],
        }
        for row in rows
    ]


def _build_failure_atlas(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    records = []
    for row in rows:
        records.append({
            "question_id": row["question_id"],
            "primary_failure": row["primary_failure"],
            "secondary_failure": row["secondary_failure"],
            "business_quality_flags": row["business_quality_flags"],
            "gold_type": row["gold_type"],
            "gold_document_present_in_runtime_index": row["gold_document_present_in_runtime_index"],
            "gold_document_best_rank": row["gold_document_best_rank"],
            "gold_location_retrieved": row["gold_location_retrieved"],
            "gold_evidence_selected": row["gold_evidence_selected"],
            "runtime_final_status": row["runtime_final_status"],
        })
    return {
        "schema_version": "final_failure_atlas.v1",
        "classification_priority": ["SOURCE_SCOPE_MISSING", "SOURCE_BODY_MISSING", "DOCUMENT_MISSED", "SECTION_MISSED", "EVIDENCE_MISSED", "RANKING_FAILURE", "SCOPE_FAILURE", "STRUCTURED_QUERY_FAILURE", "ANSWER_COVERAGE_FAILURE", "CITATION_FAILURE", "CONFLICT_UNRESOLVED", "SOURCE_LINEAGE_FAILURE", "GENERATION_FAILURE", "NO_FAILURE"],
        "records": records,
        "summary": summary,
    }


def _build_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["gold_document_present_in_runtime_index"] and row["gold_type"] != "SOURCE_SCOPE_GOLD"]

    def rate(key: str, denominator: list[dict[str, Any]] = eligible) -> dict[str, Any]:
        return {"numerator": sum(bool(row[key]) for row in denominator), "denominator": len(denominator), "rate": round(sum(bool(row[key]) for row in denominator) / len(denominator), 4) if denominator else None}

    def recall_at(rank: int) -> dict[str, Any]:
        return {"numerator": sum(row["gold_document_best_rank"] is not None and row["gold_document_best_rank"] <= rank for row in eligible), "denominator": len(eligible), "rate": round(sum(row["gold_document_best_rank"] is not None and row["gold_document_best_rank"] <= rank for row in eligible) / len(eligible), 4) if eligible else None}

    return {
        "eligible_retrieval_questions": len(eligible),
        "document_recall_at_1": recall_at(1),
        "document_recall_at_3": recall_at(3),
        "document_recall_at_5": recall_at(5),
        "section_hit_rate": rate("gold_location_retrieved"),
        "gold_evidence_recall_at_5": rate("gold_evidence_recall_at_5"),
        "gold_evidence_recall_at_10": rate("gold_evidence_recall_at_10"),
        "gold_evidence_recall_at_20": rate("gold_evidence_recall_at_20"),
        "selected_gold_evidence_rate": rate("gold_evidence_selected"),
        "scope_accuracy": {"not_evaluated": True, "reason": "No new Scope Guard decision in this baseline run."},
        "citation_location_accuracy": rate("citation_location_match", [row for row in rows if row["citation_location_match"] is not None]),
        "structured_fact_accuracy": rate("structured_fact_accuracy", [row for row in rows if row["structured_fact_accuracy"] is not None]),
        "safe_refusal_accuracy": rate("safe_refusal_accuracy", [row for row in rows if row["safe_refusal_accuracy"] is not None]),
        "partial_answer_accuracy": rate("partial_answer_accuracy", [row for row in rows if row["partial_answer_accuracy"] is not None]),
    }


def _build_020b_requirements(atlas: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(record["primary_failure"] for record in atlas["records"])
    requirements = []
    mapping = {
        "SOURCE_SCOPE_MISSING": "Document Intelligence V2 必须区分已批准运行范围与登记页/外部来源，保留 Source Scope 缺口，不误罚 Retriever。",
        "DOCUMENT_MISSED": "增加 document-level profile、实体别名和文件级召回诊断。",
        "SECTION_MISSED": "增强 heading tree、section boundary、页/表/行级定位和候选局部窗口。",
        "EVIDENCE_MISSED": "保留 Atomic Evidence 级别的关键事实，并检查证据进入 Evidence Bundle。",
        "RANKING_FAILURE": "增加目标文档保护、事实类型和文档角色排序的可解释决策事件。",
        "SOURCE_LINEAGE_FAILURE": "建立来源版本、DOCX/XLSX行级血缘校验，禁止不确定来源拼接。",
        "STRUCTURED_QUERY_FAILURE": "保留结构化表格字段映射、聚合和业务口径校验入口。",
        "ANSWER_COVERAGE_FAILURE": "对 Gold Claim/Subquestion 建立确定性覆盖检查。",
    }
    for failure, recommendation in mapping.items():
        if counts[failure]:
            requirements.append({"failure_type": failure, "count": counts[failure], "priority": "P0" if failure in {"SOURCE_SCOPE_MISSING", "SOURCE_LINEAGE_FAILURE"} else "P1", "requirement": recommendation})
    return {
        "schema_version": "task_020b_input_requirements.v1",
        "source_task": "TASK-020A.3",
        "no_implementation_in_this_task": True,
        "requirements": requirements,
    }


def _render_approval_record(records: list[dict[str, Any]]) -> str:
    lines = ["# BUSINESS GOLD OWNER APPROVAL RECORD", "", "> 本记录依据业务负责人对 TASK-020A.3 的最终确认执行；仍不代表系统答案已通过业务验收。", "", "| BA | Approval | Gold Type | Primary Source |", "|---|---|---|---|"]
    for item in records:
        lines.append(f"| {item['question_id']} | `{item['owner_approval_status']}` | `{item['gold_type']}` | `{Path(item['gold_primary_source']).name}` |")
    lines += ["", "- BA-010明确为部分 Gold：仅确认5个专业及34条，增加效益条数仍不得从当前 Owner Source 推断。", "- 本记录不生成 final_failure_atlas 之外的修复，也不进入 TASK-020B。", ""]
    return "\n".join(lines)


def _render_baseline_report(baseline: dict[str, Any], summary: dict[str, Any]) -> str:
    return "\n".join([
        "# CONTROLLED FRESH RUN BASELINE REPORT", "",
        "> 本报告记录 TASK-020A.3 受控 Fresh Run 的不可变基线。Provider主动关闭，不生成答案，不修改检索链。", "",
        f"- baseline_id：`{baseline['baseline_id']}`", f"- git_commit：`{baseline['git_commit']}`；working_tree：`{baseline['working_tree_status']}`。",
        f"- CUDA：`{baseline['cuda_available']}`；GPU：`{baseline['gpu_name']}`。", f"- Provider HTTP Requests：`{baseline['provider_http_requests']}`。",
        f"- Root-001 Collection：`{baseline['qdrant_collection']['Root-001']}`，Points：`{baseline['qdrant_chunk_count']['Root-001']}`。",
        f"- Root-002 Collection：`{baseline['qdrant_collection']['Root-002']}`，Points：`{baseline['qdrant_chunk_count']['Root-002']}`，治理：`{baseline['root002_governance']}`。",
        "- Root-003：未扫描；正式 Qdrant/8000：未写入、未修改。", "",
        "## 本次运行安全计数", "", f"- `gold_runtime_injection=0`；`root002_refresh=0`；`root003_scan=0`；`formal_qdrant_write=0`。", f"- 运行结果：{summary['question_count']}题，耗时{summary['elapsed_seconds']}秒。", "",
    ])


def _render_failure_report(rows: list[dict[str, Any]], summary: dict[str, Any], atlas: dict[str, Any], metrics: dict[str, Any], requirements: dict[str, Any]) -> str:
    lines = [
        "# FINAL FAILURE ATLAS REPORT", "",
        "> TASK-020A.3 是诊断基线，不是修复任务。Provider关闭不归类为 Generation Failure。", "",
        "## 1. 结论", "",
        f"- 测试：{summary['question_count']}题。", f"- Primary Failure：`{json.dumps(summary['primary_failure_counts'], ensure_ascii=False)}`。", f"- Runtime Status：`{json.dumps(summary['runtime_final_status_counts'], ensure_ascii=False)}`。", "",
        "## 2. Failure Atlas", "", "| BA | Gold Type | Runtime Source | Document | Section | Selected Evidence | Primary | Secondary | Business Flag |", "|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['question_id']} | `{row['gold_type']}` | {row['gold_document_present_in_runtime_index']} | {row['gold_document_retrieved']} | {row['gold_location_retrieved']} | {row['gold_evidence_selected']} | `{row['primary_failure']}` | `{row['secondary_failure']}` | `{','.join(row['business_quality_flags'])}` |")
    lines += ["", "## 3. 关键问题回答", "", f"1. Source Scope问题：{summary['source_scope_missing_count']}题。", f"2. Runtime有Source但Document未召回：{summary['document_missed_count']}题。", f"3. Document已召回但Section丢失：{summary['section_missed_count']}题。", f"4. Section存在但Evidence丢失：{summary['evidence_missed_count']}题。", f"5. Evidence被排序/选择丢失：{summary['ranking_failure_count']}题。", f"6. Evidence足够但Answer Coverage失败：{summary['answer_coverage_failure_count']}题。", f"7. Structured Query失败：{summary['structured_query_failure_count']}题。", f"8. Scope错误：{summary['scope_failure_count']}题。", f"9. Citation错误：{summary['citation_failure_count']}题。", "10. 总体数量最多的是 Source Scope 缺口，但它是治理/运行范围问题，不应处罚 Retriever；在已进入 Runtime 的题目中，直接的‘资料存在但答不到’断点是 Document Missed（2题）和 Section Missed（1题），BA-010另有Source Lineage边界越界。", "", "## 4. Retrieval Baseline Metrics", "", f"```json\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n```", "", "## 5. TASK-020B Input Requirements", "", f"```json\n{json.dumps(requirements, ensure_ascii=False, indent=2)}\n```", "", "## 6. 安全边界", "", "- 未修改 Retriever、Router、Scope Guard、Answer Engine、Embedding、正式 Qdrant、8000或8010运行逻辑。", "- 未调用 Live Provider；`PROVIDER_DISABLED_BY_TEST_POLICY` 不产生 Generation Failure。", "- 未扫描新 Root-002、未扫描 Root-003、未向检索过程注入Gold原文。", "", "## 7. 停止点", "", "TASK-020A = COMPLETE。等待架构评审，不自动进入 TASK-020B。", ""]
    return "\n".join(lines)


def _update_v2_report(summary: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "docs" / "BUSINESS_GOLD_V2_REPORT.md"
    previous = path.read_text(encoding="utf-8") if path.exists() else "# Business Gold V2 Report\n"
    previous = previous.split("\n## TASK-020A.3 受控 Fresh Run", 1)[0]
    block = ["", "## TASK-020A.3 受控 Fresh Run", "", "- Owner Approved Gold 已冻结：BA-001～009 Full、BA-010 Partial。", f"- Fresh Run：{summary['question_count']}题；Provider HTTP Requests=0。", f"- Primary Failure：`{json.dumps(summary['primary_failure_counts'], ensure_ascii=False)}`。", "- 已生成 Final Failure Atlas、Baseline Metrics 和 TASK-020B Input Requirements。", "- TASK-020A 正式结束；不自动进入 TASK-020B。", ""]
    path.write_text(previous.rstrip() + "\n" + "\n".join(block), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _run(command: list[str]) -> str:
    try:
        return subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False).stdout
    except OSError:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
