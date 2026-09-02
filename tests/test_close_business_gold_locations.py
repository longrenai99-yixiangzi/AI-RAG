from scripts.close_business_gold_locations import _claims_from_policy_extract, _close_one, _parse_number, _subquestions


def test_parse_profit_values_conservatively():
    assert _parse_number("110万元") == 110.0
    assert _parse_number("-") is None
    assert _parse_number("") is None


def test_gold_location_questions_are_explicit():
    assert "2026年局级DOP电子图形文件上传数量" in _subquestions("BA-006")
    assert "各专业条数" in _subquestions("BA-010")


def test_policy_claims_exclude_related_demo_sections():
    extracted = {
        "locations": [
            {"paragraph": 5, "section": "一、设计示范工程实施要求", "kind": "heading", "text": "一、设计示范工程实施要求"},
            {"paragraph": 6, "section": "一、设计示范工程实施要求", "kind": "requirement", "text": "底线"},
            {"paragraph": 10, "section": "二、深化设计示范工程实施要求", "kind": "heading", "text": "二、深化设计示范工程实施要求"},
            {"paragraph": 11, "section": "二、深化设计示范工程实施要求", "kind": "requirement", "text": "深化"},
        ]
    }
    claims = _claims_from_policy_extract(extracted)
    assert [claim["text"] for claim in claims] == ["底线"]


def test_ba006_supporting_source_does_not_create_gold_claim():
    location, claims = _close_one(
        "BA-006",
        "question",
        {
            "source_path": "supporting.pdf",
            "owner_confirmed_source_label": "责任状正文",
            "source_role": "SUPPORTING_SOURCE",
            "governance": "PENDING_APPROVAL",
        },
    )
    assert location["gold_location_status"] == "PARTIAL"
    assert location["source_fidelity_status"] == "UNRESOLVED"
    assert claims == []
