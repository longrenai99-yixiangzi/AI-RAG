from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"


def _source(kind: str, file_name: str, root: str, location: dict[str, Any]) -> dict[str, Any]:
    return {"source_role": kind, "file_name": file_name, "root": root, "location": location}


def artifact(task: str, relative_path: str) -> dict[str, str]:
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"required artifact is missing: {relative_path}")
    return {"task": task, "path": relative_path}


CARD_SPECS: dict[str, dict[str, Any]] = {
    "BA-001": {
        "artifacts": [
            artifact("TASK-017E-1.2.1", "evaluation/policy_facet_grounding/BA-001.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-001.json"),
        ],
        "latest_system_status": "EVIDENCE_READY_PROVIDER_TEMPORARY_FAILURE",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "PENDING_APPROVAL",
        "confidence": "MEDIUM",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "《项目设计管理手册》.pdf", "Root-002 frozen Shadow", {"page": 17}),
            _source("SUPPORTING_SOURCE", "EPC设计管理复盘总结（光谷能源站).docx", "Root-002 frozen Shadow", {"paragraph_start": 90, "paragraph_end": 91}),
            _source("SOURCE_LINEAGE_ONLY", "设计任务书.md", "Root-001", {"line_start": 8, "line_end": 10}),
        ],
        "candidate_expected_scope": "项目设计任务书管理；通用制度要求与项目复盘案例需分开表达。",
        "candidate_expected_authority": "PRIMARY=L2 管理手册；项目复盘与 Wiki 页仅作补充或来源链路。",
        "candidate_expected_answer_type": "TEMPLATE_QUERY",
        "candidate_expected_fact_mode": "NONE",
        "candidate_expected_subquestions": ["设计任务书应包含哪些内容", "设计任务书在何时编制、评审和交底"],
        "candidate_expected_claims": ["包含项目概况、工作范围、工作要求、设计技术要点", "需明确设计依据及管控要求"],
        "candidate_must_not_use_files": ["不得仅以 Wiki 概念页作为最终事实 Gold", "不得仅以单个项目复盘替代通用要求"],
        "candidate_runtime_expected_behavior": "CLAIM_ANSWER_PATH；Provider 失败时保留 Evidence，不降级为知识不存在。",
    },
    "BA-002": {
        "artifacts": [
            artifact("TASK-017C-2.1", "evaluation/ba002_formula_semantic_alignment/BA-002.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-002.json"),
        ],
        "latest_system_status": "GENERATED_WITH_SEMANTIC_MAPPING_UNCONFIRMED",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "PENDING_APPROVAL",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "《项目设计管理手册》.pdf", "Root-002 frozen Shadow", {"page": 30}),
            _source("SUPPORTING_SOURCE", "设计创效价值创造问答.md", "Root-001", {"line_start": 27, "line_end": 35}),
        ],
        "candidate_expected_scope": "项目设计创效经济效益额与设计创效率的正式口径；不自动等同于“设计效益增量”。",
        "candidate_expected_authority": "PRIMARY=L2 管理手册；问答页只提供方法与量化维度。",
        "candidate_expected_answer_type": "METHOD_QUERY",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["项目设计创效经济效益额公式", "设计创效率公式", "设计效益增量是否与上述指标同义"],
        "candidate_expected_claims": [
            "项目设计创效经济效益额=实施后实际经济效益额（不包括工期效益）-实施前预期经济效益额",
            "设计创效率=总创效金额/自施产值×100%",
            "设计效益增量与上述正式指标的术语映射尚未确认",
        ],
        "candidate_must_not_use_files": ["不得用项目案例替代正式公式", "不得把问答页作为公式主来源", "不得自行确认术语完全同义"],
        "candidate_runtime_expected_behavior": "CLAIM_FORMULA_SEMANTIC_PATH；生成正式公式并保留 SEMANTIC_MAPPING_UNCONFIRMED 边界。",
    },
    "BA-003": {
        "artifacts": [
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-003.json"),
            artifact("TASK-016A historical baseline", "docs/BUSINESS_QUERY_FAILURE_AUDIT.md"),
        ],
        "latest_system_status": "SOURCE_BODY_NOT_IN_APPROVED_SCOPE",
        "truth_source_status": "KNOWN_OUT_OF_SCOPE",
        "runtime_answerability": "SOURCE_SCOPE_MISSING",
        "governance_status": "OUT_OF_SCOPE",
        "confidence": "MEDIUM",
        "candidate_correct_file": [
            _source(
                "PRIMARY_GOLD_CANDIDATE",
                "中建三局二公司产品线设计方案比选典型案例汇编（厂房）（正文）.docx",
                "当前批准范围外",
                {"location": "厂房产品线专业目录/案例正文，待业务复核"},
            ),
            _source("SOURCE_LINEAGE_ONLY", "产品线设计方案比选典型案例汇编（厂房）.md", "Root-001", {"line_start": 1, "line_end": 1}),
        ],
        "candidate_expected_scope": "厂房产品线方案比选案例的专业目录。",
        "candidate_expected_authority": "正文案例库；Root-001 登记页只作来源链路。",
        "candidate_expected_answer_type": "MULTI_FACT",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["厂房产品线案例覆盖哪些专业"],
        "candidate_expected_claims": ["仅以厂房案例正文实际列出的专业为准"],
        "candidate_must_not_use_files": ["不得用医疗/学校产品线案例替代", "不得用登记页链接内容生成专业列表"],
        "candidate_runtime_expected_behavior": "SAFE_REFUSAL / SOURCE_SCOPE_MISSING，不使用相近案例替代。",
    },
    "BA-004": {
        "artifacts": [
            artifact("TASK-017C-3", "evaluation/ba004_answer_structure_hardening/run_01.json"),
            artifact("TASK-017E-1.1", "evaluation/claim_preflight_positive_path/BA-004.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-004.json"),
        ],
        "latest_system_status": "GENERATED_OPTION_QUERY",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "APPROVED",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "设计方案比选提示清单7.23.xlsx", "Root-001", {"sheet_name": "Sheet1", "row_number": 89}),
        ],
        "candidate_expected_scope": "自动喷淋系统管材变更；DN80 以下支管适用条件需保留。",
        "candidate_expected_authority": "L3 标准模板/方案比选清单。",
        "candidate_expected_answer_type": "OPTION_QUERY",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["可采用哪些管材方案", "各方案的适用/建议"],
        "candidate_expected_claims": ["传统镀锌钢管", "新型材料加强氯化聚氯乙烯(PVC-C)管材"],
        "candidate_must_include_evidence": ["Sheet1 第89行"],
        "candidate_must_not_use_files": ["不得用其他消防系统或其他管材方案替代"],
        "candidate_runtime_expected_behavior": "OPTION_QUERY；后端确定性渲染两个方案及来源。",
    },
    "BA-005": {
        "artifacts": [
            artifact("TASK-017E-1.1", "evaluation/claim_preflight_positive_path/BA-005.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-005.json"),
        ],
        "latest_system_status": "AUTHORITY_INSUFFICIENT",
        "truth_source_status": "UNKNOWN",
        "runtime_answerability": "AUTHORITY_INSUFFICIENT",
        "governance_status": "APPROVED",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "未确认：特殊环境集电线路电气设计的正式图审依据", "待补充", {"location": "待业务确认"}),
            _source("SUPPORTING_SOURCE", "EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx", "Root-001", {"role": "项目经验，仅作线索"}),
        ],
        "candidate_expected_scope": "特殊环境条件下集电线路电气设计图审。",
        "candidate_expected_authority": "需 L2/L3 正式规范、图审要求或经批准技术标准。",
        "candidate_expected_answer_type": "DISCIPLINE_QUERY",
        "candidate_expected_fact_mode": "NONE",
        "candidate_expected_subquestions": ["特殊环境条件", "集电线路电气图审要点", "正式依据"],
        "candidate_expected_claims": [],
        "candidate_must_not_use_files": ["不得把项目经验、复盘或通用案例当作正式图审依据"],
        "candidate_runtime_expected_behavior": "AUTHORITY_INSUFFICIENT；返回缺少正式依据说明，不生成图审要点。",
    },
    "BA-006": {
        "artifacts": [
            artifact("TASK-017E-1.1", "evaluation/claim_preflight_positive_path/BA-006.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-006.json"),
        ],
        "latest_system_status": "DIRECT_FACT_NO_SAME_SCOPE_EVIDENCE",
        "truth_source_status": "KNOWN_OUT_OF_SCOPE",
        "runtime_answerability": "SOURCE_SCOPE_MISSING",
        "governance_status": "OUT_OF_SCOPE",
        "confidence": "MEDIUM",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "局设计与技术系统责任状正文/目标数量资料（具体版本待业务确认）", "当前正式批准范围外", {"field": "DOP平台电子图形文件数据中心上传数量"}),
        ],
        "candidate_expected_scope": "2026年局级设计与技术系统责任状；组织范围必须为局级。",
        "candidate_expected_authority": "责任状正文或同范围正式目标文件。",
        "candidate_expected_answer_type": "DIRECT_FACT",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["DOP平台电子图形文件数据中心上传目标数量"],
        "candidate_expected_claims": [],
        "candidate_must_not_use_files": ["不得用项目级、二公司级或价值创造清单中的数量替代局级责任状目标"],
        "candidate_runtime_expected_behavior": "SOURCE_SCOPE_MISSING；安全拒答，不输出推测数量。",
    },
    "BA-007": {
        "artifacts": [
            artifact("TASK-017E-1.2.2", "evaluation/policy_local_grounding_window/BA-007.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-007.json"),
            artifact("TASK-018", "docs/V1_INTERNAL_TRIAL_READINESS_REPORT.md"),
        ],
        "latest_system_status": "GENERATED_TWO_VALID_POLICY_FACETS",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "PENDING_APPROVAL",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf", "Root-002 frozen Shadow", {"page": 6, "facet": "COMPANY/DESIGN_MANAGEMENT"}),
            _source("PRIMARY_GOLD_CANDIDATE", "关于印发中建三局2026年设计与技术工作计划的通知.pdf", "Root-002 frozen Shadow", {"page": 4, "facet": "GROUP/DETAILED_DESIGN"}),
        ],
        "candidate_expected_scope": "2026年；必须区分二公司设计管理示范项目与局级深化设计示范项目，不可合并为单一要求。",
        "candidate_expected_authority": "两个来源均为 L2 管理指南；Root-002 governance=PENDING_APPROVAL。",
        "candidate_expected_answer_type": "POLICY_QUERY",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["二公司设计管理示范项目要求", "局级深化设计示范项目要求"],
        "candidate_expected_claims": [
            "各主业公司打造不少于1个设计管理示范项目",
            "设计效益增量超*%或设计创效金额超**万",
            "聚焦深化设计计划管理等6大关键环节并制定标准化管控清单",
            "打造不少于1个深化设计示范项目",
        ],
        "candidate_must_not_use_files": ["不得把科技示范项目或 BIM 应用示范项目混入", "不得把公司与局级两个 Facet 合并成同一条要求"],
        "candidate_runtime_expected_behavior": "POLICY_QUERY；按两个已验证 Facet 分段回答并注明 Root-002 frozen Shadow governance。",
    },
    "BA-008": {
        "artifacts": [
            artifact("TASK-017C-1.1", "evaluation/direct_fact_scope_guard_hardening/BA-008.json"),
            artifact("TASK-017E-1.1", "evaluation/claim_preflight_positive_path/BA-008.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-008.json"),
        ],
        "latest_system_status": "GENERATED_COMPANY_DIRECT_FACT",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "APPROVED",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "2025年饶淇述职.md", "Root-001", {"line_start": 5, "line_end": 7}),
        ],
        "candidate_expected_scope": "二公司/公司级；2025年全年设计创效金额。",
        "candidate_expected_authority": "公司级年度述职/总结类来源；仅用于公司年度事实。",
        "candidate_expected_answer_type": "DIRECT_FACT",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["2025年公司设计创效金额"],
        "candidate_expected_claims": ["创效金额约4.45亿元", "确定性换算为约445,000,000元，并保留“约”"],
        "candidate_must_not_use_files": ["不得使用具体项目创效金额替代公司总额", "不得去掉“约”的限定"],
        "candidate_runtime_expected_behavior": "DIRECT_FACT_CLAIM_PATH；后端确定性单位换算，Provider 不参与计算。",
    },
    "BA-009": {
        "artifacts": [
            artifact("TASK-017E-1.1", "evaluation/claim_preflight_positive_path/BA-009.json"),
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-009.json"),
        ],
        "latest_system_status": "SOURCE_SCOPE_MISSING",
        "truth_source_status": "KNOWN_OUT_OF_SCOPE",
        "runtime_answerability": "SOURCE_SCOPE_MISSING",
        "governance_status": "OUT_OF_SCOPE",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "2026年4月EPC项目双周推进会督办表/会议纪要正文（具体文件待业务确认）", "当前批准范围外", {"target": "土木公司督办事项"}),
        ],
        "candidate_expected_scope": "2026年4月；EPC项目双周推进会；对象为土木公司。",
        "candidate_expected_authority": "会议纪要或督办表正文。",
        "candidate_expected_answer_type": "DIRECT_FACT",
        "candidate_expected_fact_mode": "DIRECT_FACT",
        "candidate_expected_subquestions": ["给土木公司的督办事项"],
        "candidate_expected_claims": [],
        "candidate_must_not_use_files": ["不得用设计服务台账、通用工作计划或其他项目督办替代"],
        "candidate_runtime_expected_behavior": "SOURCE_SCOPE_MISSING；安全拒答并登记知识缺口。",
    },
    "BA-010": {
        "artifacts": [
            artifact("TASK-017D", "evaluation/p0_integrated_shadow_regression/BA-010.json"),
            artifact("TASK-016E-2B.1", "evaluation/fact_answers/BA-010.json"),
        ],
        "latest_system_status": "FACT_RESULT_VALIDATED",
        "truth_source_status": "KNOWN_IN_SCOPE",
        "runtime_answerability": "ANSWERABLE",
        "governance_status": "PENDING_APPROVAL",
        "confidence": "HIGH",
        "candidate_correct_file": [
            _source("PRIMARY_GOLD_CANDIDATE", "方案比选与价值创造清单方案比选及价值创造.xlsx", "Root-002 frozen Shadow", {"sheet_name": "价值创造", "row_start": 4, "row_end": 87}),
        ],
        "candidate_expected_scope": "星谷科创中心项目；价值创造 Sheet；不使用其他项目或方案比选 Sheet 的数字。",
        "candidate_expected_authority": "经业务负责人确认口径的原始 Workbook；Root-002 governance=PENDING_APPROVAL。",
        "candidate_expected_answer_type": "AGGREGATION_QUERY",
        "candidate_expected_fact_mode": "DERIVED_FACT",
        "candidate_expected_subquestions": ["专业/原始分组", "各分组有效明细条数", "各分组利润>0条数", "总体增加效益条数"],
        "candidate_expected_claims": ["有效明细80条", "增加效益37条", "利润为空/未判定43条", "第88行公式汇总不计入明细"],
        "candidate_must_include_evidence": ["Workbook=方案比选与价值创造清单方案比选及价值创造.xlsx", "Sheet=价值创造", "row 4-87", "business_rule=利润>0"],
        "candidate_must_not_use_files": ["不得使用 Root-001 登记页作为统计依据", "不得使用其他项目价值创造清单", "不得把第88行汇总公式视为一条明细"],
        "candidate_runtime_expected_behavior": "FACT_ANSWER_PATH；后端确定性聚合和 Citation，不让 LLM 重算。",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile V2 Business Gold review material with latest accepted artifacts.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    prior_manifest = _read_json(args.output_dir / "gold_manifest.json")
    prior_by_id = {str(item["question_id"]): item for item in prior_manifest["records"]}
    p0_by_id = _load_p0_records()
    cards = []
    reconciliations = []
    for question_id in sorted(CARD_SPECS):
        previous = prior_by_id[question_id]
        spec = CARD_SPECS[question_id]
        p0 = p0_by_id[question_id]
        card = {
            "question_id": question_id,
            "question": previous["question"],
            "latest_accepted_artifact": spec["artifacts"][0],
            "supporting_artifacts": spec["artifacts"][1:],
            "latest_system_status": spec["latest_system_status"],
            "truth_source_status": spec["truth_source_status"],
            "runtime_answerability": spec["runtime_answerability"],
            "governance_status": spec["governance_status"],
            "owner_confirmation": "UNCONFIRMED",
            "candidate_correct_file": spec["candidate_correct_file"],
            "candidate_correct_location": [item["location"] for item in spec["candidate_correct_file"]],
            "candidate_expected_scope": spec["candidate_expected_scope"],
            "candidate_expected_authority": spec["candidate_expected_authority"],
            "candidate_expected_answer_type": spec["candidate_expected_answer_type"],
            "candidate_expected_fact_mode": spec["candidate_expected_fact_mode"],
            "candidate_expected_subquestions": spec["candidate_expected_subquestions"],
            "candidate_expected_claims": spec["candidate_expected_claims"],
            "candidate_must_include_evidence": spec.get("candidate_must_include_evidence", []),
            "candidate_must_not_use_files": spec["candidate_must_not_use_files"],
            "candidate_runtime_expected_behavior": spec["candidate_runtime_expected_behavior"],
            "confidence": spec["confidence"],
            "gold_status": "GOLD_UNCONFIRMED",
            "historical_candidate_files": [item.get("file_name") for item in previous.get("proposed_candidates", [])],
            "current_020a_input_fresh_run": bool(previous["baseline_observation"].get("fresh_run")),
            "historical_p0_fresh_run": bool(p0.get("fresh_run")),
        }
        if question_id == "BA-010":
            card["fact_authority_source"] = _ba010_authority_source()
        cards.append(card)
        reconciliations.append(
            {
                "question_id": question_id,
                "historical_baseline": artifact("TASK-016A historical baseline", "docs/BUSINESS_QUERY_FAILURE_AUDIT.md"),
                "latest_accepted_artifact": card["latest_accepted_artifact"],
                "supporting_artifacts": card["supporting_artifacts"],
                "historical_fresh_run_available": bool(p0.get("fresh_run")),
                "task020a_current_input_fresh_run": card["current_020a_input_fresh_run"],
                "selected_status": card["latest_system_status"],
                "reconciliation_rule": "late accepted artifact overrides historical baseline for Candidate Gold; owner_confirmation remains UNCONFIRMED",
            }
        )

    reconciliation = {
        "schema_version": "latest_artifact_reconciliation.v1",
        "global_artifacts_checked": [
            artifact("TASK-017D", "docs/P0_INTEGRATED_SHADOW_REGRESSION_REPORT.md"),
            artifact("TASK-017E-1", "docs/CLAIM_PREFLIGHT_SAFETY_GATE_REPORT.md"),
            artifact("TASK-017E-1.1", "docs/CLAIM_PREFLIGHT_POSITIVE_PATH_REPORT.md"),
            artifact("TASK-017E-1.2.2", "docs/POLICY_LOCAL_GROUNDING_WINDOW_REPORT.md"),
            artifact("TASK-018", "docs/V1_INTERNAL_TRIAL_READINESS_REPORT.md"),
        ],
        "historical_fresh_run_available": all(item["historical_fresh_run_available"] for item in reconciliations),
        "task020a_current_input_fresh_run": any(item["task020a_current_input_fresh_run"] for item in reconciliations),
        "records": reconciliations,
    }
    candidate_manifest = {
        "schema_version": "candidate_gold_manifest.v2",
        "owner_confirmation_required": True,
        "records": cards,
    }
    candidate_atlas = {
        "schema_version": "candidate_failure_atlas.v2",
        "final_failure_atlas_generated": False,
        "records": [_candidate_failure(card) for card in cards],
    }
    review_queue = {
        "schema_version": "gold_review_queue.v2.reconciled",
        "status": "PENDING_OWNER_REVIEW",
        "items": [_review_item(card) for card in cards],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "latest_artifact_reconciliation.json", reconciliation)
    _write_json(args.output_dir / "candidate_gold_manifest.json", candidate_manifest)
    _write_json(args.output_dir / "candidate_failure_atlas.json", candidate_atlas)
    _write_json(args.output_dir / "gold_review_queue.json", review_queue)
    (PROJECT_ROOT / "docs" / "BUSINESS_GOLD_V2_REPORT.md").write_text(
        _render_report(reconciliation, candidate_manifest, candidate_atlas), encoding="utf-8"
    )
    (PROJECT_ROOT / "docs" / "BUSINESS_GOLD_OWNER_REVIEW_SHEET.md").write_text(
        _render_review_sheet(cards), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cards": len(cards),
                "historical_fresh_run_available": reconciliation["historical_fresh_run_available"],
                "task020a_current_input_fresh_run": reconciliation["task020a_current_input_fresh_run"],
                "owner_confirmed": sum(card["owner_confirmation"] == "CONFIRMED" for card in cards),
                "output_dir": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _load_p0_records() -> dict[str, dict[str, Any]]:
    return {
        path.stem: _read_json(path)
        for path in (PROJECT_ROOT / "evaluation" / "p0_integrated_shadow_regression").glob("BA-*.json")
    }


def _ba010_authority_source() -> dict[str, Any]:
    aggregation = _read_json(PROJECT_ROOT / "evaluation" / "fact_aggregation" / "BA-010.json")
    fact_answer = _read_json(PROJECT_ROOT / "evaluation" / "fact_answers" / "BA-010.json")
    source_rows = [
        int(row["row_number"])
        for row in aggregation.get("source_rows", [])
        if isinstance(row, dict) and row.get("row_number") is not None
    ]
    return {
        "authoritative_source_path": aggregation["authoritative_source_path"],
        "target_document": aggregation["target_document"],
        "target_sheet": aggregation["target_sheet"],
        "source_rows": source_rows,
        "business_rule": {
            "benefit_semantics": aggregation["benefit_semantics"],
            "mapped_field": aggregation["mapped_field"],
            "operator": aggregation["operator"],
            "threshold": aggregation["threshold"],
            "source": aggregation["business_rule_source"],
        },
        "business_rule_source": aggregation["business_rule_source"],
        "reconciliation_status": fact_answer.get("fact_aggregation", {}).get("reconciliation_status"),
    }


def _candidate_failure(card: dict[str, Any]) -> dict[str, Any]:
    runtime = card["runtime_answerability"]
    if runtime == "SOURCE_SCOPE_MISSING":
        failure = "SOURCE_MISSING"
    elif runtime == "AUTHORITY_INSUFFICIENT":
        failure = "AUTHORITY_FAILURE"
    elif card["latest_system_status"] == "EVIDENCE_READY_PROVIDER_TEMPORARY_FAILURE":
        failure = "GENERATION_FAILURE"
    elif card["latest_system_status"] == "GENERATED_WITH_SEMANTIC_MAPPING_UNCONFIRMED":
        failure = "SEMANTIC_MAPPING_UNCONFIRMED"
    else:
        failure = "NONE_OR_PENDING_OWNER_REVIEW"
    return {
        "question_id": card["question_id"],
        "candidate_failure_type": failure,
        "basis": card["latest_accepted_artifact"],
        "status": "CANDIDATE_ONLY",
        "owner_confirmation": "UNCONFIRMED",
    }


def _review_item(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": card["question_id"],
        "status": "PENDING",
        "candidate_correct_file": card["candidate_correct_file"],
        "candidate_expected_claims": card["candidate_expected_claims"],
        "candidate_must_not_use_files": card["candidate_must_not_use_files"],
        "owner_confirmation": "UNCONFIRMED",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_report(
    reconciliation: dict[str, Any], manifest: dict[str, Any], atlas: dict[str, Any]
) -> str:
    cards = manifest["records"]
    lines = [
        "# Business Gold V2 Report",
        "",
        "> TASK-020A.1：只对齐最新已验收 Artifact 并生成 Candidate Gold Review Pack；不运行新的 Fresh Retrieval，不调用 LLM，不修改 Retriever、Router、Document Engine、Qdrant 或 8000。",
        "",
        "## 1. Artifact Reconciliation",
        "",
        f"- `historical_fresh_run_available`：`{str(reconciliation['historical_fresh_run_available']).lower()}`（TASK-017D 已存在 Fresh Run）。",
        f"- `task020a_current_input_fresh_run`：`{str(reconciliation['task020a_current_input_fresh_run']).lower()}`（当前 020A 输入包没有 fresh_run=true）。",
        "- 当前输入无 Fresh Run 不等于项目历史没有 Fresh Run。",
        "- 早期 `BUSINESS_QUERY_FAILURE_AUDIT` 仅保留为 historical baseline，不能覆盖后期验收结果。",
        "",
        "## 2. Candidate Gold Card 汇总",
        "",
        "| BA | Latest System Status | Truth Source | Runtime Answerability | Governance | Owner |",
        "|---|---|---|---|---|---|",
    ]
    for card in cards:
        lines.append(
            f"| {card['question_id']} | `{card['latest_system_status']}` | `{card['truth_source_status']}` | `{card['runtime_answerability']}` | `{card['governance_status']}` | `{card['owner_confirmation']}` |"
        )
    lines += ["", "## 3. Candidate Failure Atlas", "", "| BA | Candidate Failure | Final? |", "|---|---|---|"]
    for item in atlas["records"]:
        lines.append(f"| {item['question_id']} | `{item['candidate_failure_type']}` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |")
    lines += [
        "",
        "## 4. 关键对账结论",
        "",
        "- BA-002：正式手册存在两个公式；“设计效益增量”与正式指标的映射仍未确认。",
        "- BA-004：Sheet1 第89行的传统镀锌钢管与 PVC-C 两方案是候选事实来源。",
        "- BA-005：当前不是普通 Evidence Miss，而是正式图审依据不足。",
        "- BA-006、BA-009：目标正文处于当前批准范围外，运行时应安全拒答。",
        "- BA-007：公司设计管理与局级深化设计是两个已验证 Facet，Root-002 仍为 PENDING_APPROVAL。",
        "- BA-008：公司级年度金额为约4.45亿元；不得以项目金额替代。",
        "- BA-010：统计依据是价值创造 Sheet 行4-87及业务确认的利润>0规则，不是检索上下文或 Root-001 登记页。",
        "",
        "## 5. 输出",
        "",
        "- `evaluation/business_gold_v2/latest_artifact_reconciliation.json`",
        "- `evaluation/business_gold_v2/candidate_gold_manifest.json`",
        "- `evaluation/business_gold_v2/candidate_failure_atlas.json`",
        "- `evaluation/business_gold_v2/gold_review_queue.json`",
        "- `docs/BUSINESS_GOLD_OWNER_REVIEW_SHEET.md`",
        "",
        "## 6. 停止点",
        "",
        "所有 Candidate Gold Card 均为 `owner_confirmation=UNCONFIRMED`。本任务未生成 final_failure_atlas，未进入 TASK-020B。",
        "",
    ]
    return "\n".join(lines)


def _render_review_sheet(cards: list[dict[str, Any]]) -> str:
    lines = ["# Business Gold Owner Review Sheet", "", "> 每题均为候选复核材料，不代表系统或业务负责人已经确认 Gold。", ""]
    for card in cards:
        lines += [
            f"## {card['question_id']}",
            "",
            f"问题：{card['question']}",
            "",
            f"最新验收 Artifact：`{card['latest_accepted_artifact']['task']}` / `{card['latest_accepted_artifact']['path']}`",
            "",
            "候选正确来源：",
        ]
        for item in card["candidate_correct_file"]:
            lines.append(f"- `{item['source_role']}`：`{item['file_name']}`；root=`{item['root']}`；location=`{item['location']}`")
        lines += [
            "",
            f"最小引用位置：`{card['candidate_correct_location']}`",
            "",
            f"候选关键 Claims：{'; '.join(card['candidate_expected_claims']) or '待业务补充'}",
            "",
            f"适用 Scope：{card['candidate_expected_scope']}",
            "",
            f"Authority：{card['candidate_expected_authority']}",
            "",
            f"当前运行是否应答：`{card['runtime_answerability']}`；预期行为：{card['candidate_runtime_expected_behavior']}",
            "",
            f"当前 Root 治理状态：`{card['governance_status']}`；Truth Source：`{card['truth_source_status']}`",
            "",
            f"绝不能使用：{'; '.join(card['candidate_must_not_use_files']) or '无'}",
            "",
            f"系统置信度：`{card['confidence']}`；Owner Confirmation：`{card['owner_confirmation']}`",
            "",
            "业务负责人选择：",
            "",
            "[ ] 确认",
            "",
            "[ ] 修改后确认",
            "",
            "[ ] 不确认",
            "",
            "业务负责人备注：",
            "",
            "________________",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
