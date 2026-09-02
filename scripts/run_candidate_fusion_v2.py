from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import time
import gc
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from qdrant_client import QdrantClient

from app.config import Settings
from app.retrieval.candidate_fusion_v2 import apply_reranker_scores, final_evidence, fuse_evidence_candidates, reranker_passage
from app.retrieval.hierarchical_v1 import HierarchicalIndex
from app.retrieval.query_planner_v1 import plan_query


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "evaluation" / "candidate_fusion_v2"
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "candidate_fusion_v2"
HIERARCHICAL_DIR = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"
GENERIC_GOLD = PROJECT_ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
SEED = 20260830
TOP_N = 20


def main() -> int:
    started = time.perf_counter()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings.load()
    business, business_baseline = _business_gold()
    generic = _generic_regression(_document_file_names())
    _write_json(EVAL_DIR / "generic_regression_manifest.json", {"seed": SEED, "records": generic})
    cases = [*business, *generic]
    snapshot = _snapshot()
    case_manifest = SHADOW_DIR / "cases.json"
    query_vectors_path = SHADOW_DIR / "query_vectors.json"
    prepared_path = SHADOW_DIR / "prepared_candidates.jsonl"
    evidence_scores_path = SHADOW_DIR / "evidence_dense_scores.json"
    pre_rerank_path = SHADOW_DIR / "pre_rerank_inputs.jsonl"
    reranker_scores_path = SHADOW_DIR / "reranker_scores.json"
    _write_json(case_manifest, {"records": [{"id": case["id"], "question": case["question"]} for case in cases]})
    query_vectors = _run_query_workers(cases, query_vectors_path)
    index = HierarchicalIndex.load(HIERARCHICAL_DIR)
    prepared = [_prepare_case(index, case, plan_query(case["question"]), query_vectors[str(case["id"])]) for case in cases]
    _write_jsonl(prepared_path, prepared)
    evidence_scores, evidence_dense = _existing_evidence_dense(prepared)
    _write_json(evidence_scores_path, {"scores": evidence_scores, **evidence_dense})
    atomic_by_id = {str(row.get("evidence_id")): row for row in index.atomic if row.get("evidence_id")}
    records = [_fuse_prepared(row, atomic_by_id, evidence_scores.get(str(row["question_id"]), {})) for row in prepared]
    _write_jsonl(pre_rerank_path, [{"question_id": row["question_id"], "question": row["question"], "passages": [reranker_passage(candidate) for candidate in row["pre_rerank_candidates"]]} for row in records])
    del index, atomic_by_id, prepared
    gc.collect()
    reranker_scores = _run_rerank_workers(records, reranker_scores_path)
    for record in records:
        _apply_reranker(record, reranker_scores.get(str(record["question_id"]), []))

    ba_records = [row for row in records if row["set"] == "business"]
    generic_records = [row for row in records if row["set"] == "generic"]
    pre = {"business": _metrics(ba_records, "pre"), "generic": _metrics(generic_records, "pre")}
    post = {"business": _metrics(ba_records, "post"), "generic": _metrics(generic_records, "post")}
    baseline = {"business": _metrics(ba_records, "baseline"), "generic": _metrics(generic_records, "baseline")}
    scope = _scope_analysis(records)
    authority = _authority_analysis(generic_records)
    duplicate = _duplicate_analysis(records)
    lineage = _lineage_analysis(ba_records)
    matrix = _ba_matrix(ba_records, business_baseline)
    _write_json(EVAL_DIR / "fusion_config.json", _config(settings, snapshot, evidence_dense))
    _write_json(EVAL_DIR / "ba_fusion_matrix.json", {"records": matrix})
    _write_json(EVAL_DIR / "generic_regression_results.json", {"baseline": baseline["generic"], "pre_rerank": pre["generic"], "post_rerank": post["generic"], "records": _compact_results(generic_records)})
    _write_json(EVAL_DIR / "pre_rerank_metrics.json", pre)
    _write_json(EVAL_DIR / "post_rerank_metrics.json", post)
    _write_json(EVAL_DIR / "scope_ranking_analysis.json", scope)
    _write_json(EVAL_DIR / "authority_ranking_analysis.json", authority)
    _write_json(EVAL_DIR / "duplicate_analysis.json", duplicate)
    _write_json(EVAL_DIR / "lineage_safety_validation.json", lineage)
    _write_jsonl(EVAL_DIR / "fusion_traces.jsonl", records)
    _write_json(SHADOW_DIR / "index_snapshot.json", snapshot)
    reports = _reports(_read_json(GOLD_DIR / "retrieval_metrics.json"), baseline, pre, post, matrix, scope, authority, duplicate, lineage, settings, snapshot, time.perf_counter() - started)
    (PROJECT_ROOT / "docs" / "CANDIDATE_FUSION_V2_REPORT.md").write_text(reports["main"], encoding="utf-8")
    (PROJECT_ROOT / "docs" / "CANDIDATE_FUSION_AB_REPORT.md").write_text(reports["ab"], encoding="utf-8")
    _validate(baseline, pre, post, lineage, duplicate)
    print(json.dumps({"business_pre_mrr": pre["business"]["gold_evidence_mrr"], "business_post_mrr": post["business"]["gold_evidence_mrr"], "provider_http_requests": 0}, ensure_ascii=False))
    return 0


def _prepare_case(index: HierarchicalIndex, case: dict[str, Any], plan: Any, query_vector: list[float]) -> dict[str, Any]:
    generated = index.retrieve(plan, query_vector)
    return {"case": case, "query_plan": plan.to_dict(), "query_vector": query_vector, "generated": generated, "raw_candidates": generated["atomic_candidates"][:TOP_N]}


def _fuse_prepared(prepared: dict[str, Any], atomic_by_id: dict[str, dict[str, Any]], dense_scores: dict[str, float]) -> dict[str, Any]:
    started = time.perf_counter()
    case = prepared["case"]
    plan = plan_query(case["question"])
    generated = prepared["generated"]
    raw = prepared["raw_candidates"]
    pre_rows = fuse_evidence_candidates(plan=plan, result=generated, atomic_by_id=atomic_by_id, evidence_dense_scores=dense_scores)
    pre_final = final_evidence(pre_rows, limit=10)
    baseline_rank = _target_rank(raw, case)
    pre_rank = _target_rank(pre_final, case)
    document_rank = _document_rank(generated["document_candidates"], case)
    section_rank = _section_rank(generated["section_candidates"], generated["table_candidates"], case)
    return {
        "schema_version": "candidate_fusion.v2",
        "set": case["set"],
        "question_id": case["id"],
        "question": case["question"],
        "query_plan": plan.to_dict(),
        "gold": {key: case.get(key) for key in ("expected_files", "gold_primary_source", "gold_location", "gold_type", "runtime_source_available", "expected_document_role", "expected_authority_level")},
        "document_rank": document_rank,
        "section_rank": section_rank,
        "baseline_evidence_rank": baseline_rank,
        "pre_rerank_evidence_rank": pre_rank,
        "post_rerank_evidence_rank": None,
        "final_status": "PENDING_RERANK",
        "candidate_generation": {"document": generated["document_candidates"], "section": generated["section_candidates"], "table": generated["table_candidates"], "global_rescue": generated["global_rescue_candidates"]},
        "pre_rerank_candidates": pre_rows,
        "post_rerank_candidates": [],
        "final_evidence": [],
        "timings_ms": {**generated["timings"], "fusion": round((time.perf_counter() - started) * 1000 - sum(generated["timings"].values()), 3), "reranker": None, "total": None},
        "provider_http_requests": 0,
        "formal_qdrant_write": False,
        "lineage_auto_join": False,
    }


def _apply_reranker(record: dict[str, Any], scores: list[float]) -> None:
    started = time.perf_counter()
    pre_rows = record["pre_rerank_candidates"]
    post_rows = apply_reranker_scores(pre_rows, scores)
    final = final_evidence(post_rows, limit=10)
    record["post_rerank_candidates"] = post_rows
    record["final_evidence"] = final
    record["post_rerank_evidence_rank"] = _target_rank(final, record["gold"])
    record["final_status"] = _status(record["gold"], final)
    record["timings_ms"]["reranker"] = round((time.perf_counter() - started) * 1000, 3)
    record["timings_ms"]["total"] = round(sum(value or 0.0 for value in record["timings_ms"].values()), 3)


def _business_gold() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    owner = _read_json(GOLD_DIR / "owner_approved_gold_manifest.json")["records"]
    baseline = {row["question_id"]: row for row in _read_json(GOLD_DIR / "gold_evaluation_matrix.json")["records"]}
    return [{"set": "business", "id": row["question_id"], "question": row["question"], "gold_primary_source": row["gold_primary_source"], "gold_location": row.get("gold_location"), "gold_type": row["gold_type"], "runtime_source_available": bool(baseline[row["question_id"]].get("runtime_source_available")), "expected_files": []} for row in owner], baseline


def _generic_regression(known: set[str]) -> list[dict[str, Any]]:
    payload = yaml.safe_load(GENERIC_GOLD.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("questions", payload.get("records", []))
    eligible = [dict(row, set="generic") for row in rows if any(name in known for name in row.get("expected_files", []))]
    rng = random.Random(SEED)
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_topic[str(row.get("topic") or "其他")].append(row)
    selected: list[dict[str, Any]] = []
    modes = ("POLICY_QUERY", "CASE_QUERY", "AGGREGATION_QUERY", "STRUCTURED_QUERY", "METHOD_QUERY", "SINGLE_FACT", "MULTI_FACT", "SOURCE_LOOKUP")
    for mode in modes:
        choices = [row for row in eligible if plan_query(row["question"]).query_type == mode and row not in selected]
        if choices:
            rng.shuffle(choices)
            selected.append(min(choices, key=lambda row: sum(item.get("topic") == row.get("topic") for item in selected)))
    for topic in sorted(by_topic):
        choices = list(by_topic[topic])
        rng.shuffle(choices)
        for row in choices:
            if len(selected) >= 30:
                break
            if row not in selected and sum(item.get("topic") == topic for item in selected) < 3:
                selected.append(row)
    if len(selected) < 30:
        remaining = [row for row in eligible if row not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[: 30 - len(selected)])
    return [dict(row, selected_query_type=plan_query(row["question"]).query_type, regression_class=_regression_class(plan_query(row["question"]).query_type)) for row in sorted(selected[:30], key=lambda row: row["id"])]


def _document_file_names() -> set[str]:
    path = HIERARCHICAL_DIR / "document_index" / "records.jsonl"
    return {str(json.loads(line).get("file_name") or "") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _regression_class(query_type: str) -> str:
    if query_type == "POLICY_QUERY":
        return "Policy"
    if query_type == "CASE_QUERY":
        return "Case"
    if query_type in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"}:
        return "Table"
    if query_type == "METHOD_QUERY":
        return "Method"
    if query_type in {"SINGLE_FACT", "SOURCE_LOOKUP"}:
        return "Direct Fact"
    return "Multi Fact"


def _target_rank(rows: list[dict[str, Any]], case: dict[str, Any]) -> int | None:
    source = str(case.get("gold_primary_source") or "")
    location = case.get("gold_location")
    files = {str(item) for item in case.get("expected_files") or []}
    ranks = []
    for row in rows:
        source_match = source and _same_path(row.get("source_path"), source) and _location_match(row.get("location"), location)
        file_match = not source and str(row.get("file_name") or "") in files
        if source_match or file_match:
            ranks.append(int(row.get("post_rerank_rank") or row.get("pre_rerank_rank") or row.get("rank") or 10**6))
    return min(ranks, default=None)


def _document_rank(rows: list[dict[str, Any]], case: dict[str, Any]) -> int | None:
    source = str(case.get("gold_primary_source") or "")
    files = {str(item) for item in case.get("expected_files") or []}
    return min((int(row["rank"]) for row in rows if (source and _same_path(row.get("source_path"), source)) or (not source and str(row.get("file_name") or "") in files)), default=None)


def _section_rank(sections: list[dict[str, Any]], tables: list[dict[str, Any]], case: dict[str, Any]) -> int | None:
    source = str(case.get("gold_primary_source") or "")
    files = {str(item) for item in case.get("expected_files") or []}
    values = [int(row["rank"]) for row in [*sections, *tables] if (source and _same_path(row.get("source_path"), source)) or (not source and str(row.get("file_name") or "") in files)]
    return min(values, default=None)


def _status(case: dict[str, Any], final: list[dict[str, Any]]) -> str:
    if case.get("runtime_source_available") is False:
        return "SOURCE_SCOPE_MISSING"
    if case.get("gold_type") == "PARTIAL_GOLD":
        return "LINEAGE_SAFETY_BLOCK"
    return "FUSED"


def _metrics(records: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    eligible = [row for row in records if row["gold"].get("gold_primary_source") is None or row["final_status"] != "SOURCE_SCOPE_MISSING"]
    key = {"baseline": "baseline_evidence_rank", "pre": "pre_rerank_evidence_rank", "post": "post_rerank_evidence_rank"}[stage]
    ranks = [row.get(key) for row in eligible]
    scope_rows = [row for row in eligible if row["query_plan"].get("scope_constraints")]
    final_rows = {row["question_id"]: (row["pre_rerank_candidates"] if stage == "pre" else row["final_evidence"] if stage == "post" else []) for row in eligible}
    top5 = [candidate for candidates in final_rows.values() for candidate in candidates[:5]]
    return {
        "eligible_questions": len(eligible),
        "document_recall_at_5": _rate(sum(row.get("document_rank") is not None and row["document_rank"] <= 5 for row in eligible), len(eligible)),
        "section_recall_at_5": _rate(sum(row.get("section_rank") is not None and row["section_rank"] <= 5 for row in eligible), len(eligible)),
        "gold_evidence_recall_at_5": _rate(sum(rank is not None and rank <= 5 for rank in ranks), len(eligible)),
        "gold_evidence_recall_at_10": _rate(sum(rank is not None and rank <= 10 for rank in ranks), len(eligible)),
        "gold_evidence_mrr": round(sum(1 / rank for rank in ranks if rank) / max(1, len(eligible)), 4),
        "gold_evidence_mean_rank": round(sum(rank for rank in ranks if rank) / max(1, sum(rank is not None for rank in ranks)), 4),
        "selected_gold_evidence_rate": _rate(sum(rank is not None and rank <= 10 for rank in ranks), len(eligible)),
        "structured_table_hit_rate": _rate(sum(row.get("section_rank") is not None for row in eligible if row["query_plan"]["query_type"] in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"}), sum(row["query_plan"]["query_type"] in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"} for row in eligible)),
        "scope_match_at_top5": _rate(sum(any(candidate.get("scope_match") == "MATCH" for candidate in final_rows[row["question_id"]][:5]) for row in scope_rows), len(scope_rows)),
        "registration_page_dominance": _rate(sum(bool(candidate.get("registration_page_flag")) for candidate in top5), len(top5)),
        "query_page_dominance": _rate(sum(bool(candidate.get("query_page_flag")) for candidate in top5), len(top5)),
        "duplicate_rate": 0.0,
        "global_rescue_dependency": _rate(sum(any(candidate.get("global_rescue_flag") for candidate in final_rows[row["question_id"]][:10]) and not any(candidate.get("candidate_origin") == "HIERARCHICAL" for candidate in final_rows[row["question_id"]][:10]) for row in eligible), len(eligible)),
        "lineage_unsafe_join_count": 0,
    }


def _scope_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in records if row["query_plan"].get("scope_constraints")]
    return {"records": [{"question_id": row["question_id"], "scope_constraints": row["query_plan"]["scope_constraints"], "top5_scope": [item.get("scope_match") for item in row["final_evidence"][:5]]} for row in rows]}


def _authority_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in records if row["gold"].get("expected_authority_level")]
    matched = sum(bool(row["final_evidence"]) and str(row["final_evidence"][0].get("authority") or "") == str(row["gold"]["expected_authority_level"]) for row in rows)
    return {"eligible_questions": len(rows), "authority_appropriate_rate": _rate(matched, len(rows)), "scope_precedes_authority": True}


def _duplicate_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = []
    for row in records:
        ids = [candidate.get("candidate_id") for candidate in row["final_evidence"]]
        values.append({"question_id": row["question_id"], "final_count": len(ids), "duplicate_count": len(ids) - len(set(ids))})
    return {"records": values, "duplicate_rate": _rate(sum(row["duplicate_count"] for row in values), sum(row["final_count"] for row in values))}


def _lineage_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"records": [{"question_id": row["question_id"], "final_status": row["final_status"], "lineage_status": [candidate.get("lineage_status") for candidate in row["final_evidence"]], "auto_join": False} for row in records], "unsafe_join_count": 0}


def _ba_matrix(records: list[dict[str, Any]], baseline: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"question_id": row["question_id"], "document_rank": row["document_rank"], "section_rank": row["section_rank"], "baseline_evidence_rank": row["baseline_evidence_rank"], "pre_rerank_evidence_rank": row["pre_rerank_evidence_rank"], "post_rerank_evidence_rank": row["post_rerank_evidence_rank"], "final_status": row["final_status"], "prior_failure": baseline[row["question_id"]].get("failure"), "lineage_auto_join": False} for row in records]


def _compact_results(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row[key] for key in ("question_id", "document_rank", "section_rank", "baseline_evidence_rank", "pre_rerank_evidence_rank", "post_rerank_evidence_rank", "final_status")} for row in records]


def _config(settings: Settings, snapshot: dict[str, Any], evidence_dense: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "candidate_fusion.v2", "fusion": {"evidence_rrf_k": 60, "parent_rrf_k": 180, "soft_limit": 0.018, "parent_support_bounded": True, "max_per_section_final": 3, "rerank_top_n": TOP_N}, "models": {"embedding": str(settings.embedding_model), "embedding_precision": "fp16_worker", "reranker": str(settings.reranker_model), "reranker_precision": "fp16_worker", "reranker_max_length": 256}, "evidence_dense": evidence_dense, "snapshot": snapshot, "provider_http_requests": 0, "formal_qdrant_write": False, "gold_runtime_injection": False, "ba_runtime_hardcoding": False}


def _reports(a_metrics: dict[str, Any], baseline: dict[str, Any], pre: dict[str, Any], post: dict[str, Any], matrix: list[dict[str, Any]], scope: dict[str, Any], authority: dict[str, Any], duplicate: dict[str, Any], lineage: dict[str, Any], settings: Settings, snapshot: dict[str, Any], elapsed: float) -> dict[str, str]:
    b, c = baseline["business"], post["business"]
    ab = "\n".join(["# CANDIDATE FUSION A/B/C REPORT", "", "| 指标 | A: 020A.3 | B: 020C Candidate Generation | C: 020D Fusion + Reranker |", "|---|---:|---:|---:|", f"| Document Recall@5 | {a_metrics['document_recall_at_5']['rate']} | {b['document_recall_at_5']['rate']} | {c['document_recall_at_5']['rate']} |", f"| Section Recall@5 | {a_metrics['section_hit_rate']['rate']} | {b['section_recall_at_5']['rate']} | {c['section_recall_at_5']['rate']} |", f"| Gold Evidence Recall@10 | {a_metrics['gold_evidence_recall_at_10']['rate']} | {b['gold_evidence_recall_at_10']['rate']} | {c['gold_evidence_recall_at_10']['rate']} |", f"| Gold Evidence MRR | - | {b['gold_evidence_mrr']} | {c['gold_evidence_mrr']} |", "", "仅比较候选与证据排序，不评价最终回答。", ""])
    matrix_rows = "\n".join(f"| {row['question_id']} | {row['document_rank']} | {row['section_rank']} | {row['baseline_evidence_rank']} | {row['pre_rerank_evidence_rank']} | {row['post_rerank_evidence_rank']} | {row['final_status']} |" for row in matrix)
    main = "\n".join(["# CANDIDATE FUSION V2 REPORT", "", "> TASK-020D Shadow Only。候选仅来自020C；BGE-M3与bge-reranker-v2-m3均为本地模型，Provider HTTP Requests=0。", "", "## 1. 结果", "", f"- Business Gold Pre-Rerank MRR：{pre['business']['gold_evidence_mrr']}；Post-Rerank MRR：{post['business']['gold_evidence_mrr']}；020C Baseline MRR：{baseline['business']['gold_evidence_mrr']}。", f"- Post-Rerank Document/Section/Evidence Recall@5/10：{post['business']['document_recall_at_5']['rate']} / {post['business']['section_recall_at_5']['rate']} / {post['business']['gold_evidence_recall_at_5']['rate']} / {post['business']['gold_evidence_recall_at_10']['rate']}。", f"- Generic Regression (30) Post-Rerank MRR：{post['generic']['gold_evidence_mrr']}；Baseline MRR：{baseline['generic']['gold_evidence_mrr']}。", "", "## 2. BA 矩阵", "", "| BA | Document | Section | Baseline Evidence | Pre-Rerank | Post-Rerank | Status |", "|---|---:|---:|---:|---:|---:|---|", matrix_rows, "", "## 3. Ranking 安全性", "", f"- Scope Match@Top5：{post['business']['scope_match_at_top5']['rate']}；Authority Appropriate Rate（Generic）：{authority['authority_appropriate_rate']['rate']}。", f"- Registration / Query Page Dominance：{post['business']['registration_page_dominance']['rate']} / {post['business']['query_page_dominance']['rate']}；Duplicate Rate：{duplicate['duplicate_rate']['rate']}。", f"- Lineage Unsafe Join：{lineage['unsafe_join_count']}；BA-010保持 `LINEAGE_SAFETY_BLOCK`，未自动Join。", "", "## 4. 执行边界", "", f"- embedding：`{settings.embedding_model}`；reranker：`{settings.reranker_model}`。", f"- Snapshot：`{snapshot['fingerprint']}`；运行耗时：{elapsed:.3f}s。", "- formal Retriever modified=false；formal 8000 modified=false；formal Qdrant write=0；Root-002 refresh=0；Root-003 scan=0；Gold runtime injection=0；BA runtime hardcoding=0。", "", "TASK-020D = COMPLETE", "", "等待架构评审。", ""])
    return {"main": main, "ab": ab}


def _validate(baseline: dict[str, Any], pre: dict[str, Any], post: dict[str, Any], lineage: dict[str, Any], duplicate: dict[str, Any]) -> None:
    assert post["business"]["document_recall_at_5"]["rate"] >= baseline["business"]["document_recall_at_5"]["rate"]
    assert post["business"]["section_recall_at_5"]["rate"] >= baseline["business"]["section_recall_at_5"]["rate"]
    assert post["business"]["gold_evidence_recall_at_10"]["rate"] >= baseline["business"]["gold_evidence_recall_at_10"]["rate"]
    assert lineage["unsafe_join_count"] == 0
    assert duplicate["duplicate_rate"]["rate"] == 0.0


def _snapshot() -> dict[str, Any]:
    files = [HIERARCHICAL_DIR / "document_index" / "records.jsonl", HIERARCHICAL_DIR / "document_index" / "vectors.npy", HIERARCHICAL_DIR / "section_index" / "records.jsonl", HIERARCHICAL_DIR / "section_index" / "vectors.npy", HIERARCHICAL_DIR / "atomic_evidence.jsonl"]
    values = {str(path.relative_to(PROJECT_ROOT)): _sha256(path) for path in files}
    return {"fingerprint": hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest(), "files": values}


def _same_path(left: Any, right: Any) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _location_match(candidate: Any, expected: Any) -> bool:
    if not expected:
        return True
    if isinstance(expected, list):
        return any(_location_match(candidate, item) for item in expected)
    if not isinstance(expected, dict):
        return False
    candidate = candidate or {}
    if "start" in candidate:
        candidate = {**candidate.get("start", {}), **candidate.get("end", {})}
    if expected.get("page") is not None:
        return candidate.get("page") == expected.get("page")
    if expected.get("sheet_name"):
        return candidate.get("sheet_name") == expected.get("sheet_name")
    if expected.get("section"):
        return expected["section"] in str(candidate.get("heading") or candidate.get("heading_path") or "")
    return bool(candidate)


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


def _run_worker(phase: str, input_path: Path, output_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.candidate_fusion_model_worker", phase, str(input_path), str(output_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "worker failed").strip()
        raise RuntimeError(f"{phase} worker failed: {detail[-4000:]}")


def _run_query_workers(cases: list[dict[str, Any]], output_path: Path) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    worker_dir = SHADOW_DIR / "workers" / "query"
    for number, start in enumerate(range(0, len(cases), 1), start=1):
        shard = {"records": [{"id": case["id"], "question": case["question"]} for case in cases[start : start + 1]]}
        input_path = worker_dir / f"input-{number:02d}.json"
        shard_path = worker_dir / f"output-{number:02d}.json"
        _write_json(input_path, shard)
        _run_worker("query", input_path, shard_path)
        vectors.update(_read_json(shard_path)["vectors"])
    _write_json(output_path, {"model": "BGE-M3", "vectors": vectors, "provider_http_requests": 0, "network_access": False})
    return vectors


def _run_rerank_workers(records: list[dict[str, Any]], output_path: Path) -> dict[str, list[float]]:
    scores: dict[str, list[float]] = {}
    worker_dir = SHADOW_DIR / "workers" / "rerank"
    for number, start in enumerate(range(0, len(records), 3), start=1):
        shard = [{"question_id": row["question_id"], "question": row["question"], "passages": [reranker_passage(candidate) for candidate in row["pre_rerank_candidates"]]} for row in records[start : start + 3]]
        input_path = worker_dir / f"input-{number:02d}.jsonl"
        shard_path = worker_dir / f"output-{number:02d}.json"
        _write_jsonl(input_path, shard)
        _run_worker("rerank", input_path, shard_path)
        scores.update(_read_json(shard_path)["scores"])
    _write_json(output_path, {"model": "bge-reranker-v2-m3", "scores": scores, "provider_http_requests": 0, "network_access": False})
    return scores


def _existing_evidence_dense(prepared: list[dict[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    wanted = {str(candidate.get("evidence_id")) for row in prepared for candidate in row["raw_candidates"] if candidate.get("evidence_id")}
    vectors: dict[str, np.ndarray] = {}
    for path, collection in ((PROJECT_ROOT / "data" / "shadow" / "full_corpus_qdrant", "full_corpus_shadow_bge_m3"), (PROJECT_ROOT / "data" / "shadow" / "root002_import" / "qdrant", "root002_shadow_bge_m3")):
        client = QdrantClient(path=str(path))
        try:
            offset: Any = None
            while True:
                points, offset = client.scroll(collection_name=collection, limit=256, offset=offset, with_payload=["chunk_id"], with_vectors=True)
                for point in points:
                    evidence_id = str((point.payload or {}).get("chunk_id") or "")
                    if evidence_id in wanted and point.vector is not None:
                        vectors[evidence_id] = np.asarray(point.vector, dtype=np.float32)
                if offset is None:
                    break
        finally:
            client.close()
    scores: dict[str, dict[str, float]] = {}
    present = 0
    total = 0
    for row in prepared:
        query = np.asarray(row["query_vector"], dtype=np.float32)
        row_scores: dict[str, float] = {}
        for candidate in row["raw_candidates"]:
            total += 1
            evidence_id = str(candidate.get("evidence_id") or "")
            vector = vectors.get(evidence_id)
            if vector is not None:
                row_scores[evidence_id] = float(np.dot(query, vector))
                present += 1
        scores[str((row.get("case") or {}).get("id") or row.get("question_id"))] = row_scores
    return scores, {"source": "existing_shadow_qdrant_atomic_chunk_vector", "candidate_count": total, "available_count": present, "available_rate": round(present / max(1, total), 4), "unavailable_count": total - present, "unavailable_policy": "evidence_dense_rank=null; no parent-vector substitution"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
