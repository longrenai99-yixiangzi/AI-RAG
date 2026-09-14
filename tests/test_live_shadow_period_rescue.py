from app.retrieval.query_planner_v1 import plan_query
from app.trial.live_shadow_v25 import _period_scope_rescue


def test_h1_period_rescue_excludes_full_year_metric() -> None:
    question = "2025 \u5e74\u4e0a\u534a\u5e74\u4e8c\u516c\u53f8\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u7387\u662f\u591a\u5c11\uff1f"
    records = {
        "h1": {"evidence_id": "h1", "file_name": "2025\u5e74\u534a\u5e74\u603b\u7ed3.md", "source_path": "D:\\raw\\2025\u5e74\u534a\u5e74\u603b\u7ed3.md", "text": "\u4e0a\u534a\u5e74\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u73873.31%"},
        "annual": {"evidence_id": "annual", "file_name": "2025\u5e74\u5e74\u5ea6\u603b\u7ed3.md", "source_path": "D:\\raw\\2025\u5e74\u5e74\u5ea6\u603b\u7ed3.md", "text": "2025\u5e74\u4e09\u4f18\u4e00\u521b\u6574\u4f53\u521b\u6548\u73873.33%"},
    }
    rescued = _period_scope_rescue(question, plan_query(question), records)
    assert [row["evidence_id"] for row in rescued] == ["h1"]
