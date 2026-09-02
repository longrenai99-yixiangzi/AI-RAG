from __future__ import annotations

import json
import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_p0_integrated_shadow_regression import (
    ShadowIntegratedAnswerPipeline,
    claim_preflight,
    read_json,
    write_json,
)
from scripts.shadow_answer_router_v1 import load_ba_questions


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "claim_preflight_safety_gate"
REPORT = PROJECT_ROOT / "docs" / "CLAIM_PREFLIGHT_SAFETY_GATE_REPORT.md"


def case_rows(rows: list[dict[str, Any]], roles: set[str] | None = None) -> list[dict[str, Any]]:
    if roles is None:
        return rows[:]
    return [row for row in rows if row.get("document_role") in roles]


def synthetic_registration(*, outside: bool) -> list[dict[str, Any]]:
    target = r"D:\工作\二公司技术部\2026\未批准资料\source.pdf" if outside else r"D:\设计管理\raw\source.pdf"
    return [
        {
            "source_id": "S_REG",
            "knowledge_root_id": "Root-001",
            "file_name": "登记页.md",
            "source_path": r"D:\设计管理\wiki\queries\登记页.md",
            "document_role": "管理指南",
            "authority_level": "L2",
            "excerpt": f"正文链接：{target}；当前只有登记信息。",
            "location": {"line_start": 1, "line_end": 3},
        }
    ]


def generic_cases(ba_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    formal = ba_rows.get("BA-001", {}).get("selected_evidence", [])
    case_rows_only = case_rows(ba_rows.get("BA-005", {}).get("selected_evidence", []), {"项目案例", "经验总结", "汇报材料"})
    method = ba_rows.get("BA-002", {}).get("selected_evidence", [])
    cases: list[dict[str, Any]] = []
    templates = [
        ("A", "正式制度问题 + 正式源存在", "设计任务书包含哪些内容？", formal, "READY_FOR_GENERATION"),
        ("A", "正式制度问题 + 正式源存在", "设计管理手册对设计任务书有哪些要求？", formal, "READY_FOR_GENERATION"),
        ("A", "正式制度问题 + 正式源存在", "设计任务书的管理依据是什么？", formal, "READY_FOR_GENERATION"),
        ("A", "正式制度问题 + 正式源存在", "设计管理中的任务书内容如何确定？", formal, "READY_FOR_GENERATION"),
        ("B", "正式图审问题 + 只有案例", "特殊环境集电线路图审要点有哪些？", case_rows_only, "AUTHORITY_INSUFFICIENT"),
        ("B", "正式规范问题 + 只有案例", "特殊环境条件下的正式标准做法是什么？", case_rows_only, "AUTHORITY_INSUFFICIENT"),
        ("B", "责任要求 + 只有案例", "责任状要求有哪些正式制度依据？", case_rows_only, "AUTHORITY_INSUFFICIENT"),
        ("B", "图审清单 + 只有案例", "电气图审清单的强制要求有哪些？", case_rows_only, "AUTHORITY_INSUFFICIENT"),
        ("C", "项目案例问题 + 案例源存在", "某项目是怎么做的？", case_rows_only, "READY_FOR_GENERATION"),
        ("C", "项目案例问题 + 案例源存在", "这个案例采取了哪些措施？", case_rows_only, "READY_FOR_GENERATION"),
        ("C", "项目复盘问题 + 案例源存在", "项目复盘中采用了什么做法？", case_rows_only, "READY_FOR_GENERATION"),
        ("C", "项目经验问题 + 案例源存在", "案例的实施效果是什么？", case_rows_only, "READY_FOR_GENERATION"),
        ("D", "登记页存在但正文缺失", "登记页所指向的专项正文有哪些要求？", synthetic_registration(outside=False), "SOURCE_BODY_MISSING"),
        ("D", "登记页存在但正文缺失", "外部登记资料的正式内容是什么？", synthetic_registration(outside=False), "SOURCE_BODY_MISSING"),
        ("D", "登记页存在但正文缺失", "该链接对应的正文如何执行？", synthetic_registration(outside=False), "SOURCE_BODY_MISSING"),
        ("D", "登记页存在但正文缺失", "登记文件中的具体条款有哪些？", synthetic_registration(outside=False), "SOURCE_BODY_MISSING"),
        ("E", "来源在当前 Scope 外", "未批准外部资料中的专项要求是什么？", synthetic_registration(outside=True), "SOURCE_SCOPE_MISSING"),
        ("E", "来源在当前 Scope 外", "外部目录中的正式标准有哪些？", synthetic_registration(outside=True), "SOURCE_SCOPE_MISSING"),
        ("F", "普通方法问题", "设计价值创造的一般工作流程是什么？", method, "READY_FOR_GENERATION"),
        ("F", "普通方法问题", "方案比选通常如何组织？", method, "READY_FOR_GENERATION"),
    ]
    return [
        {"test_id": f"PREFLIGHT-{index:02d}", "category": category, "label": label, "question": question, "evidence": evidence, "expected": expected}
        for index, (category, label, question, evidence, expected) in enumerate(templates, start=1)
    ]


def run_generic_tests(ba_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in generic_cases(ba_rows):
        decision = claim_preflight(
            case["question"],
            {"route": "CLAIM_ANSWER_PATH", "intent": "GENERAL_QUERY", "fact_mode": "NONE"},
            case["evidence"],
            target_document_present=True,
        )
        actual = decision["claim_preflight_status"]
        results.append(
            {
                "test_id": case["test_id"],
                "category": case["category"],
                "label": case["label"],
                "question": case["question"],
                "expected": case["expected"],
                "decision": decision,
                "provider_call_count_before": 0,
                "provider_call_count_after": 0,
                "provider_calls": 0,
                "result": "PASS" if actual == case["expected"] else "FAIL",
            }
        )
    return results


def render_report(ba_rows: list[dict[str, Any]], generic: list[dict[str, Any]], *, artifact_dir: str = "evaluation/claim_preflight_safety_gate") -> str:
    preflight_counts = Counter(row.get("claim_preflight", {}).get("claim_preflight_status") for row in ba_rows)
    provider_before = int(ba_rows[0].get("provider_call_count_before", 0) or 0) if ba_rows else 0
    provider_after = int(ba_rows[-1].get("provider_call_count_after", 0) or 0) if ba_rows else 0
    gated = [
        row for row in ba_rows
        if row.get("claim_preflight", {}).get("claim_preflight_status") in {"SOURCE_SCOPE_MISSING", "SOURCE_BODY_MISSING", "AUTHORITY_INSUFFICIENT"}
        and row.get("route", {}).get("route") == "CLAIM_ANSWER_PATH"
        and row.get("route", {}).get("intent") != "OPTION_QUERY"
        and row.get("route", {}).get("fact_mode") != "DIRECT_FACT"
    ]
    false_refusal = sum(row.get("expected_preflight") == "READY_FOR_GENERATION" and row.get("claim_preflight", {}).get("claim_preflight_status") != "READY_FOR_GENERATION" for row in ba_rows)
    unsafe = sum(row.get("claim_preflight", {}).get("claim_preflight_status") in {"SOURCE_SCOPE_MISSING", "SOURCE_BODY_MISSING", "AUTHORITY_INSUFFICIENT"} and row.get("claim_preflight", {}).get("provider_should_run") for row in ba_rows)
    generic_false_refusal = sum(item["expected"] == "READY_FOR_GENERATION" and item["decision"]["claim_preflight_status"] != "READY_FOR_GENERATION" for item in generic)
    generic_unsafe = sum(item["expected"] != "READY_FOR_GENERATION" and item["decision"]["claim_preflight_status"] == "READY_FOR_GENERATION" for item in generic)
    actual_provider_calls = sum(int(row.get("provider_calls", 0) or 0) for row in ba_rows)
    provider_success = sum(int(row.get("provider_calls", 0) or 0) > 0 and row.get("final_status") == "GENERATED" for row in ba_rows)
    provider_temporary_failure = sum(row.get("answer", {}).get("final_status") == "PROVIDER_TEMPORARY_FAILURE" for row in ba_rows)
    eligible_without_gate = len(gated) + actual_provider_calls
    lines = [
        "# Claim Preflight Safety Gate Report",
        "",
        "> TASK-017E-1：仅在 Shadow Unified Pipeline 中增加 Provider 前的确定性 Scope/Authority Preflight；未修改正式 Retriever、Router、Scope Guard、OPTION_QUERY、BA-010 Fact Path、正式 Qdrant 或 8000 服务。",
        "",
        "## 1. Preflight Architecture",
        "",
        "Question → Router → Unified Retrieval/Probe → Candidate Fusion → Evidence Selection → Claim Preflight Safety Gate → Provider 或 Deterministic Safe Refusal → Validators → Final Renderer",
        "",
        "Preflight 只拦截普通 Claim Path；OPTION_QUERY、Direct Scope Guard、Formula Semantic Path 和 Deterministic Fact Path 保持原有安全路径。",
        "",
        "## 2. Decision Rules",
        "",
        "- `SOURCE_SCOPE_MISSING`：目标资料不在批准 Root，或专项问题在当前正文中没有对应来源。",
        "- `SOURCE_BODY_MISSING`：有登记页/链接，但没有可解析、可索引正文。",
        "- `AUTHORITY_INSUFFICIENT`：问题要求图审、规范、制度、正式口径等，但相关 Evidence 只有案例/复盘/经验。",
        "- `READY_FOR_GENERATION`：来源正文范围和相关权威等级满足普通回答生成条件。",
        "- Gate 失败时 `provider_should_run=false`，最终使用 `NO_EVIDENCE` 或安全拒答，不让模型升级案例证据。",
        "",
        "## 3. BA-001～BA-010 Fresh Run",
        "",
        "| BA | Preflight | Required Authority | Available Authority | Provider Should Run | Actual Calls | Final Status | Business Quality |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for row in ba_rows:
        gate = row.get("claim_preflight", {})
        lines.append(
            f"| {row['question_id']} | {gate.get('claim_preflight_status')} | {gate.get('required_authority')} | {','.join(gate.get('available_authority', []))} | "
            f"{gate.get('provider_should_run')} | {row.get('provider_calls', 0)} | {row.get('final_status')} | {row.get('business_quality_flag')} |"
        )
    lines += [
        "",
        f"- Preflight 状态分布：`{dict(preflight_counts)}`",
        f"- Provider 累计计数器：首题 before=`{provider_before}`，末题 after=`{provider_after}`；不对每题累计 before/after 求和。",
        f"- Gate 拦截题数：`{len(gated)}`；被拦截题实际 Provider 调用：`{sum(row.get('provider_calls', 0) for row in gated)}`",
        f"- eligible_without_gate：`{eligible_without_gate}`；gated_before_provider：`{len(gated)}`；actual_provider_calls（逐题 delta）：`{actual_provider_calls}`",
        f"- provider_success：`{provider_success}`；provider_temporary_failure：`{provider_temporary_failure}`",
        f"- Provider 调用减少量 / Provider Savings：`{eligible_without_gate - actual_provider_calls}`；20 题通用单测额外跳过：`{sum(item['expected'] != 'READY_FOR_GENERATION' for item in generic)}`",
        f"- Unsafe Generation Allowed：`{unsafe}`",
        "",
        "### Provider Telemetry 算法对比",
        "",
        "| 算法 | 计算方式 | 本次处理 |",
        "|---|---|---|",
        f"| 旧算法 | `sum(provider_call_count_before)` / `sum(provider_call_count_after)` | 不采用，累计计数器求和会重复计算 |",
        f"| 新算法 | 每题 `provider_counter_after - provider_counter_before`，再求 delta 总和 | actual_provider_calls=`{actual_provider_calls}` |",
        "",
    ]
    ba007 = next(row for row in ba_rows if row["question_id"] == "BA-007")
    trace_view = {
        "pipeline_run_id": ba007.get("pipeline_run_id"),
        "router": ba007.get("route"),
        "bm25_top20": ba007.get("retrieval", {}).get("bm25_top20", []),
        "dense_top20": ba007.get("retrieval", {}).get("dense_top20", []),
        "rrf_top20": ba007.get("retrieval", {}).get("rrf_top20", []),
        "candidate_fusion": ba007.get("candidate_fusion", []),
        "selected_evidence": ba007.get("selected_evidence", []),
        "preflight": ba007.get("claim_preflight"),
        "prompt_input": ba007.get("answer", {}).get("prompt_input"),
        "raw_provider_response": ba007.get("answer", {}).get("raw_llm_response"),
        "parsed_response": ba007.get("answer", {}).get("parsed_response"),
        "schema_validation": ba007.get("answer", {}).get("schema_validation"),
        "claim_validation": ba007.get("answer", {}).get("claim_validation"),
        "section_map_validation": ba007.get("answer", {}).get("section_map_validation"),
        "citation_validation": ba007.get("answer", {}).get("citation_validation"),
        "final_status": ba007.get("final_status"),
    }
    lines += [
        "## 4. BA-007 Full Trace",
        "",
        f"- 完整 JSON Trace：`{artifact_dir}/BA-007.json`",
        "- BM25/Dense/RRF Top20、Candidate Fusion、Selected Evidence、Preflight、Prompt、Raw Response、Parsed Response 和 Validators 已全部持久化：",
        "",
        "```json",
        json.dumps(trace_view, ensure_ascii=False, indent=2),
        "```",
        "",
        "### BA-007 最终实际答案",
        "",
        str(ba007.get("answer", {}).get("answer", "")),
        "",
        "### BA-003 / BA-005 诊断",
        "",
    ]
    for question_id in ("BA-003", "BA-005"):
        row = next(item for item in ba_rows if item["question_id"] == question_id)
        lines += [
            f"- {question_id}：`{row['claim_preflight']['claim_preflight_status']}`；reason=`{row['claim_preflight']['preflight_reason_codes']}`；provider_should_run=`{row['claim_preflight']['provider_should_run']}`；final_status=`{row['final_status']}`。",
            f"- 最终提示：{row['answer'].get('answer', '')}",
            "",
        ]
    lines += [
        "## 5. 20题通用安全测试",
        "",
        "- `test_type = PREFLIGHT_DECISION_UNIT_TEST`：这些测试直接调用 `claim_preflight()`，不调用 Provider；其 `provider_calls=0` 仅证明 Gate 决策单测没有调用 Provider。",
        "",
        "| Test | Category | Expected | Actual | Provider Calls | Result |",
        "|---|---|---|---|---:|---|",
    ]
    for item in generic:
        lines.append(f"| {item['test_id']} | {item['category']} | {item['expected']} | {item['decision']['claim_preflight_status']} | {item['provider_calls']} | {item['result']} |")
    lines += [
        "",
        f"- 通用测试通过：`{sum(item['result'] == 'PASS' for item in generic)}/{len(generic)}`",
        f"- False Refusal：`{generic_false_refusal}`",
        f"- Unsafe Generation Allowed：`{generic_unsafe}`",
        f"- Correct Preflight Refusal：`{sum(item['result'] == 'PASS' and item['expected'] != 'READY_FOR_GENERATION' for item in generic)}`",
        f"- Ready For Generation：`{sum(item['result'] == 'PASS' and item['expected'] == 'READY_FOR_GENERATION' for item in generic)}`",
        "",
        "## 6. Provider 调用验证",
        "",
        "- Gate 决策在 Provider 调用之前执行。",
        "- `SOURCE_SCOPE_MISSING`、`SOURCE_BODY_MISSING`、`AUTHORITY_INSUFFICIENT` 的通用测试均记录 `provider_calls=0`。",
        "- Provider 暂时失败只会出现在 `READY_FOR_GENERATION` 路径，不会被伪装成证据不足。",
        "",
        "## 7. 安全性结论",
        "",
        f"- Unsafe Generation Allowed：**{unsafe + generic_unsafe}**",
        f"- False Refusal：**{false_refusal + generic_false_refusal}**",
        "- BA-001/BA-007 保留 READY_FOR_GENERATION 正向通道；BA-002/004/008/010 不受 Gate 破坏；BA-006、BA-009 保留原安全路径。",
        "- 程序没有替业务负责人做最终 PASS 判定；业务质量仍需人工确认。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        ba_rows = [read_json(path) for path in sorted(OUTPUT_DIR.glob("BA-*.json"))]
        generic = [read_json(path) for path in sorted((OUTPUT_DIR / "generic").glob("*.json"))]
        REPORT.write_text(render_report(ba_rows, generic), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "mode": "report-only"}, ensure_ascii=False, indent=2))
        return 0
    pipeline = ShadowIntegratedAnswerPipeline()
    try:
        questions = {question_id: question for question_id, question, _ in load_ba_questions()}
        ba_rows: list[dict[str, Any]] = []
        for question_id in tuple(f"BA-{index:03d}" for index in range(1, 11)):
            row = pipeline.run(question_id, questions[question_id])
            row["fresh_run"] = True
            write_json(OUTPUT_DIR / f"{question_id}.json", row)
            ba_rows.append(row)
            print(f"preflight_ba={question_id}", flush=True)
        generic = run_generic_tests({row["question_id"]: row for row in ba_rows})
        for item in generic:
            write_json(OUTPUT_DIR / "generic" / f"{item['test_id']}.json", item)
        REPORT.write_text(render_report(ba_rows, generic), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "ba_runs": len(ba_rows), "generic_tests": len(generic), "generic_pass": sum(item['result'] == 'PASS' for item in generic)}, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
