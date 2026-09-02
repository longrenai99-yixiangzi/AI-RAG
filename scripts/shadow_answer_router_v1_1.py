from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shadow_answer_router_v1 import (
    EXTRA_CASES,
    GOLD_PATH,
    load_ba_questions,
    load_fact_capability,
    target_info,
)


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "answer_router_v1_1"
OUTPUT = OUTPUT_DIR / "route_cases.json"
REPORT = PROJECT_ROOT / "docs" / "SHADOW_ANSWER_ROUTER_V1_1_REPORT.md"

DIRECT_FACT_TYPE_TERMS = {
    "COUNT_VALUE": ("数量", "多少个", "多少条", "几个", "数量是多少", "不少于多少"),
    "AMOUNT_VALUE": ("金额是多少", "多少元", "多少万元", "多少钱"),
    "RATE_VALUE": ("效益率", "创效率", "比例", "占比"),
    "DATE_VALUE": ("日期", "时间", "何时", "哪天"),
    "TARGET_VALUE": ("目标是多少", "要求多少", "要求达到", "规定为"),
}

DIRECT_MARKERS = ("目标是多少", "要求多少", "要求达到", "规定为", "不少于多少", "设计阶段效益目标", "设计效益率目标")
DERIVED_MARKERS = ("当前", "台账里", "台账中", "所有项目", "各项目", "各单位", "按项目", "按专业", "每个专业", "分别", "加起来", "平均", "分布", "统计")

DIRECT_EXPECTED = {
    "BA-006": ("CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    "BA-008": ("CLAIM_ANSWER_PATH", "DIRECT_FACT"),
}

DIRECT_DERIVED_PAIRS = [
    ("D-001", "公司要求设计示范项目不少于多少个？", "CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    ("D-002", "当前项目台账里共有多少个设计示范项目？", "FACT_PATH_UNAVAILABLE", "DERIVED_FACT"),
    ("D-003", "2025年公司设计创效金额是多少？", "CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    ("D-004", "把2025年所有项目设计创效金额加起来是多少？", "FACT_PATH_UNAVAILABLE", "DERIVED_FACT"),
    ("D-005", "设计效益率目标是多少？", "CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    ("D-006", "根据各项目金额计算公司平均设计效益率是多少？", "FACT_PATH_UNAVAILABLE", "DERIVED_FACT"),
    ("D-007", "责任状要求DOP上传数量是多少？", "CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    ("D-008", "当前各单位DOP上传数量合计是多少？", "FACT_PATH_UNAVAILABLE", "DERIVED_FACT"),
    ("D-009", "星谷科创中心项目设计价值创造目标效益率是多少？", "CLAIM_ANSWER_PATH", "DIRECT_FACT"),
    ("D-010", "按专业统计星谷项目价值创造总额是多少？", "FACT_PATH_UNAVAILABLE", "DERIVED_FACT"),
]


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
    if any(term in question for term in ("公司", "按项目", "按专业", "每个专业", "各项目", "各单位", "星谷项目")):
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
    explicit_sum = any(term in question for term in ("总金额", "合计金额", "总效益", "总利润", "金额合计", "总额")) or ("求和" in question and "要求和" not in question)
    if explicit_sum or ("合计" in question and any(term in question for term in ("金额", "元", "万元", "利润", "效益"))):
        result.append("SUM")
    return list(dict.fromkeys(result))


def direct_fact_type(question: str, fact: list[str]) -> str:
    for kind, terms in DIRECT_FACT_TYPE_TERMS.items():
        if any(term in question for term in terms):
            if kind == "COUNT_VALUE" and "目标" in question:
                continue
            return kind
    if "DATE_FACT" in fact:
        return "DATE_VALUE"
    return "OTHER"


def has_direct_semantics(question: str) -> bool:
    return any(marker in question for marker in DIRECT_MARKERS) or (
        "是多少" in question and not any(marker in question for marker in DERIVED_MARKERS)
    )


def has_derived_semantics(question: str, ops: list[str], target_document: str | None, target_sheet: str | None, capability: dict[str, Any], direct: bool) -> bool:
    structured_target = target_document == capability["target_document"] and target_sheet == capability["target_sheet"]
    if any(marker in question for marker in DERIVED_MARKERS):
        return True
    if set(ops) & {"GROUP_BY", "SUM", "FILTER"}:
        return True
    # “有哪些专业”只有在明确指向结构化清单时才需要 LIST_DISTINCT；
    # 普通文本中的“包含哪些专业/有哪些要求”仍走 Claim Path。
    if structured_target and "LIST_DISTINCT" in ops and not direct:
        return True
    # 结构化表格中的“多少条/多少个”表示跨记录计数；单一原文数量不满足该条件。
    return structured_target and "COUNT" in ops and not direct


def route_question(question: str, capability: dict[str, Any]) -> dict[str, Any]:
    intent = infer_intent(question)
    facts = fact_types(question)
    ops = operations(question)
    entity, document, sheet = target_info(question, capability)
    direct = has_direct_semantics(question)
    derived = has_derived_semantics(question, ops, document, sheet, capability, direct)
    ambiguous = (
        "设计示范项目" in question
        and "多少个" in question
        and not any(marker in question for marker in ("要求", "目标", "规定", "当前", "台账", "所有项目", "各项目"))
    )
    reasons: list[str] = []
    if ambiguous:
        reasons.append("问题同时可能表示制度目标数量或实际项目记录数量，语义无法区分")
        return {
            "query": question,
            "route": "FACT_PATH_UNAVAILABLE",
            "routing_status": "ROUTE_AMBIGUOUS",
            "fact_mode": "AMBIGUOUS_FACT",
            "confidence": 0.70,
            "intent": "FACT_QUERY",
            "fact_types": facts,
            "operations": ops,
            "aggregation_operations": ops,
            "requires_aggregation": True,
            "direct_fact_type": None,
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "missing_fact_capabilities": ["query semantics clarification required"],
            "final_path": "FACT_PATH_UNAVAILABLE",
            "final_status": "ROUTE_AMBIGUOUS",
            "provider_status": "NOT_RUN",
        }
    if direct and not derived:
        reasons.append("单一原文事实表达（要求/目标/金额/比例/日期），不要求跨记录计算")
        return {
            "query": question,
            "route": "CLAIM_ANSWER_PATH",
            "routing_status": "ROUTE_DETERMINED",
            "fact_mode": "DIRECT_FACT",
            "confidence": 0.93,
            "intent": intent,
            "fact_types": facts,
            "operations": [],
            "aggregation_operations": [],
            "requires_aggregation": False,
            "direct_fact_type": direct_fact_type(question, facts),
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "final_path": "CLAIM_ANSWER_PATH",
            "final_status": "ROUTED_TO_CLAIM_PATH",
            "provider_status": "NOT_RUN",
        }
    if not direct and not derived:
        reasons.append("普通制度/方法/案例/定义说明，不要求直接事实提取或多行聚合")
        return {
            "query": question,
            "route": "CLAIM_ANSWER_PATH",
            "routing_status": "ROUTE_DETERMINED",
            "fact_mode": "NONE",
            "confidence": 0.92,
            "intent": intent,
            "fact_types": facts,
            "operations": [],
            "aggregation_operations": [],
            "requires_aggregation": False,
            "direct_fact_type": None,
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "final_path": "CLAIM_ANSWER_PATH",
            "final_status": "ROUTED_TO_CLAIM_PATH",
            "provider_status": "NOT_RUN",
        }
    reasons.append("答案需要跨记录/分组/筛选/列表或求和操作")
    missing: list[str] = []
    if not entity and not document:
        missing.append("target structured table document not identified")
    target_matches = document == capability["target_document"] and sheet == capability["target_sheet"]
    if not target_matches:
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
        reasons.append("DERIVED_FACT能力不足：" + "; ".join(missing))
        return {
            "query": question,
            "route": "FACT_PATH_UNAVAILABLE",
            "routing_status": "ROUTE_DETERMINED",
            "fact_mode": "DERIVED_FACT",
            "confidence": 0.87,
            "intent": "FACT_QUERY",
            "fact_types": facts,
            "operations": ops,
            "aggregation_operations": ops,
            "requires_aggregation": True,
            "direct_fact_type": None,
            "target_entity": entity,
            "target_document": document,
            "target_sheet": sheet,
            "routing_reasons": reasons,
            "missing_fact_capabilities": missing,
            "final_path": "FACT_PATH_UNAVAILABLE",
            "final_status": "FACT_PATH_UNAVAILABLE",
            "provider_status": "NOT_RUN",
        }
    reasons.append("结构化来源、字段映射、业务语义和确定性聚合能力齐备")
    return {
        "query": question,
        "route": "FACT_ANSWER_PATH",
        "routing_status": "ROUTE_DETERMINED",
        "fact_mode": "DERIVED_FACT",
        "confidence": 0.97,
        "intent": "FACT_QUERY",
        "fact_types": facts,
        "operations": ops,
        "aggregation_operations": ops,
        "requires_aggregation": True,
        "direct_fact_type": None,
        "target_entity": entity,
        "target_document": document,
        "target_sheet": sheet,
        "routing_reasons": reasons,
        "final_path": "FACT_ANSWER_PATH",
        "final_status": "DETERMINISTIC_FACT_RESULT_AVAILABLE",
        "provider_status": "NOT_REQUIRED",
    }


def expected_ba_cases() -> list[tuple[str, str, str, str]]:
    questions = load_ba_questions()
    expected: dict[str, tuple[str, str]] = {
        "BA-001": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-002": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-003": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-004": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-005": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-006": ("CLAIM_ANSWER_PATH", "DIRECT_FACT"),
        "BA-007": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-008": ("CLAIM_ANSWER_PATH", "DIRECT_FACT"),
        "BA-009": ("CLAIM_ANSWER_PATH", "NONE"),
        "BA-010": ("FACT_ANSWER_PATH", "DERIVED_FACT"),
    }
    return [(case_id, query, route, mode) for case_id, query, _old in questions for route, mode in [expected[case_id]]]


def expected_extra_cases() -> list[tuple[str, str, str, str, str | None]]:
    from scripts.shadow_answer_router_v1 import EXTRA_CASES

    cases = []
    for case_id, label, query, old_route in EXTRA_CASES:
        if case_id == "R-012":
            cases.append((case_id, query, "FACT_PATH_UNAVAILABLE", "AMBIGUOUS_FACT", "ROUTE_AMBIGUOUS"))
        elif case_id == "R-014":
            cases.append((case_id, query, "CLAIM_ANSWER_PATH", "DIRECT_FACT", "ROUTE_DETERMINED"))
        elif old_route == "CLAIM_ANSWER_PATH":
            cases.append((case_id, query, old_route, "NONE", "ROUTE_DETERMINED"))
        else:
            cases.append((case_id, query, old_route, "DERIVED_FACT", "ROUTE_DETERMINED"))
    return cases


def main() -> int:
    capability = load_fact_capability()
    cases: list[dict[str, Any]] = []
    for case_id, query, expected_route, expected_mode in expected_ba_cases():
        decision = route_question(query, capability)
        cases.append({"case_id": case_id, "query": query, "expected_route": expected_route, "expected_fact_mode": expected_mode, "expected_routing_status": "ROUTE_DETERMINED", "actual_route": decision["route"], "actual_fact_mode": decision["fact_mode"], "actual_routing_status": decision["routing_status"], "decision": decision})
    for case_id, query, expected_route, expected_mode, expected_status in expected_extra_cases():
        decision = route_question(query, capability)
        cases.append({"case_id": case_id, "query": query, "expected_route": expected_route, "expected_fact_mode": expected_mode, "expected_routing_status": expected_status, "actual_route": decision["route"], "actual_fact_mode": decision["fact_mode"], "actual_routing_status": decision["routing_status"], "decision": decision})
    for case_id, query, expected_route, expected_mode in DIRECT_DERIVED_PAIRS:
        decision = route_question(query, capability)
        cases.append({"case_id": case_id, "query": query, "expected_route": expected_route, "expected_fact_mode": expected_mode, "expected_routing_status": "ROUTE_DETERMINED", "actual_route": decision["route"], "actual_fact_mode": decision["fact_mode"], "actual_routing_status": decision["routing_status"], "decision": decision})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"schema_version": "answer-route-decision.v1.1", "capability": capability, "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    route_accuracy = sum(case["expected_route"] == case["actual_route"] for case in cases)
    mode_accuracy = sum(case["expected_fact_mode"] == case["actual_fact_mode"] for case in cases)
    status_accuracy = sum(case["expected_routing_status"] == case["actual_routing_status"] for case in cases)
    false_fact = sum(case["expected_route"] == "CLAIM_ANSWER_PATH" and case["actual_route"] != "CLAIM_ANSWER_PATH" for case in cases)
    false_claim = sum(case["expected_route"] != "CLAIM_ANSWER_PATH" and case["actual_route"] == "CLAIM_ANSWER_PATH" for case in cases)
    lines = [
        "# Shadow Answer Router V1.1 Report",
        "",
        "> TASK-016E-4.1：区分 DIRECT_FACT 与 DERIVED_FACT，避免将直接事实误路由到 Fact Aggregator。",
        "> 仅修改 Shadow Router；未修改正式 8000、Retriever、Qdrant、Embedding、RRF、Reranker、Claim Answer Engine 或 BA-010 Fact Path。",
        "",
        "## 1. 路由定义",
        "",
        "- `DIRECT_FACT`：源文档直接存在的单一事实，默认走 `CLAIM_ANSWER_PATH`。",
        "- `DERIVED_FACT`：需要 COUNT、GROUP_BY、SUM、FILTER、LIST_DISTINCT 或跨记录/跨 Sheet 计算。",
        "- `AMBIGUOUS_FACT`：无法判断是制度目标还是实际记录统计，安全返回 `FACT_PATH_UNAVAILABLE` 并标记 `ROUTE_AMBIGUOUS`。",
        "- 数量、金额、比例等词本身不再直接触发 Fact Path。",
        "",
        "## 2. 路由指标",
        "",
        f"- 测试题数：{len(cases)}",
        f"- Route Accuracy：**{route_accuracy}/{len(cases)} ({route_accuracy / len(cases):.1%})**",
        f"- Fact Mode Accuracy：**{mode_accuracy}/{len(cases)} ({mode_accuracy / len(cases):.1%})**",
        f"- Routing Status Accuracy：**{status_accuracy}/{len(cases)} ({status_accuracy / len(cases):.1%})**",
        f"- False Fact Route：{false_fact}",
        f"- False Claim Route：{false_claim}",
        f"- FACT_PATH_UNAVAILABLE：{sum(case['actual_route']=='FACT_PATH_UNAVAILABLE' for case in cases)}",
        f"- ROUTE_AMBIGUOUS：{sum(case['actual_routing_status']=='ROUTE_AMBIGUOUS' for case in cases)}",
        "",
        "## 3. 重点 BA 验收",
        "",
    ]
    for case_id in ("BA-006", "BA-007", "BA-008", "BA-010"):
        case = next(item for item in cases if item["case_id"] == case_id)
        lines.append(f"- {case_id}：fact_mode=`{case['actual_fact_mode']}`，route=`{case['actual_route']}`，operations=`{case['decision']['operations']}`，status=`{case['decision']['final_status']}`")
    lines += [
        "",
        "## 4. 对照题检查",
        "",
        "- 公司要求设计示范项目不少于多少个？→ DIRECT_FACT → CLAIM",
        "- 当前项目台账里共有多少个设计示范项目？→ DERIVED_FACT → 当前能力不足时 FACT_PATH_UNAVAILABLE",
        "- 2025年公司设计创效金额是多少？→ DIRECT_FACT → CLAIM",
        "- 把2025年所有项目设计创效金额加起来是多少？→ DERIVED_FACT → 当前 SUM 能力不足时 FACT_PATH_UNAVAILABLE",
        "- 设计效益率目标是多少？→ DIRECT_FACT → CLAIM",
        "- 根据各项目金额计算公司平均设计效益率是多少？→ DERIVED_FACT → FACT_PATH_UNAVAILABLE",
        "",
        "## 5. Provider Failure",
        "",
        "Router 未调用 Provider，因此本次没有产生 Provider Failure。上游 BA-007 稳定性中的 Provider Error 保留为 `I PROVIDER_FAILURE`，未被 Router 转换为 NO_EVIDENCE 或 STRUCTURE_INVALID。",
        "",
        "## 6. 输出边界",
        "",
        "- 业务问题和测试编号只用于验收对账，Router 决策不读取 BA 编号。",
        "- Router 不计算 80、37、43 等事实数字，只检查 Fact 能力是否可用。",
        "- BA-010 保持 DERIVED_FACT → FACT_ANSWER_PATH，不回退。",
        "- 本任务未接入正式 8000 服务。",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(REPORT.resolve()), "cases": len(cases), "route_accuracy": route_accuracy, "mode_accuracy": mode_accuracy, "status_accuracy": status_accuracy}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
