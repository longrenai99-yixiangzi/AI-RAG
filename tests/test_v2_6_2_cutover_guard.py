import json
import sys

import pytest

from scripts import run_v2_6_2_8010_cutover as cutover


def setup_files(tmp_path, monkeypatch, *, candidate_hash="candidate-hash", authorized=True):
    config = tmp_path / "internal_trial.yaml"
    config.write_bytes(b"trial_mode: true\nv2_primary_mode: 'V1_PRIMARY'\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"candidate_hash": candidate_hash}), encoding="utf-8")
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps({
        "decision_id": "OWNER-TEST-001",
        "candidate_hash": candidate_hash,
        "port_8010_persistent_primary_switch_authorized": authorized,
    }), encoding="utf-8")
    report = tmp_path / "cutover.json"
    monkeypatch.setattr(cutover, "CONFIG", config)
    monkeypatch.setattr(cutover, "MANIFEST", manifest)
    monkeypatch.setattr(cutover, "REPORT", report)
    return config, manifest, authorization, report


def test_default_invocation_is_read_only(tmp_path, monkeypatch, capsys):
    report = tmp_path / "cutover.json"
    monkeypatch.setattr(cutover, "REPORT", report)
    monkeypatch.setattr(sys, "argv", ["cutover"])

    assert cutover.main() == 0
    assert not report.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "PRECHECK_ONLY_NO_CHANGES"


def test_wrong_candidate_is_rejected_before_mutation(tmp_path, monkeypatch):
    config, _, authorization, report = setup_files(tmp_path, monkeypatch)
    before = config.read_bytes()
    monkeypatch.setattr(cutover, "port_open", lambda _port: False)
    monkeypatch.setattr(sys, "argv", [
        "cutover", "--execute", "--expected-candidate-hash", "wrong",
        "--authorization-file", str(authorization),
    ])

    with pytest.raises(SystemExit, match="does not match"):
        cutover.main()

    assert config.read_bytes() == before
    assert not report.exists()


def test_8000_listener_blocks_before_mutation(tmp_path, monkeypatch):
    config, _, authorization, report = setup_files(tmp_path, monkeypatch)
    before = config.read_bytes()
    monkeypatch.setattr(cutover, "port_open", lambda port: port == 8000)
    monkeypatch.setattr(sys, "argv", [
        "cutover", "--execute", "--expected-candidate-hash", "candidate-hash",
        "--authorization-file", str(authorization),
    ])

    with pytest.raises(SystemExit, match="8000"):
        cutover.main()

    assert config.read_bytes() == before
    assert not report.exists()


def test_authorized_execution_records_decision_and_activates_candidate(tmp_path, monkeypatch):
    config, _, authorization, report = setup_files(tmp_path, monkeypatch)
    state = {"running": False}

    def restart(mode):
        config.write_text(f"v2_primary_mode: '{mode}'\n", encoding="utf-8")
        state["running"] = True
        return {"configured_primary_mode": mode, "port_8000_listener": False}

    monkeypatch.setattr(cutover, "restart", restart)
    monkeypatch.setattr(cutover, "port_open", lambda port: state["running"] if port == 8010 else False)
    monkeypatch.setattr(cutover, "get_json", lambda path: {"status": "ok"} if path == "/api/health" else {"enabled": True})
    monkeypatch.setattr(cutover, "smoke_search", lambda: {"item_count": 1})
    monkeypatch.setattr(cutover, "smoke_diagnostics", lambda: {"overview_keys": [], "question_keys": []})
    monkeypatch.setattr(cutover, "ask", lambda *args: {"case_id": args[0], "candidate_hash": "candidate-hash"})
    monkeypatch.setattr(sys, "argv", [
        "cutover", "--execute", "--expected-candidate-hash", "candidate-hash",
        "--authorization-file", str(authorization),
    ])

    assert cutover.main() == 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "PASS_ACTIVE_V262"
    assert result["authorization"]["decision_id"] == "OWNER-TEST-001"
    assert cutover.primary_mode(config.read_bytes()) == cutover.CANDIDATE


def test_failed_execution_restores_stopped_state_and_config(tmp_path, monkeypatch):
    config, _, authorization, report = setup_files(tmp_path, monkeypatch)
    before = config.read_bytes()
    state = {"running": False}

    def restart(_mode):
        config.write_text("v2_primary_mode: 'V2_6_2_CANDIDATE'\n", encoding="utf-8")
        state["running"] = True
        raise RuntimeError("simulated restart failure")

    def restore(snapshot, was_running):
        assert was_running is False
        config.write_bytes(snapshot)
        state["running"] = False
        return {
            "status": "PASS", "config_restored_byte_for_byte": True,
            "service_running_before": False, "service_running_after": False,
            "primary_mode": cutover.V1,
        }

    monkeypatch.setattr(cutover, "restart", restart)
    monkeypatch.setattr(cutover, "restore_runtime", restore)
    monkeypatch.setattr(cutover, "port_open", lambda port: state["running"] if port == 8010 else False)
    monkeypatch.setattr(sys, "argv", [
        "cutover", "--execute", "--expected-candidate-hash", "candidate-hash",
        "--authorization-file", str(authorization),
    ])

    assert cutover.main() == 1
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "FAIL_RESTORED_PRE_EXECUTION_STATE"
    assert result["recovery"]["service_running_after"] is False
    assert config.read_bytes() == before
