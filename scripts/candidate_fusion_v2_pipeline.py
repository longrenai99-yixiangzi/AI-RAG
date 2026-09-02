from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.retrieval.candidate_fusion_v2 import reranker_passage
from app.retrieval.hierarchical_v1 import HierarchicalIndex
from scripts.run_candidate_fusion_v2 import (
    EVAL_DIR,
    GOLD_DIR,
    HIERARCHICAL_DIR,
    SHADOW_DIR,
    _apply_reranker,
    _authority_analysis,
    _ba_matrix,
    _business_gold,
    _compact_results,
    _config,
    _document_file_names,
    _duplicate_analysis,
    _existing_evidence_dense,
    _fuse_prepared,
    _generic_regression,
    _lineage_analysis,
    _metrics,
    _prepare_case,
    _read_json,
    _reports,
    _scope_analysis,
    _snapshot,
    _validate,
    _write_json,
    _write_jsonl,
)
from app.retrieval.query_planner_v1 import plan_query


CONTEXT = SHADOW_DIR / "pipeline_context.json"
CASES = SHADOW_DIR / "cases.json"
QUERY_VECTORS = SHADOW_DIR / "query_vectors.json"
PREPARED = SHADOW_DIR / "prepared_candidates.jsonl"
EVIDENCE_SCORES = SHADOW_DIR / "evidence_dense_scores.json"
PRE_RECORDS = SHADOW_DIR / "pre_rerank_records.jsonl"
RERANK_INPUT = SHADOW_DIR / "pre_rerank_inputs.jsonl"
RERANK_SCORES = SHADOW_DIR / "reranker_scores.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "retrieve_fuse", "finalize"))
    args = parser.parse_args()
    if args.phase == "prepare":
        _prepare()
    elif args.phase == "retrieve_fuse":
        _retrieve_fuse()
    else:
        _finalize()
    return 0


def _prepare() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    business, _ = _business_gold()
    generic = _generic_regression(_document_file_names())
    context = {"snapshot": _snapshot(), "cases": [*business, *generic], "generic_manifest": {"seed": 20260830, "records": generic}}
    _write_json(CONTEXT, context)
    _write_json(CASES, {"records": context["cases"]})
    _write_json(EVAL_DIR / "generic_regression_manifest.json", context["generic_manifest"])


def _retrieve_fuse() -> None:
    context = _read_json(CONTEXT)
    vectors = _read_json(QUERY_VECTORS)["vectors"]
    index = HierarchicalIndex.load(HIERARCHICAL_DIR)
    try:
        prepared = [_prepare_case(index, case, plan_query(case["question"]), vectors[str(case["id"])]) for case in context["cases"]]
        atomic_by_id = {str(row.get("evidence_id")): row for row in index.atomic if row.get("evidence_id")}
        scores, evidence_dense = _existing_evidence_dense(prepared)
        records = [_fuse_prepared(row, atomic_by_id, scores.get(str(row["case"]["id"]), {})) for row in prepared]
    finally:
        del index
    _write_jsonl(PREPARED, prepared)
    _write_json(EVIDENCE_SCORES, {"scores": scores, **evidence_dense})
    _write_jsonl(PRE_RECORDS, records)
    _write_jsonl(RERANK_INPUT, [{"question_id": row["question_id"], "question": row["question"], "passages": [reranker_passage(candidate) for candidate in row["pre_rerank_candidates"]]} for row in records])
    context["evidence_dense"] = evidence_dense
    _write_json(CONTEXT, context)


def _finalize() -> None:
    started = time.perf_counter()
    context = _read_json(CONTEXT)
    settings = Settings.load()
    records = _read_jsonl(PRE_RECORDS)
    scores = _read_json(RERANK_SCORES)["scores"]
    for record in records:
        _apply_reranker(record, scores.get(str(record["question_id"]), []))
    business, business_baseline = _business_gold()
    ba_records = [row for row in records if row["set"] == "business"]
    generic_records = [row for row in records if row["set"] == "generic"]
    pre = {"business": _metrics(ba_records, "pre"), "generic": _metrics(generic_records, "pre")}
    post = {"business": _metrics(ba_records, "post"), "generic": _metrics(generic_records, "post")}
    baseline = {"business": _metrics(ba_records, "baseline"), "generic": _metrics(generic_records, "baseline")}
    acceptance = _acceptance(baseline, post)
    post["acceptance"] = acceptance
    scope = _scope_analysis(records)
    authority = _authority_analysis(generic_records)
    duplicate = _duplicate_analysis(records)
    lineage = _lineage_analysis(ba_records)
    matrix = _ba_matrix(ba_records, business_baseline)
    _write_json(EVAL_DIR / "fusion_config.json", _config(settings, context["snapshot"], context["evidence_dense"]))
    _write_json(EVAL_DIR / "ba_fusion_matrix.json", {"records": matrix})
    _write_json(EVAL_DIR / "generic_regression_results.json", {"baseline": baseline["generic"], "pre_rerank": pre["generic"], "post_rerank": post["generic"], "records": _compact_results(generic_records)})
    _write_json(EVAL_DIR / "pre_rerank_metrics.json", pre)
    _write_json(EVAL_DIR / "post_rerank_metrics.json", post)
    _write_json(EVAL_DIR / "scope_ranking_analysis.json", scope)
    _write_json(EVAL_DIR / "authority_ranking_analysis.json", authority)
    _write_json(EVAL_DIR / "duplicate_analysis.json", duplicate)
    _write_json(EVAL_DIR / "lineage_safety_validation.json", lineage)
    _write_jsonl(EVAL_DIR / "fusion_traces.jsonl", records)
    _write_json(SHADOW_DIR / "index_snapshot.json", context["snapshot"])
    reports = _reports(_read_json(GOLD_DIR / "retrieval_metrics.json"), baseline, pre, post, matrix, scope, authority, duplicate, lineage, settings, context["snapshot"], time.perf_counter() - started)
    reports["main"] += "\n## 验收结论\n\n" + f"**{acceptance['result']}**：{acceptance['reason']}\n\n"
    (Path(__file__).resolve().parents[1] / "docs" / "CANDIDATE_FUSION_V2_REPORT.md").write_text(reports["main"], encoding="utf-8")
    (Path(__file__).resolve().parents[1] / "docs" / "CANDIDATE_FUSION_AB_REPORT.md").write_text(reports["ab"], encoding="utf-8")
    _validate(baseline, pre, post, lineage, duplicate)
    print(json.dumps({"business_post_mrr": post["business"]["gold_evidence_mrr"], "provider_http_requests": 0}, ensure_ascii=False))


def _acceptance(baseline: dict[str, Any], post: dict[str, Any]) -> dict[str, str]:
    before = baseline["business"]["gold_evidence_mrr"]
    after = post["business"]["gold_evidence_mrr"]
    if after > before:
        return {"result": "PASS", "reason": f"Gold Evidence MRR improved from {before} to {after}."}
    return {"result": "NOT_PASSED_MRR_NO_IMPROVEMENT", "reason": f"Gold Evidence MRR stayed at {after}; TASK-020D cannot claim ranking success."}


if __name__ == "__main__":
    raise SystemExit(main())
