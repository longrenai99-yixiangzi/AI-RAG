from scripts.reconcile_business_gold_v2 import _candidate_failure


def test_source_scope_gap_is_preserved_as_candidate_only():
    result = _candidate_failure(
        {
            "question_id": "BA-X",
            "runtime_answerability": "SOURCE_SCOPE_MISSING",
            "latest_system_status": "SOURCE_SCOPE_MISSING",
            "latest_accepted_artifact": {"task": "TASK-X", "path": "x.json"},
        }
    )

    assert result["candidate_failure_type"] == "SOURCE_MISSING"
    assert result["status"] == "CANDIDATE_ONLY"


def test_provider_failure_is_not_mislabeled_as_evidence_gap():
    result = _candidate_failure(
        {
            "question_id": "BA-X",
            "runtime_answerability": "ANSWERABLE",
            "latest_system_status": "EVIDENCE_READY_PROVIDER_TEMPORARY_FAILURE",
            "latest_accepted_artifact": {"task": "TASK-X", "path": "x.json"},
        }
    )

    assert result["candidate_failure_type"] == "GENERATION_FAILURE"
