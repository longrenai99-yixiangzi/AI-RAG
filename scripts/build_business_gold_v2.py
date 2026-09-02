from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build V2 business Gold review artifacts from persisted Shadow runs.")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "v1_business_acceptance",
    )
    parser.add_argument(
        "--locator-audit",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "atomic_evidence" / "gold_locator_audit.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "business_gold_v2",
    )
    args = parser.parse_args()

    locator_by_id = _load_locator_audit(args.locator_audit)
    rows = []
    for path in sorted(args.baseline_dir.glob("BA-*.json")):
        baseline = json.loads(path.read_text(encoding="utf-8"))
        question_id = str(baseline.get("question_id") or path.stem)
        locator = locator_by_id.get(question_id, {})
        candidates = list(locator.get("candidates") or [])
        rows.append(_gold_draft(baseline, locator, candidates))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "business_gold.v2.draft",
        "purpose": "人工确认正确文件、位置、范围、权威性和关键 Claim；候选不等于 Gold。",
        "source": {
            "baseline_dir": str(args.baseline_dir.resolve()),
            "locator_audit": str(args.locator_audit.resolve()),
            "baseline_kind": "PERSISTED_SHADOW_RESULTS",
            "fresh_run_records": sum(bool(item["baseline_observation"]["fresh_run"]) for item in rows),
            "fresh_run_required_after_gold_confirmation": True,
        },
        "records": rows,
    }
    atlas = {
        "schema_version": "failure_atlas.v2.preliminary",
        "purpose": "基于已持久化 Shadow 结果的初步归因；业务 Gold 确认后才可升级为最终归因。",
        "records": [_failure_record(row) for row in rows],
    }
    review_queue = {
        "schema_version": "gold_review_queue.v2",
        "status": "PENDING_BUSINESS_OWNER_REVIEW",
        "items": [_review_item(row) for row in rows],
    }
    _write_json(args.output_dir / "gold_manifest.json", manifest)
    _write_json(args.output_dir / "ba_failure_atlas.json", atlas)
    _write_json(args.output_dir / "gold_review_queue.json", review_queue)

    report_path = PROJECT_ROOT / "docs" / "BUSINESS_GOLD_V2_REPORT.md"
    report_path.write_text(_render_report(manifest, atlas, review_queue), encoding="utf-8")
    print(
        json.dumps(
            {
                "questions": len(rows),
                "gold_statuses": _counts(row["gold_status"] for row in rows),
                "failure_types": _counts(item["preliminary_failure_type"] for item in atlas["records"]),
                "fresh_run_records": manifest["source"]["fresh_run_records"],
                "output_dir": str(args.output_dir.resolve()),
                "report": str(report_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _load_locator_audit(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {
        str(value.get("question_id")): value
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for value in [json.loads(line)]
    }


def _gold_draft(
    baseline: dict[str, Any], locator: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    route = baseline.get("route") or {}
    return {
        "question_id": str(baseline.get("question_id")),
        "question": str(baseline.get("question") or ""),
        "answerable": "PENDING_BUSINESS_CONFIRMATION",
        "expected_answer_type": None,
        "expected_fact_mode": None,
        "expected_scope": None,
        "expected_authority": None,
        "expected_files": [],
        "expected_locations": [],
        "expected_fields": [],
        "expected_subquestions": [],
        "expected_claims": [],
        "must_include_evidence": [],
        "must_not_use_files": [],
        "gold_status": "GOLD_UNCONFIRMED",
        "business_owner_review": {
            "review_status": "PENDING",
            "reviewer": None,
            "reviewed_at": None,
        },
        "baseline_observation": {
            "fresh_run": bool(baseline.get("fresh_run")),
            "final_status": baseline.get("final_status"),
            "route": route.get("route") if isinstance(route, dict) else None,
            "answer_path": baseline.get("answer_path"),
            "evidence_count": len(baseline.get("top_evidence") or baseline.get("selected_evidence") or []),
        },
        "proposed_query_facets": locator.get("query_facets") or {},
        "proposed_candidates": candidates[:5],
        "proposed_excluded_candidates": [
            {"file_name": item.get("file_name"), "location": item.get("location"), "reason": "REGISTRATION_PAGE"}
            for item in candidates
            if item.get("registration_only")
        ][:5],
    }


def _failure_record(gold: dict[str, Any]) -> dict[str, Any]:
    observation = gold["baseline_observation"]
    candidates = gold["proposed_candidates"]
    status = str(observation.get("final_status") or "UNKNOWN")
    registration_only = bool(candidates and candidates[0].get("registration_only"))
    if status == "FACT_RESULT":
        failure_type, confidence = "NONE", "MEDIUM"
    elif registration_only:
        failure_type, confidence = "SOURCE_MISSING", "MEDIUM"
    elif status == "STRUCTURE_INVALID":
        failure_type, confidence = "GENERATION_FAILURE", "MEDIUM"
    elif status in {"NO_EVIDENCE", "PARTIAL_EVIDENCE"}:
        failure_type, confidence = "EVIDENCE_MISSED", "LOW"
    elif status in {"GENERATED", "EVIDENCE_ONLY"}:
        failure_type, confidence = "PENDING_BUSINESS_REVIEW", "LOW"
    else:
        failure_type, confidence = "UNCONFIRMED", "LOW"
    return {
        "question_id": gold["question_id"],
        "observed_final_status": status,
        "preliminary_failure_type": failure_type,
        "diagnosis_confidence": confidence,
        "diagnosis_status": "PRELIMINARY_REQUIRES_GOLD_REVIEW",
        "candidate_count": len(candidates),
        "registration_only_top_candidate": registration_only,
        "next_check": _next_check(failure_type),
    }


def _review_item(gold: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": gold["question_id"],
        "question": gold["question"],
        "status": "PENDING",
        "required_confirmation": [
            "正确文件和版本",
            "最小可引用位置（页/段/行/Sheet/行号）",
            "组织、项目、年份、专业等适用范围",
            "权威等级和文档角色",
            "关键 Claim 与不得使用的来源",
        ],
        "candidate_count": len(gold["proposed_candidates"]),
        "candidate_files": [item.get("file_name") for item in gold["proposed_candidates"]],
        "registration_candidates": gold["proposed_excluded_candidates"],
    }


def _next_check(failure_type: str) -> str:
    return {
        "NONE": "确认业务 Gold 后做回归基线。",
        "SOURCE_MISSING": "确认外部正文是否属于已批准知识范围；未批准时登记 Knowledge Gap。",
        "EVIDENCE_MISSED": "确认正确文件/位置后，检查 Document、Section、Atomic 三层命中。",
        "GENERATION_FAILURE": "冻结 Evidence 后检查 Schema、Claim、Section Map 和 Citation。",
        "PENDING_BUSINESS_REVIEW": "先由业务负责人评价现有答案是否真正回答问题。",
    }.get(failure_type, "等待业务 Gold 确认。")


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_report(
    manifest: dict[str, Any], atlas: dict[str, Any], review_queue: dict[str, Any]
) -> str:
    records = manifest["records"]
    failure_by_id = {item["question_id"]: item for item in atlas["records"]}
    lines = [
        "# Business Gold V2 + Failure Atlas 报告",
        "",
        "> TASK-020A：仅基于已持久化 Shadow 结果与原子定位候选生成业务复核材料。不修改 Retriever、不调用 LLM、不修改 8000 或正式 Qdrant。",
        "",
        "## 1. 结论",
        "",
        "BA-001～BA-010 当前全部为 `GOLD_UNCONFIRMED`。本报告不会把系统候选、历史答案或登记页自动写成正确 Gold。",
        "",
        "## 2. 汇总",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| Business Questions | {len(records)} |",
        f"| 已持久化结果中 fresh_run=true | {manifest['source']['fresh_run_records']} |",
        f"| GOLD_UNCONFIRMED | {sum(item['gold_status'] == 'GOLD_UNCONFIRMED' for item in records)} |",
        f"| 待业务复核项 | {len(review_queue['items'])} |",
        f"| 登记页首候选 | {sum(item['registration_only_top_candidate'] for item in atlas['records'])} |",
        "",
        "## 3. 初步 Failure Atlas",
        "",
        "| 问题 | 当前状态 | 初步归因 | 置信度 | 下一步核查 |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        failure = failure_by_id[record["question_id"]]
        lines.append(
            f"| {record['question_id']} | {failure['observed_final_status']} | `{failure['preliminary_failure_type']}` | {failure['diagnosis_confidence']} | {failure['next_check']} |"
        )
    lines.extend(
        [
            "",
            "## 4. 业务复核要求",
            "",
            "每题必须由业务负责人确认：正确文件、版本、最小引用位置、适用范围、权威等级、关键 Claim，以及不得使用的错误来源。",
            "",
            "登记页、Wiki 索引页、链接页只可作为 Source Lineage 线索，不能作为事实 Gold。",
            "",
            "当前材料用于 Gold 确认与初步 Failure Atlas。业务 Gold 确认后，需要重新执行一次受控 Shadow Fresh Run，才能形成最终 Failure Atlas 和 V2 检索基线。",
            "",
            "## 5. 输出文件",
            "",
            "- `evaluation/business_gold_v2/gold_manifest.json`",
            "- `evaluation/business_gold_v2/ba_failure_atlas.json`",
            "- `evaluation/business_gold_v2/gold_review_queue.json`",
            "",
            "## 6. 停止点",
            "",
            "TASK-020A 已建立复核基线。只有业务 Gold 被确认后，才能进入 TASK-020B 的 Document Intelligence V2；当前不进入 Retriever 改造。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
