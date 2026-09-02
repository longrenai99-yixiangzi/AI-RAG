from pathlib import Path
from collections import Counter

import yaml


def test_gold_question_set_has_ten_required_categories() -> None:
    path = Path(__file__).parent / "gold_questions" / "golden_questions.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = payload["questions"]

    assert len(questions) == 50
    categories = {item["category"] for item in questions}
    assert categories == {
        "POLICY_QUERY",
        "CASE_QUERY",
        "METHOD_QUERY",
        "TEMPLATE_QUERY",
        "DISCIPLINE_QUERY",
    }
    assert Counter(item["category"] for item in questions) == {
        "POLICY_QUERY": 10,
        "CASE_QUERY": 10,
        "METHOD_QUERY": 10,
        "TEMPLATE_QUERY": 10,
        "DISCIPLINE_QUERY": 10,
    }
    assert all(item["question"].strip() for item in questions)
    assert all(item["expected_keywords"] for item in questions)
