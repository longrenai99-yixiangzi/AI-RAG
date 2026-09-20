from scripts.evaluate_knowledge_os_v2_retrieval import metrics


def test_retrieval_metrics_rank_expected_source():
    rows = [{"file_name": "甲.md"}, {"file_name": "乙.md"}]
    result, ranks = metrics(rows, ["甲 项目", "乙 项目"], [{"id": "Q1", "question": "甲", "expected_files": ["甲.md"]}])
    assert ranks == [1]
    assert result["recall@5"] == 1.0
    assert result["mrr"] == 1.0
