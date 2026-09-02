from scripts.bootstrap_trial_cycle_01 import initial_registry, source_register
from scripts.run_trial_cycle_regression import _evaluate, _fact_present


def test_initial_business_registry_keeps_gold_and_trial_separate():
    rows = initial_registry()
    required = {"question_id", "question", "business_domain", "correct_source_path", "correct_location", "key_facts", "must_include_claims", "expected_runtime_status", "source_governance_status", "owner_confirmation_status", "created_from", "regression_enabled"}
    assert all(required <= set(row) for row in rows)
    assert sum(row["registry_set"] == "BUSINESS_GOLD" for row in rows) == 3
    assert sum(row["registry_set"] == "TRIAL_QUESTION" for row in rows) == 10
    assert all(row["runtime_input"] is False for row in rows)


def test_source_closure_register_distinguishes_governance_states():
    states = {row["question_id"]: row["source_status"] for row in source_register(initial_registry())}
    assert states["TQ-001"] == "VERIFIED_RUNTIME"
    assert states["BA-006"] == "PENDING_APPROVAL"
    assert states["BA-003"] == "SOURCE_IDENTIFIED"


def test_business_gold_regression_checks_source_and_owner_confirmed_facts():
    item = next(row for row in initial_registry() if row["question_id"] == "TQ-002")
    result = {
        "answer_status": "ANSWERED",
        "answer": "二级设计进度计划应包括初步设计完成、基坑支护设计完成、人防施工图外审完成、专项方案完成、专项施工图设计完成、专项外部审查完成。",
        "citations": [{"source_path": item["correct_source_path"]}],
        "provider_http_requests": 0,
    }
    evaluation = _evaluate(item, result)
    assert evaluation["regression_status"] == "PASSED"
    assert evaluation["gold_runtime_injection"] == 0


def test_table_business_gold_requires_multiple_confirmed_risk_rows():
    item = next(row for row in initial_registry() if row["question_id"] == "TQ-003")
    result = {
        "answer_status": "ANSWERED",
        "answer": "设计文件不满足报批报建进度要求风险；设计条件不充分的风险；设计水平欠缺、设计质量风险；设计标准响应不全、不明确风险；各专业设计之间的交叉提资、信息交流不足风险。",
        "citations": [{"source_path": item["correct_source_path"]}],
        "provider_http_requests": 0,
    }
    assert _evaluate(item, result)["regression_status"] == "PASSED"


def test_regression_fact_match_ignores_punctuation_and_whitespace_only():
    assert _fact_present("各专业设计之间的交叉提资、信息交流不足风险", "各专业设计之间的交叉提资，信息交流不足风险")
