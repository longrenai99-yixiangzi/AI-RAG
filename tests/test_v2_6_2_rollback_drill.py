import pytest

from scripts import run_v2_6_2_8010_rollback_drill as drill


def test_primary_mode_switch_preserves_all_other_config_bytes(tmp_path, monkeypatch):
    config = tmp_path / "internal_trial.yaml"
    before = b"trial_mode: true\r\nv2_primary_mode: 'V2_6_2_CANDIDATE'\r\nformal_port: 8000\r\n"
    config.write_bytes(before)
    monkeypatch.setattr(drill, "CONFIG", config)

    drill.set_primary_mode(drill.V1)

    expected = before.replace(b"v2_primary_mode: 'V2_6_2_CANDIDATE'", b"v2_primary_mode: 'V1_PRIMARY'")
    assert config.read_bytes() == expected
    assert drill.primary_mode(config.read_bytes()) == drill.V1


def test_candidate_smoke_requires_exact_manifest_hash():
    result = {
        "answer_status": "ANSWERED",
        "answer": "项目包含设计策划目标。",
        "citations": [{"citation_id": "S1"}],
        "debug": {"runtime_pointer": {"mode": drill.CANDIDATE, "candidate_hash": "wrong"}},
    }

    with pytest.raises(RuntimeError, match="candidate hash mismatch"):
        drill._validate_smoke_result("SMOKE-TEST", result, ("设计策划目标",), drill.CANDIDATE, "manifest-hash")


def test_canary_failure_retains_hash_and_missing_terms():
    result = {
        "answer_status": "ANSWERED",
        "answer": "项目包含设计策划目标。",
        "citations": [{"citation_id": "S1"}],
        "query_run_id": "QR-canary",
        "debug": {"runtime_pointer": {"mode": drill.CANDIDATE, "candidate_hash": "manifest-hash"}},
    }

    checked = drill.candidate_canary_result(
        "CANARY-TEST", "测试问题", ("设计策划目标", "报批报建管理"), result, "manifest-hash"
    )

    assert checked["canary_status"] == "FAIL"
    assert checked["candidate_hash"] == "manifest-hash"
    assert checked["query_run_id"] == "QR-canary"
    assert "报批报建管理" in checked["failure"]


def test_v1_smoke_accepts_legacy_response_without_runtime_pointer():
    result = {"answer_status": "ANSWERED", "answer": "V1 的可读答复。", "citations": []}

    checked = drill._validate_smoke_result("SMOKE-TEST", result, (), drill.V1)

    assert checked["runtime_pointer"] == drill.V1
