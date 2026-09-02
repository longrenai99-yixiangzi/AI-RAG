from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "shadow" / "trial_cycle_01" / "business_acceptance_registry.jsonl"
SOURCES = ROOT / "data" / "shadow" / "trial_cycle_01" / "source_closure_register.jsonl"
FEEDBACK_TRIALS = ROOT / "data" / "shadow" / "trial_cycle_01" / "trial_feedback_questions.jsonl"
OUT = ROOT / "evaluation" / "trial_cycle_01"
REPORT = ROOT / "docs" / "TRIAL_CYCLE_01_INITIAL_REGRESSION.md"
SOURCE_REPORT = ROOT / "docs" / "TRIAL_CYCLE_01_SOURCE_CLOSURE_REPORT.md"
TRIAL_URL = "http://127.0.0.1:8010/api/v2/query"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _same_path(left: Any, right: Any) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _fact_present(fact: str, answer: str) -> bool:
    normalize = lambda value: re.sub(r"[\s、，,；;：:（）()]+", "", value)
    return normalize(fact) in normalize(answer)


def _evaluate(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    answer = str(result.get("answer") or "")
    citations = result.get("citations") or []
    expected_source = item.get("correct_source_path")
    source_hit = None if not expected_source else any(_same_path(expected_source, citation.get("source_path")) for citation in citations)
    missing_facts = [fact for fact in item.get("key_facts", []) if not _fact_present(fact, answer)]
    strict = bool(item.get("regression_enabled"))
    passed = (result.get("answer_status") == item.get("expected_runtime_status") and source_hit is True and not missing_facts) if strict else None
    return {
        "question_id": item["question_id"],
        "registry_set": item["registry_set"],
        "question": item["question"],
        "owner_confirmation_status": item["owner_confirmation_status"],
        "source_governance_status": item["source_governance_status"],
        "runtime_status": result.get("answer_status"),
        "expected_runtime_status": item.get("expected_runtime_status"),
        "citation_source_hit": source_hit,
        "missing_key_facts": missing_facts,
        "strict_regression": strict,
        "regression_status": "PASSED" if passed is True else "FAILED" if passed is False else "OBSERVED_ONLY",
        "provider_http_requests": result.get("provider_http_requests"),
        "gold_runtime_injection": 0,
    }


def _run_question(question: str) -> dict[str, Any]:
    payload = json.dumps({"question": question, "trial_user": "reviewer-001"}, ensure_ascii=False).encode("utf-8")
    request = Request(TRIAL_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _report(rows: list[dict[str, Any]]) -> str:
    gold = [row for row in rows if row["registry_set"] == "BUSINESS_GOLD"]
    trial = [row for row in rows if row["registry_set"] == "TRIAL_QUESTION"]
    gold_passed = sum(row["regression_status"] == "PASSED" for row in gold)
    statuses = {status: sum(row["runtime_status"] == status for row in rows) for status in sorted({row["runtime_status"] for row in rows})}
    lines = [
        "# TRIAL-CYCLE-01 初始回归", "",
        "> Business Gold严格验收；Trial Questions仅记录运行现象，不作为准确率分母。全程只使用8010 Shadow，Provider HTTP Requests=0。", "",
        "## 结果", "",
        f"- Business Gold：{gold_passed}/{len(gold)} 通过。",
        f"- Trial Questions：{len(trial)} 题，仅观察。",
        f"- 运行状态分布：`{statuses}`。", "",
        "## 明细", "", "| ID | Set | Runtime | Strict Result | Source Hit | Missing Facts |", "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['question_id']} | {row['registry_set']} | {row['runtime_status']} | {row['regression_status']} | {row['citation_source_hit']} | {', '.join(row['missing_key_facts']) or '-'} |")
    lines += ["", "## 解释", "", "- Trial题的失败不自动归咎于Retriever；必须先进入Failure Diagnosis与Source Closure。", "- Source Scope Missing是治理状态，不等价于文件不存在。", "- 本报告不触发任何正式知识发布。", ""]
    return "\n".join(lines)


def _source_report(rows: list[dict[str, Any]]) -> str:
    lines = ["# TRIAL-CYCLE-01 Source Closure 运行状态", "", "| ID | Source Status | Runtime Status | Regression | Next Action |", "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['question_id']} | {row['source_status']} | {row['runtime_status']} | {row['last_regression_status']} | {row['next_action']} |")
    lines += ["", "- `SOURCE_SCOPE_MISSING` 仅表示当前8010没有获准可用正文；不得将其描述为原始文件不存在。", "- 本报告不触发Root审批、导入或正式知识发布。", ""]
    return "\n".join(lines)


def _feedback_sources(items: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = {row["question_id"] for row in sources}
    for item in items:
        if item["question_id"] in known:
            continue
        sources.append({
            "schema_version": "trial-cycle-01.source-closure.v1",
            "question_id": item["question_id"],
            "question": item["question"],
            "source_status": item["source_governance_status"],
            "correct_source_path": item.get("correct_source_path"),
            "correct_source_file_name": item.get("correct_source_file_name"),
            "correct_location": item.get("correct_location"),
            "source_governance_status": item["source_governance_status"],
            "runtime_status": "NOT_YET_RUN",
            "next_action": "等待业务负责人确认正确来源、位置和关键事实。",
            "created_from": item["created_from"],
            "formal_knowledge_publish": False,
        })
    return sources


def main() -> int:
    items = _read_jsonl(REGISTRY) + (_read_jsonl(FEEDBACK_TRIALS) if FEEDBACK_TRIALS.exists() else [])
    rows = [_evaluate(item, _run_question(item["question"])) for item in items]
    result_by_id = {row["question_id"]: row for row in rows}
    sources = _feedback_sources(items, _read_jsonl(SOURCES))
    for source in sources:
        runtime = result_by_id[source["question_id"]]
        source["runtime_status"] = runtime["runtime_status"]
        source["last_regression_status"] = runtime["regression_status"]
        source["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    _write_jsonl(SOURCES, sources)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "initial_regression.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows, "provider_http_requests": 0, "formal_knowledge_publish": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(_report(rows), encoding="utf-8")
    SOURCE_REPORT.write_text(_source_report(sources), encoding="utf-8")
    print(json.dumps({"questions": len(rows), "business_gold": sum(row["registry_set"] == "BUSINESS_GOLD" for row in rows), "provider_http_requests": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
