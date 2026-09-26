from app.retrieval.query_planner_v1 import plan_query
from app.ingestion.atomic_search import scoring_target_phrase
from app.trial.live_shadow_v25 import _exact_phrase_rescue, _named_source_rescue, _period_scope_rescue


def test_h1_period_rescue_excludes_full_year_metric() -> None:
    question = "2025 \u5e74\u4e0a\u534a\u5e74\u4e8c\u516c\u53f8\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u7387\u662f\u591a\u5c11\uff1f"
    records = {
        "old_h1": {"evidence_id": "old_h1", "file_name": "2024\u5e74\u534a\u5e74\u603b\u7ed3.md", "source_path": "[LOCAL_PATH_REDACTED]", "text": "\u4e0a\u534a\u5e74\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u73873.20%"},
        "h1": {"evidence_id": "h1", "file_name": "2025\u5e74\u534a\u5e74\u603b\u7ed3.md", "source_path": "[LOCAL_PATH_REDACTED]", "text": "\u4e0a\u534a\u5e74\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u73873.31%"},
        "annual": {"evidence_id": "annual", "file_name": "2025\u5e74\u5e74\u5ea6\u603b\u7ed3.md", "source_path": "[LOCAL_PATH_REDACTED]", "text": "2025\u5e74\u4e09\u4f18\u4e00\u521b\u6574\u4f53\u521b\u6548\u73873.33%"},
    }
    rescued = _period_scope_rescue(question, plan_query(question), records)
    assert [row["evidence_id"] for row in rescued] == ["h1"]


def test_exact_named_source_rescue_keeps_only_direct_evidence() -> None:
    question = "\u4e2d\u5efa\u4e09\u5c40\u9879\u76ee\u6570\u5b57\u5efa\u9020\u7cfb\u7edf\u89e3\u51b3\u65b9\u6848\u91c7\u7528\u4ec0\u4e48\u6280\u672f\u67b6\u6784\uff1f"
    records = {
        "architecture": {"evidence_id": "architecture", "file_name": "04.\u4e2d\u5efa\u4e09\u5c40\u9879\u76ee\u6570\u5b57\u5efa\u9020\u7cfb\u7edf\u89e3\u51b3\u65b9\u6848.pdf", "text": "\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a\u4e09\u5c42\u67b6\u6784\u3002"},
        "other": {"evidence_id": "other", "file_name": "04.\u4e2d\u5efa\u4e09\u5c40\u9879\u76ee\u6570\u5b57\u5efa\u9020\u7cfb\u7edf\u89e3\u51b3\u65b9\u6848.pdf", "text": "\u9879\u76ee\u80cc\u666f\u3002"},
    }
    assert [row["evidence_id"] for row in _named_source_rescue(question, records)] == ["architecture"]


def test_scoring_question_rescues_the_matching_table_row() -> None:
    question = "中建三局局对二公司的2026年设计与技术系统专项责任书中，关于设计建设标准参考手册的评分标准是什么"
    records = {
        "wrong": {
            "evidence_id": "wrong",
            "file_name": "3.二公司：2026年设计与技术专项责任书 .docx",
            "text": "行：1 | 设计与技术支持中心能力建设 | 发布《深化设计能力建设实施细则》 | 20 | 未制定细则扣10分。",
        },
        "right": {
            "evidence_id": "right",
            "file_name": "3.二公司：2026年设计与技术专项责任书 .docx",
            "text": "行：4 | 设计管理 | 新增不少于2个业态项目设计建设标准参考手册。 | 20 | 每少建立一个业态项目设计建设标准参考手册扣1分。",
        },
    }
    assert [row["evidence_id"] for row in _exact_phrase_rescue(question, records)] == ["right"]


def test_scoring_target_phrase_handles_explicit_and_quoted_subjects() -> None:
    assert scoring_target_phrase("关于设计建设标准参考手册的评分标准是什么") == "设计建设标准参考手册"
    assert scoring_target_phrase("《设计优化案例汇编》未发布扣几分") == "设计优化案例汇编"
