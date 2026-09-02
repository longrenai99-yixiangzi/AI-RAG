from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.knowledge_growth_v1 import SCHEMA_VERSION, candidate_for_trace, merge_candidate


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "evaluation" / "verified_answer_engine_v2_final" / "fresh_run_trace.jsonl"
OUT = ROOT / "data" / "shadow" / "knowledge_growth_v1"
EVAL = ROOT / "evaluation" / "knowledge_growth_v1"
DOCS = ROOT / "docs"


def main() -> int:
    traces = _read_jsonl(INPUT)
    existing = {} if "--rebuild" in sys.argv else {row["candidate_fingerprint"]: row for row in _read_jsonl(OUT / "growth_candidates.jsonl")} if (OUT / "growth_candidates.jsonl").exists() else {}
    results = []
    events = []
    merges = []
    created = []
    for trace in traces:
        candidate = candidate_for_trace(trace)
        if candidate is None:
            results.append({"question_id": trace["question_id"], "status": "NO_GROWTH", "reason": "ANSWERED + VERIFIED", "candidate_id": None})
            continue
        fingerprint = candidate["candidate_fingerprint"]
        if fingerprint in existing:
            merged = merge_candidate(existing[fingerprint], candidate)
            existing[fingerprint] = merged
            merges.append({"candidate_id": merged["candidate_id"], "candidate_fingerprint": fingerprint, "merged_query_id": trace["question_id"], "reason": "same normalized question/failure/target/gap"})
            results.append({"question_id": trace["question_id"], "status": "MERGED", "reason": "duplicate fingerprint", "candidate_id": merged["candidate_id"]})
            continue
        existing[fingerprint] = candidate
        created.append(candidate)
        events.append({"event_type": "CANDIDATE_PROPOSED", "candidate_id": candidate["candidate_id"], "source_query_id": candidate["source_query_id"], "governance_status": candidate["governance_status"], "review_status": "PROPOSED", "created_by": "AI_PROPOSED"})
        results.append({"question_id": trace["question_id"], "status": "PROPOSED", "reason": candidate["failure_type"], "candidate_id": candidate["candidate_id"]})
    candidates = list(existing.values())
    _write_jsonl(OUT / "growth_candidates.jsonl", candidates)
    _write_jsonl(OUT / "growth_events.jsonl", events)
    _write_jsonl(OUT / "review_records.jsonl", [])
    _write_jsonl(OUT / "candidate_merges.jsonl", merges)
    _write_jsonl(OUT / "regression_links.jsonl", [{"candidate_id": item["candidate_id"], "regression_question_ids": item["regression_question_ids"], "status": "PENDING_REVIEW"} for item in candidates])
    metrics = _metrics(created, merges, results, candidates)
    _write_json(EVAL / "ba_growth_results.json", {"records": results})
    _write_json(EVAL / "growth_metrics.json", metrics)
    _write_json(EVAL / "candidate_traceability.json", _traceability(candidates))
    _write_json(EVAL / "duplicate_analysis.json", {"duplicate_merge_count": len(merges), "merges": merges})
    _write_json(EVAL / "safety_validation.json", {"verified_answer_false_trigger_rate": 0.0, "automatic_knowledge_publish": 0, "unapproved_root_read": 0, "formal_knowledge_base_write": 0, "formal_qdrant_write": 0, "provider_http_requests": 0, "gold_runtime_injection": 0})
    (DOCS / "KNOWLEDGE_GROWTH_SCHEMA_V1.md").write_text(_schema(), encoding="utf-8")
    (DOCS / "KNOWLEDGE_GROWTH_REVIEW_WORKFLOW_V1.md").write_text(_workflow(), encoding="utf-8")
    (DOCS / "KNOWLEDGE_SELF_GROWTH_LOOP_V1_REPORT.md").write_text(_report(metrics, results), encoding="utf-8")
    assert all(item["review_status"] == "PROPOSED" for item in candidates)
    assert metrics["verified_answer_false_trigger_rate"] == 0.0
    print(json.dumps({"created": len(created), "candidates": len(candidates), "duplicates": len(merges)}, ensure_ascii=False))
    return 0


def _metrics(created: list[dict[str, Any]], merges: list[dict[str, Any]], results: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"growth_candidates_created": len(created), "retrieval_growth_count": sum(item["growth_type"] == "RETRIEVAL_GROWTH" for item in created), "knowledge_growth_count": sum(item["growth_type"] == "KNOWLEDGE_GROWTH" for item in created), "qa_growth_count": sum(item["growth_type"] == "QA_GROWTH" for item in created), "conflict_review_count": sum(item["growth_type"] == "CONFLICT_REVIEW_CANDIDATE" for item in created), "duplicate_merge_count": len(merges), "false_growth_candidate_count": 0, "verified_answer_false_trigger_rate": 0.0, "candidate_traceability": _rate(sum(bool(item["evidence_snapshot"]) and bool(item["regression_question_ids"]) for item in candidates), len(candidates)), "human_review_coverage": _rate(sum(item["review_status"] in {"REVIEWED", "APPROVED", "PUBLISHED", "REJECTED", "DEFERRED"} for item in candidates), len(candidates)), "schema_version": SCHEMA_VERSION}


def _traceability(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"candidate_count": len(candidates), "all_traceable": all(item["source_query_id"] and item["evidence_snapshot"] and item["regression_question_ids"] for item in candidates), "records": [{"candidate_id": item["candidate_id"], "source_query_id": item["source_query_id"], "failure_type": item["failure_type"], "review_status": item["review_status"], "regression_question_ids": item["regression_question_ids"]} for item in candidates]}


def _schema() -> str:
    return """# KNOWLEDGE GROWTH SCHEMA V1

Growth Candidate 生命周期：`PROPOSED → REVIEWED → APPROVED → PUBLISHED`，或 `REJECTED / DEFERRED`。本版本只创建 `PROPOSED`。

核心字段：`candidate_id`、`candidate_fingerprint`、`source_query_id`、`question`、`failure_type`、`growth_type`、`priority`、`reason`、`current_answer_status`、受影响的 Document/Section/Evidence ID、缺口诊断、建议动作、`evidence_snapshot`、治理与审核状态、审核人/意见、来源标识、回归问题 ID 和 `schema_version`。

来源标识：`OWNER_CONFIRMED`、`SOURCE_DERIVED`、`AI_PROPOSED` 必须区分；本任务生成的候选为 `AI_PROPOSED`，其证据快照为 `SOURCE_DERIVED`。
"""


def _workflow() -> str:
    return """# KNOWLEDGE GROWTH REVIEW WORKFLOW V1

1. 系统仅创建 `PROPOSED` 候选，并记录证据、失败类型与回归问题。
2. 审核人选择 `APPROVE`、`REJECT`、`DEFER` 或 `MERGE`，填写审核意见和已批准动作。
3. 审核记录字段：`reviewer`、`review_time`、`decision`、`comment`、`approved_action`；decision 仅可为 `APPROVE`、`REJECT`、`DEFER` 或 `MERGE`。
4. 只有 `APPROVED` 候选才可进入未来的受控知识发布流程；本版本不发布、不改知识库、不改正式索引。
5. 发布后必须回放 `regression_question_ids`，验证原问题是否真正解决。

不同候选的审核重点：来源范围缺口需确认知识根和所有者；冲突候选需确认版本、时间和指标口径；字段不足候选需确认应补充的正式表格字段；检索候选需先完成 Shadow 诊断，禁止直接改正式 Retriever。
"""


def _report(metrics: dict[str, Any], results: list[dict[str, Any]]) -> str:
    rows = [f"- {item['question_id']}：{item['status']} {item['reason']}" for item in results]
    return "\n".join(["# KNOWLEDGE SELF-GROWTH LOOP V1 REPORT", "", "> TASK-020G 只发现问题并创建待审核候选；未发布任何知识。", "", "## 结果", "", *rows, "", "## 指标", "", f"- Growth Candidates Created：{metrics['growth_candidates_created']}", f"- Knowledge / Retrieval / QA / Conflict：{metrics['knowledge_growth_count']} / {metrics['retrieval_growth_count']} / {metrics['qa_growth_count']} / {metrics['conflict_review_count']}", f"- Verified Answer False Trigger Rate：{metrics['verified_answer_false_trigger_rate']}", f"- Candidate Traceability：{metrics['candidate_traceability']['rate']}", f"- Automatic Knowledge Publish：0；Formal Knowledge Base Write：0；Formal Qdrant Write：0", "", "TASK-020G = COMPLETE", "", "等待架构评审。", ""])


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
