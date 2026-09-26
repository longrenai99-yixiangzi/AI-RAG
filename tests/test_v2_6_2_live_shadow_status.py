import json

from scripts.refresh_v2_6_2_live_shadow_status import _exclude_owner_invalid_questions, _known_drill_query_ids, _reviewed_hit_query_ids, _runtime_code_counts


def test_excludes_only_same_candidate_rollback_drill_queries(tmp_path):
    candidate_hash = "fb919"
    current = tmp_path / "current.json"
    current.write_text(
        json.dumps({
            "candidate_hash": candidate_hash,
            "steps": [
                {"step": "V262_SMOKE", "results": [{"query_run_id": "smoke"}]},
                {"step": "V262_CANARY", "results": [{"query_run_id": "canary"}]},
                {"step": "V1_RESTORATION_SMOKE", "results": [{"query_run_id": "restore"}]},
                {"step": "V1_BASELINE", "results": [{"query_run_id": "baseline"}]},
            ],
        }),
        encoding="utf-8",
    )
    historical = tmp_path / "historical.json"
    historical.write_text(
        json.dumps({"candidate_hash": "d6bc", "steps": [{"step": "V262_SMOKE", "results": [{"query_run_id": "old"}]}]}),
        encoding="utf-8",
    )

    assert _known_drill_query_ids(candidate_hash, [current, historical]) == {"smoke", "canary", "restore"}


def test_owner_excluded_question_hash_does_not_count_as_live_sample():
    rows = [
        {"question_hash": "real-a", "query_run_id": "q1"},
        {"question_hash": "owner-invalid", "query_run_id": "q2"},
        {"question_hash": "owner-invalid", "query_run_id": "q3"},
    ]

    eligible, excluded = _exclude_owner_invalid_questions(rows, {"owner-invalid"})

    assert [row["question_hash"] for row in eligible] == ["real-a"]
    assert len(excluded) == 2


def test_runtime_code_hash_is_lineage_not_sample_volume_filter():
    rows = [
        {"question_hash": "old", "runtime_code_sha256": "old-code"},
        {"question_hash": "current", "runtime_code_sha256": "current-code"},
        {"question_hash": "unfingerprinted"},
    ]

    assert _runtime_code_counts(rows) == {"old-code": 1, "current-code": 1, "UNRECORDED": 1}


def test_shadow_review_overlay_only_resolves_scoped_hits():
    review = {
        "candidate_hash": "current-candidate",
        "records": [
            {"query_run_id": "false-lost", "disposition": "FALSE_LOST_HIT"},
            {"query_run_id": "fixed-new", "disposition": "FALSE_NEW_HIT_REMEDIATED", "remediated_runtime_code_sha256": "current-code"},
            {"query_run_id": "stale-new", "disposition": "FALSE_NEW_HIT_REMEDIATED", "remediated_runtime_code_sha256": "old-code"},
        ],
    }

    assert _reviewed_hit_query_ids(review, "current-candidate", "current-code") == {"false-lost", "fixed-new"}
    assert _reviewed_hit_query_ids(review, "other-candidate", "current-code") == set()
