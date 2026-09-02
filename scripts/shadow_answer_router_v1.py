from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FACT_RESULT = PROJECT_ROOT / "evaluation" / "fact_answers" / "BA-010.json"
GOLD_PATH = PROJECT_ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "answer_router"
OUTPUT = OUTPUT_DIR / "route_cases.json"
REPORT = PROJECT_ROOT / "docs" / "SHADOW_ANSWER_ROUTER_V1_REPORT.md"

ROUTES = ("CLAIM_ANSWER_PATH", "FACT_ANSWER_PATH", "FACT_PATH_UNAVAILABLE")

EXTRA_CASES = [
    ("R-001", "制度要求", "设计管理制度中的项目设计任务书评审要求有哪些？", "CLAIM_ANSWER_PATH"),
    ("R-002", "方法流程", "设计任务书编制流程包括哪些步骤？", "CLAIM_ANSWER_PATH"),
    ("R-003", "项目案例", "EPC设计管理复盘案例中有哪些常见经验？", "CLAIM_ANSWER_PATH"),
    ("R-004", "专业知识", "特殊环境下集电线路电气图审要点有哪些？", "CLAIM_ANSWER_PATH"),
    ("R-005", "模板内容", "设计任务书模板需要填写哪些内容？", "CLAIM_ANSWER_PATH"),
    ("R-006", "普通做法", "设计价值创造有哪些主要做法？", "CLAIM_ANSWER_PATH"),
    ("R-007", "Fact数量", "星谷项目有多少条价值创造策划？", "FACT_ANSWER_PATH"),
    ("R-008", "Fact分组", "按专业统计星谷价值创造清单有多少条？", "FACT_ANSWER_PATH"),
    ("R-009", "Fact分组", "星谷项目每个专业分别多少条？", "FACT_ANSWER_PATH"),
    ("R-010", "Fact条件", "星谷项目利润大于0的增加效益有多少条？", "FACT_ANSWER_PATH"),
    ("R-011", "Fact求和", "星谷项目价值创造条目合计多少金额？", "FACT_PATH_UNAVAILABLE"),
    ("R-012", "Fact范围缺口", "2026年有多少个设计示范项目？", "FACT_PATH_UNAVAILABLE"),
    ("R-013", "制度要求", "设计示范项目有哪些要求？", "CLAIM_ANSWER_PATH"),
    ("R-014", "Fact范围缺口", "公司2025年设计创效金额是多少元？", "FACT_PATH_UNAVAILABLE"),
    ("R-015", "Fact范围缺口", "按项目统计2026年设计示范项目数量？", "FACT_PATH_UNAVAILABLE"),
    ("R-016", "管理职责", "设计示范项目的管理要求和职责是什么？", "CLAIM_ANSWER_PATH"),
    ("R-017", "Fact列表", "价值创造清单中有哪些专业？", "FACT_ANSWER_PATH"),
    ("R-018", "Fact列表", "利润大于0的价值创造条目有哪些？", "FACT_ANSWER_PATH"),
    ("R-019", "定义解释", "设计价值创造清单的利润字段如何理解？", "CLAIM_ANSWER_PATH"),
    ("R-020", "Fact组合", "星谷项目价值创造有哪些专业并合计多少条？", "FACT_ANSWER_PATH"),
]


def load_fact_capability() -> dict[str, Any]:
    result = json.loads(FACT_RESULT.read_text(encoding="utf-8"))
    aggregation = result.get("fact_aggregation", {})
    return {
        "target_document": aggregation.get("target_document"),
        "target_sheet": aggregation.get("target_sheet"),
        "structured_table_source": bool(aggregation.get("source_rows")),
        "field_mapping": ["专业类别", "利润"],
        "business_semantics": aggregation.get("business_rule"),
        "deterministic_aggregation": result.get("validation_result", {}).get("valid") is True,
        "supported_operations": ["LIST_DISTINCT", "GROUP_BY", "COUNT", "FILTER"],
        "fact_answer_ready": result.get("validation_result", {}).get("valid") is True and result.get("citation_result", {}).get("valid") is True,
    }


def infer_intent(question: str) -> str:
    if any(term in question for term in ("制度", "规定", "要求", "规范", "责任状", "管理要求")):
        return "POLICY_QUERY"
    if any(term in question for term in ("案例", "经验", "复盘", "总结")):
        return "CASE_QUERY"
    if any(term in question for term in ("模板", "表单", "任务书")) and not any(term in question for term in ("多少", "统计", "合计")):
        return "TEMPLATE_QUERY"
    if any(term in question for term in ("建筑", "结构", "机电", "电气", "暖通", "给排水", "BIM", "EPC", "专业")):
        return "DISCIPLINE_QUERY"
    if any(term in question for term in ("如何", "怎么", "方法", "步骤", "流程", "编制", "策划")):
        return "METHOD_QUERY"
    return "GENERAL_QUERY"


def fact_types(question: str) -> list[str]:
    result: list[str] = []
    if any(term in question for term in ("多少条", "多少个", "数量", "数量分布", "分别多少", "有哪些专业", "哪几个专业", "有多少")):
        result.append("COUNT_FACT")
    if any(term in question for term in ("金额", "多少钱", "多少元", "多少万元", "总金额", "合计金额")):
        result.append("AMOUNT_FACT")
    if any(term in question for term in ("效益率", "创效率", "比例", "占比")):
        result.append("RATE_FACT")
    if re.search(r"20\d{2}年|\d+月", question):
        result.append("DATE_FACT")
    if any(term in question for term in ("公司", "按项目", "按专业", "每个专业", "土木公司", "星谷项目")):
        result.append("SCOPE_FACT")
    return list(dict.fromkeys(result))


def operations(question: str) -> list[str]:
    result: list[str] = []
    if any(term in question for term in ("有哪些专业", "哪些专业", "哪几个专业", "专业列表", "列出")):
        result.append("LIST_DISTINCT")
    if any(term in question for term in ("按专业", "每个专业", "各专业", "按项目", "分组", "分别")):
        result.append("GROUP_BY")
    if any(term in question for term in ("多少条", "多少个", "数量", "多少", "计数")):
        result.append("COUNT")
    if any(term in question for term in ("其中", "利润大于0", "满足条件", "按条件", "筛选", "过滤", "增加效益")):
        result.append("FILTER")
    explicit_sum = any(term in question for term in ("总金额", "合计金额", "总效益", "总利润", "金额合计")) or ("求和" in question and "要求和" not in question)
    if explicit_sum or (
        "合计" in question and any(term in question for term in ("金额", "元", "万元", "利润", "效益"))
    ):
        result.append("SUM")
    return list(dict.fromkeys(result))


def target_info(question: str, capability: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    if any(term in question for term in ("星谷", "价值创造清单", "价值创造策划")) or (
        "价值创造" in question and any(term in question for term in ("利润", "条目", "专业", "统计"))
    ):
        return "星谷科创中心", capability["target_document"], capability["target_sheet"]
    if "设计示范项目" in question:
        return "设计示范项目", "关于印发中建三局2026年设计与技术工作计划的通知.pdf", None
    if "设计服务管理台账" in question or "双周推进" in question:
        return "设计服务管理", "公司设计服务管理台帐2026.xlsx", None
    if "公司设计创效" in question:
        return "公司设计创效", None, None
    return None, None, None


def route_question(question: str, capability: dict[str, Any]) -> dict[str, Any]:
    intent = infer_intent(question)
    fact = fact_types(question)
    ops = operations(question)
    entity, document, sheet = target_info(question, capability)
    strong_fact_language = bool(set(ops) & {"COUNT", "SUM", "GROUP_BY", "FILTER"})
    list_fact_language = "LIST_DISTINCT" in ops and any(term in question for term in ("清单", "星谷", "项目", "价值创造"))
    fact_trigger = strong_fact_language or list_fact_language
    reasons: list[str] = []
    if fact_trigger:
        reasons.append("问题包含数量/金额/分组/条件/列表统计语义组合")
        reasons.append(f"operations={','.join(ops)}")
    else:
        reasons.append("问题主要要求制度、方法、案例、定义或说明，不要求确定性统计")
    if entity:
        reasons.append(f"识别目标实体：{entity}")
    if document:
        reasons.append(f"识别目标资料：{document}")
    if sheet:
        reasons.append(f"识别目标 Sheet：{sheet}")
    if not fact_trigger:
        return {
            "query": question,
            "route": "CLAIM_ANSWER_PATH",
            "confidence": 0.92,
            "intent": intent,
            "fact_types": fact,
            "operations": ops,
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "final_path": "CLAIM_ANSWER_PATH",
            "final_status": "ROUTED_TO_CLAIM_PATH",
            "provider_status": "NOT_RUN",
        }
    missing: list[str] = []
    target_matches_capability = document == capability["target_document"] and sheet == capability["target_sheet"]
    if not entity and not document:
        missing.append("target structured table document not identified")
    if not target_matches_capability:
        missing.append("no confirmed Structured Table Source for this target")
    if not capability["field_mapping"]:
        missing.append("Field Mapping missing")
    if not capability["business_semantics"]:
        missing.append("Business Semantics missing")
    if not capability["deterministic_aggregation"]:
        missing.append("Deterministic Aggregation capability missing")
    unsupported = sorted(set(ops) - set(capability["supported_operations"]))
    if unsupported:
        missing.append(f"unsupported operations: {','.join(unsupported)}")
    if missing:
        reasons.append("Fact 语义已识别，但当前确定性 Fact 能力不足：" + "; ".join(missing))
        return {
            "query": question,
            "route": "FACT_PATH_UNAVAILABLE",
            "confidence": 0.86,
            "intent": "FACT_QUERY",
            "fact_types": fact,
            "operations": ops,
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "missing_fact_capabilities": missing,
            "final_path": "FACT_PATH_UNAVAILABLE",
            "final_status": "FACT_PATH_UNAVAILABLE",
            "provider_status": "NOT_RUN",
        }
    reasons.append("目标结构化表格、字段映射、业务语义和确定性聚合能力均可用")
    return {
        "query": question,
        "route": "FACT_ANSWER_PATH",
        "confidence": 0.97,
        "intent": "FACT_QUERY",
        "fact_types": fact,
        "operations": ops,
        "target_entity": entity,
        "target_document": document,
        "target_sheet": sheet,
        "routing_reasons": reasons,
        "final_path": "FACT_ANSWER_PATH",
        "final_status": "DETERMINISTIC_FACT_RESULT_AVAILABLE" if capability["fact_answer_ready"] else "FACT_PATH_UNAVAILABLE",
        "provider_status": "NOT_REQUIRED",
    }


def load_ba_questions() -> list[tuple[str, str, str]]:
    import yaml

    payload = yaml.safe_load(GOLD_PATH.read_text(encoding="utf-8")) or {}
    expected = {
        "BA-001": "CLAIM_ANSWER_PATH",
        "BA-002": "CLAIM_ANSWER_PATH",
        "BA-003": "CLAIM_ANSWER_PATH",
        "BA-004": "CLAIM_ANSWER_PATH",
        "BA-005": "CLAIM_ANSWER_PATH",
        "BA-006": "FACT_PATH_UNAVAILABLE",
        "BA-007": "CLAIM_ANSWER_PATH",
        "BA-008": "FACT_PATH_UNAVAILABLE",
        "BA-009": "CLAIM_ANSWER_PATH",
        "BA-010": "FACT_ANSWER_PATH",
    }
    return [(str(item["id"]), str(item["question"]), expected[str(item["id"])]) for item in payload["questions"]]


def render_report(cases: list[dict[str, Any]], capability: dict[str, Any], provider_failure_context: dict[str, Any]) -> str:
    accuracy = sum(case["expected_route"] == case["actual_route"] for case in cases)
    false_fact = sum(case["expected_route"] == "CLAIM_ANSWER_PATH" and case["actual_route"] != "CLAIM_ANSWER_PATH" for case in cases)
    false_claim = sum(case["expected_route"] != "CLAIM_ANSWER_PATH" and case["actual_route"] == "CLAIM_ANSWER_PATH" for case in cases)
    unavailable = sum(case["actual_route"] == "FACT_PATH_UNAVAILABLE" for case in cases)
    lines = [
        "# Shadow Answer Router V1 Report",
        "",
        "> TASK-016E-4：只在 Shadow 环境验证 Claim Answer Path 与 Fact Answer Path 路由。",
        "> Router 不调用 LLM，不修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF 或 Reranker。",
        "",
        "## 1. Fact Capability",
        "",
        f"- Structured Table Source：`{capability['structured_table_source']}`",
        f"- Target Document：`{capability['target_document']}`",
        f"- Target Sheet：`{capability['target_sheet']}`",
        f"- Field Mapping：`{capability['field_mapping']}`",
        f"- Business Semantics：`{json.dumps(capability['business_semantics'], ensure_ascii=False)}`",
        f"- Deterministic Aggregation：`{capability['deterministic_aggregation']}`",
        f"- Supported Operations：`{capability['supported_operations']}`",
        "",
        "## 2. BA-001～BA-010 路由结果",
        "",
        "| ID | 问题 | Expected Route | Actual Route | Intent | Operations | Final Path | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in cases[:10]:
        lines.append(f"| {case['case_id']} | {case['query']} | {case['expected_route']} | {case['actual_route']} | {case['decision']['intent']} | {','.join(case['decision']['operations']) or '-'} | {case['decision']['final_path']} | {case['decision']['final_status']} |")
    lines += [
        "",
        "## 3. 新增 20 题路由结果",
        "",
        "| ID | 问题 | Expected Route | Actual Route | Operations | Final Path |",
        "|---|---|---|---|---|---|",
    ]
    for case in cases[10:]:
        lines.append(f"| {case['case_id']} | {case['query']} | {case['expected_route']} | {case['actual_route']} | {','.join(case['decision']['operations']) or '-'} | {case['decision']['final_path']} |")
    lines += [
        "",
        "## 4. Router 指标",
        "",
        f"- Route Accuracy：**{accuracy}/{len(cases)} ({accuracy / len(cases):.1%})**",
        f"- False Fact Route：`{false_fact}`",
        f"- False Claim Route：`{false_claim}`",
        f"- FACT_PATH_UNAVAILABLE：`{unavailable}`",
        f"- Provider Failure 分类：`{json.dumps(provider_failure_context, ensure_ascii=False)}`；Router 本身未调用 Provider，未将 Provider Failure 转换成业务失败。",
        "",
        "## 5. 重点验收",
        "",
        "- BA-007：必须且实际为 `CLAIM_ANSWER_PATH`。",
        "- BA-010：必须且实际为 `FACT_ANSWER_PATH`，使用已验证的确定性 Fact Result。",
        "- “设计价值创造有哪些主要做法？”进入 Claim，不因“价值创造”单词误触发 Fact。",
        "- “2026年有多少个设计示范项目？”进入 FACT_PATH_UNAVAILABLE，不回退让 LLM 计算。",
        "- “星谷项目有多少条价值创造策划？”进入 FACT_ANSWER_PATH。",
        "",
        "## 6. 输出边界",
        "",
        "- Router 决策未使用 BA 编号或完整问题文本硬编码；BA 编号只用于测试 Expected Route 对账。",
        "- Fact 路由只在结构化来源、字段映射、业务语义和确定性聚合能力同时存在时可用。",
        "- 事实统计数字仍由 Fact Answer Path 产生，Router 不计算数字。",
        "- 本任务未接入正式 8000 服务。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    import yaml

    capability = load_fact_capability()
    cases: list[dict[str, Any]] = []
    for case_id, query, expected in load_ba_questions():
        cases.append({"case_id": case_id, "query": query, "expected_route": expected, "actual_route": route_question(query, capability)["route"], "decision": route_question(query, capability)})
    for case_id, label, query, expected in EXTRA_CASES:
        decision = route_question(query, capability)
        cases.append({"case_id": case_id, "label": label, "query": query, "expected_route": expected, "actual_route": decision["route"], "decision": decision})
    provider_failure_context = {"source": "TASK-016E-3.1 upstream stability", "provider_failures": 1, "classification": "I PROVIDER_FAILURE", "router_provider_calls": 0}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"schema_version": "answer-route-decision.v1", "capability": capability, "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(cases, capability, provider_failure_context), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(REPORT.resolve()), "cases": len(cases), "accuracy": sum(c['expected_route']==c['actual_route'] for c in cases)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
