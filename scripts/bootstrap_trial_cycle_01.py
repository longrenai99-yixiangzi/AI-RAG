from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "shadow" / "trial_cycle_01"
DOCS = ROOT / "docs"
REGISTRY = DATA / "business_acceptance_registry.jsonl"
SOURCES = DATA / "source_closure_register.jsonl"

MANUAL = r"D:\工作\二公司技术部\2026\各类文件\设计管理\《项目设计管理手册》.pdf"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trial(question_id: str, question: str, source_file: str, source_status: str, domain: str, answer_type: str) -> dict[str, Any]:
    return {
        "schema_version": "trial-cycle-01.business-question.v1",
        "question_id": question_id,
        "question": question,
        "business_domain": domain,
        "organization": None,
        "project": None,
        "year": None,
        "specialty": None,
        "answer_type": answer_type,
        "correct_source_path": None,
        "correct_source_file_name": source_file,
        "correct_location": None,
        "key_facts": [],
        "must_include_claims": [],
        "must_not_use_sources": [],
        "expected_runtime_status": "OBSERVE_ONLY",
        "source_governance_status": source_status,
        "owner_confirmation_status": "OWNER_APPROVED_LEGACY_FACTS_PENDING_NORMALIZATION",
        "created_from": "BUSINESS_GOLD_OWNER_APPROVAL_RECORD",
        "registry_set": "TRIAL_QUESTION",
        "regression_enabled": False,
        "runtime_input": False,
        "formal_knowledge_publish": False,
        "created_at": _now(),
    }


def initial_registry() -> list[dict[str, Any]]:
    items = [
        _trial("BA-001", "设计任务书需要包含哪些内容？", "《项目设计管理手册》.pdf", "INDEXED_SHADOW", "设计管理", "STRUCTURED_CONTENT"),
        _trial("BA-002", "设计效益增量的计算方式？", "《项目设计管理手册》.pdf", "INDEXED_SHADOW", "设计管理", "FORMULA"),
        _trial("BA-003", "厂房产品线的方案比选案例包含哪些专业？", "中建三局二公司产品线设计方案比选典型案例汇编（厂房）（正文）.docx", "SOURCE_IDENTIFIED", "项目案例", "LIST"),
        _trial("BA-004", "自动喷淋系统管材方案比选可采用哪几种方案进行比选？", "设计方案比选提示清单7.23.xlsx", "INDEXED_SHADOW", "方案比选", "OPTION_COMPARISON"),
        _trial("BA-005", "特殊环境条件下集电线路电气设计的图审要点有哪些？", "全专业施工图审核要点提示汇编（2026年）.xlsx", "SOURCE_IDENTIFIED", "专业设计", "CHECKLIST"),
        _trial("BA-006", "2026年局设计与技术系统的责任状要求DOP平台电子图形文件数据中心上传数量是多少？", "3.二公司：2026年设计与技术专项责任书 .docx", "PENDING_APPROVAL", "技术管理", "DIRECT_FACT"),
        _trial("BA-007", "2026年设计示范项目的打造要求是什么？", "关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx", "PENDING_APPROVAL", "设计管理", "POLICY"),
        _trial("BA-008", "2025年公司设计创效金额是多少元？", "2025年饶淇述职.md", "INDEXED_SHADOW", "设计管理", "DIRECT_FACT"),
        _trial("BA-009", "2026年4月EPC项目双周推进会上，给土木公司的督办是什么？", "EPC项目设计管理工作监督任务表（2026年4月第一周）.xlsx", "PENDING_APPROVAL", "EPC", "DIRECT_FACT"),
        _trial("BA-010", "星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？", "设计管理策划书-星谷科创中心项目.docx", "INDEXED_SHADOW", "项目案例", "STRUCTURED_AGGREGATION"),
        {
            "schema_version": "trial-cycle-01.business-question.v1",
            "question_id": "TQ-001",
            "question": "设计评估是要评估设计文件的哪些方面的内容？",
            "business_domain": "设计管理",
            "organization": "二公司",
            "project": None,
            "year": None,
            "specialty": None,
            "answer_type": "STRUCTURED_CONTENT",
            "correct_source_path": MANUAL,
            "correct_source_file_name": "《项目设计管理手册》.pdf",
            "correct_location": "第40页、第41页",
            "key_facts": ["设计完整度评估", "设计深度评估", "技术可行性评估"],
            "must_include_claims": ["设计评估主要包括设计完整度评估、设计深度评估、技术可行性评估。"],
            "must_not_use_sources": [],
            "expected_runtime_status": "ANSWERED",
            "source_governance_status": "VERIFIED_RUNTIME",
            "owner_confirmation_status": "OWNER_CONFIRMED_CURRENT_TRIAL",
            "created_from": "owner_feedback_and_source_verification",
            "registry_set": "BUSINESS_GOLD",
            "regression_enabled": True,
            "runtime_input": False,
            "formal_knowledge_publish": False,
            "created_at": _now(),
        },
        {
            "schema_version": "trial-cycle-01.business-question.v1",
            "question_id": "TQ-002",
            "question": "二级设计进度计划，包含哪些节点？",
            "business_domain": "设计管理",
            "organization": "二公司",
            "project": None,
            "year": None,
            "specialty": None,
            "answer_type": "STRUCTURED_CONTENT",
            "correct_source_path": MANUAL,
            "correct_source_file_name": "《项目设计管理手册》.pdf",
            "correct_location": "第19页",
            "key_facts": ["初步设计完成", "基坑支护设计完成", "人防施工图外审完成", "专项方案完成", "专项施工图设计完成", "专项外部审查完成"],
            "must_include_claims": ["二级设计进度计划由一级设计进度计划分解制定。"],
            "must_not_use_sources": [],
            "expected_runtime_status": "ANSWERED",
            "source_governance_status": "VERIFIED_RUNTIME",
            "owner_confirmation_status": "OWNER_CONFIRMED_CURRENT_TRIAL",
            "created_from": "owner_feedback_and_source_verification",
            "registry_set": "BUSINESS_GOLD",
            "regression_enabled": True,
            "runtime_input": False,
            "formal_knowledge_publish": False,
            "created_at": _now(),
        },
        {
            "schema_version": "trial-cycle-01.business-question.v1",
            "question_id": "TQ-003",
            "question": "设计风险应对措施有哪些？",
            "business_domain": "设计管理",
            "organization": "二公司",
            "project": None,
            "year": None,
            "specialty": None,
            "answer_type": "STRUCTURED_TABLE",
            "correct_source_path": MANUAL,
            "correct_source_file_name": "《项目设计管理手册》.pdf",
            "correct_location": "第26页，表13-2",
            "key_facts": ["设计文件不满足报批报建进度要求风险", "设计条件不充分的风险", "设计水平欠缺、设计质量风险", "设计标准响应不全、不明确风险", "各专业设计之间的交叉提资、信息交流不足风险"],
            "must_include_claims": ["表13-2应逐项输出风险描述、应对策略和应对措施。"],
            "must_not_use_sources": [],
            "expected_runtime_status": "ANSWERED",
            "source_governance_status": "VERIFIED_RUNTIME",
            "owner_confirmation_status": "OWNER_CONFIRMED_CURRENT_TRIAL",
            "created_from": "owner_feedback_and_source_verification",
            "registry_set": "BUSINESS_GOLD",
            "regression_enabled": True,
            "runtime_input": False,
            "formal_knowledge_publish": False,
            "created_at": _now(),
        },
    ]
    return items


def source_register(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        status = item["source_governance_status"]
        source_state = {
            "VERIFIED_RUNTIME": "VERIFIED_RUNTIME",
            "INDEXED_SHADOW": "INDEXED_SHADOW",
            "PENDING_APPROVAL": "PENDING_APPROVAL",
        }.get(status, "SOURCE_IDENTIFIED")
        result.append({
            "schema_version": "trial-cycle-01.source-closure.v1",
            "question_id": item["question_id"],
            "question": item["question"],
            "source_status": source_state,
            "correct_source_path": item["correct_source_path"],
            "correct_source_file_name": item["correct_source_file_name"],
            "correct_location": item["correct_location"],
            "source_governance_status": status,
            "runtime_status": "NOT_YET_RUN",
            "next_action": {
                "VERIFIED_RUNTIME": "保留为已验证来源，纳入Business Gold回归。",
                "INDEXED_SHADOW": "运行时回归并补齐Owner关键事实。",
                "PENDING_APPROVAL": "等待业务负责人批准该来源进入Shadow，不重新扫描Root。",
                "SOURCE_IDENTIFIED": "人工确认物理路径及治理归属后进入审批判断。",
            }[source_state],
            "created_from": item["created_from"],
            "formal_knowledge_publish": False,
            "updated_at": _now(),
        })
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _report(items: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    business_gold = [item for item in items if item["registry_set"] == "BUSINESS_GOLD"]
    trial = [item for item in items if item["registry_set"] == "TRIAL_QUESTION"]
    states = {state: sum(row["source_status"] == state for row in sources) for state in sorted({row["source_status"] for row in sources})}
    return "\n".join([
        "# TRIAL-CYCLE-01 初始基线", "",
        "> 本阶段冻结 V2 核心架构，只建设真实业务验收资产与知识源闭环台账。不得把题目答案注入运行时，不扩大 Root，不自动发布知识。", "",
        "## TRIAL-01A：Business Acceptance Registry", "",
        f"- 初始问题：{len(items)} 题；Business Gold：{len(business_gold)} 题；Trial Questions：{len(trial)} 题。",
        "- 没有凭空补齐30～50题；其余题目将由8010真实提问和Owner确认逐步进入。",
        "- 10道历史BA保留来源确认记录，但因新Schema仍缺少部分机器可验关键事实，先放入Trial观察集，不虚报为完整新Gold。", "",
        "## TRIAL-01B：Source Closure Register", "",
        f"- Source状态分布：`{states}`。",
        "- `SOURCE_IDENTIFIED`：已知目标文件名，但尚待物理路径/治理确认。",
        "- `PENDING_APPROVAL`：来源已知但当前运行时没有读取授权；等待审批，不重复扫描Root。",
        "- `INDEXED_SHADOW` / `VERIFIED_RUNTIME`：可进入Shadow回归，不等于可写入正式知识库。", "",
        "## 后续准入", "",
        "1. Trial Question获得Owner确认的来源、位置和关键事实后，才升级为Business Gold。",
        "2. 每次修复必须同时运行Business Gold与Trial Questions；Trial只观察趋势，不用于准确率宣传。",
        "3. Source Closure状态未到`APPROVED_FOR_SHADOW`前，不导入外部正文。", "",
    ])


def main() -> int:
    items = initial_registry()
    sources = source_register(items)
    _write_jsonl(REGISTRY, items)
    _write_jsonl(SOURCES, sources)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "TRIAL_CYCLE_01_BASELINE.md").write_text(_report(items, sources), encoding="utf-8")
    print(json.dumps({"registry": str(REGISTRY), "source_register": str(SOURCES), "questions": len(items), "formal_knowledge_publish": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
