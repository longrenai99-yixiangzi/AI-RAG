from scripts.build_business_gold_v2 import _failure_record


def test_registration_candidate_is_source_gap():
    record = _failure_record(
        {
            "question_id": "BA-X",
            "baseline_observation": {"final_status": "NO_EVIDENCE"},
            "proposed_candidates": [{"registration_only": True}],
        }
    )

    assert record["preliminary_failure_type"] == "SOURCE_MISSING"


def test_structure_invalid_is_generation_failure_when_body_exists():
    record = _failure_record(
        {
            "question_id": "BA-X",
            "baseline_observation": {"final_status": "STRUCTURE_INVALID"},
            "proposed_candidates": [{"registration_only": False}],
        }
    )

    assert record["preliminary_failure_type"] == "GENERATION_FAILURE"
