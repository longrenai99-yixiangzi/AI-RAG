from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "internal_trial.yaml"
START = ROOT / "scripts" / "start_internal_trial.ps1"
STOP = ROOT / "scripts" / "stop_internal_trial.ps1"
MANIFEST = ROOT / "evaluation" / "knowledge_os_v2_6" / "remediation_candidate_v2_6_2.json"
REPORT = ROOT / "evaluation" / "knowledge_os_v2_6" / "v2_6_2_8010_rollback_drill.json"
V1 = "V1_PRIMARY"
CANDIDATE = "V2_6_2_CANDIDATE"
SMOKE = [
    ("SMOKE-001", "设计管理策划书通常包含哪几个章节板块？", ("项目概况", "报批报建管理")),
    ("SMOKE-002", '孝感奥体中心项目的建设规模与"一场两馆"座位数是多少？', ("14.76", "30000", "8000", "1500")),
    ("SMOKE-003", "海南中心塔冠施工设置多少个支撑胎架？针对主梁变形采取了什么措施？", ("22个胎架", "预起拱40mm")),
]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_mode(text: str) -> str:
    match = re.search(r"(?m)^v2_primary_mod[LOCAL_PATH_REDACTED]*['\"]?([^'\"\s#]+)", text)
    return match.group(1).upper() if match else V1


def set_primary_mode(mode: str) -> None:
    text = CONFIG.read_text(encoding="utf-8")
    if re.search(r"(?m)^v2_primary_mod[LOCAL_PATH_REDACTED]*.*$", text):
        updated = re.sub(r"(?m)^v2_primary_mod[LOCAL_PATH_REDACTED]*.*$", f"v2_primary_mode: '{mode}'", text)
    else:
        updated = text.rstrip() + f"\nv2_primary_mode: '{mode}'\n"
    CONFIG.write_text(updated, encoding="utf-8")


def run_script(path: Path) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=660,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{path.name} failed: {(result.stdout + result.stderr)[-1600:]}")
    return (result.stdout + result.stderr)[-1600:]


def start_service() -> None:
    """Start 8010 without waiting on the launcher shell after the service is ready."""
    launcher = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                get_json("/api/health")
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("8010 did not become healthy after start")
        # The launcher may wait on a detached browser/process even after uvicorn is
        # ready. Warm the chosen runtime directly, then release only that launcher.
        request = Request("http://127.0.0.1:8010/api/v2/warmup", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=600) as response:
            if not json.loads(response.read().decode("utf-8")).get("ready"):
                raise RuntimeError("8010 warmup returned not ready")
    finally:
        if launcher.poll() is None:
            launcher.terminate()
            try:
                launcher.wait(timeout=10)
            except subprocess.TimeoutExpired:
                launcher.kill()


def get_json(path: str) -> dict:
    with urlopen(f"http://127.0.0.1:8010{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_runtime(expected_mode: str) -> dict:
    health = get_json("/api/health")
    if health.get("status") != "ok":
        raise RuntimeError("8010 health check failed")
    if _port_open(8000):
        raise RuntimeError("8000 listener detected during 8010-only drill")
    configured = primary_mode(CONFIG.read_text(encoding="utf-8"))
    if configured != expected_mode:
        raise RuntimeError(f"primary pointer mismatch: expected {expected_mode}, got {configured}")
    return {"health": health.get("status"), "configured_primary_mode": configured, "port_8000_listener": False}


def ask(case_id: str, question: str, required_terms: tuple[str, ...], expected_mode: str) -> dict:
    payload = json.dumps(
        {"question": question, "trial_user": "reviewer-001", "conversation_id": "v262-rollback-drill", "node_id": case_id},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request("http://127.0.0.1:8010/api/v2/query", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    pointer = ((result.get("debug") or {}).get("runtime_pointer") or {}).get("mode")
    if expected_mode == CANDIDATE:
        if pointer != CANDIDATE or result.get("answer_status") != "ANSWERED":
            raise RuntimeError(f"{case_id} candidate response is not verified")
        missing = [term for term in required_terms if term not in str(result.get("answer") or "")]
        if missing or not result.get("citations"):
            raise RuntimeError(f"{case_id} candidate smoke failed: missing={missing}, citations={len(result.get('citations') or [])}")
    else:
        if pointer == CANDIDATE or not str(result.get("answer") or "").strip():
            raise RuntimeError(f"{case_id} V1 restoration smoke failed")
    return {
        "case_id": case_id,
        "question": question,
        "answer_status": result.get("answer_status"),
        "citation_count": len(result.get("citations") or []),
        "query_run_id": result.get("query_run_id"),
        "runtime_pointer": pointer or V1,
        "answer_excerpt": str(result.get("answer") or "")[:500],
    }


def _port_open(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def restart(mode: str) -> dict:
    set_primary_mode(mode)
    run_script(STOP)
    start_service()
    return verify_runtime(mode)


def main() -> int:
    if "--execute" not in sys.argv:
        raise SystemExit("Refusing to alter 8010 without --execute.")
    before_config = CONFIG.read_text(encoding="utf-8")
    if primary_mode(before_config) != V1:
        raise SystemExit("Rollback drill requires V1_PRIMARY as the starting pointer.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = {
        "schema_version": "knowledge_os_v2_6_2.8010_rollback_drill",
        "started_at": now(),
        "authorization": "OWNER_CONFIRMED_8010_ONLY_V1_TO_V262_TO_V1",
        "candidate_hash": manifest.get("candidate_hash"),
        "snapshot": {"config_sha256": sha256(CONFIG), "primary_mode": V1, "port_8000_listener": _port_open(8000)},
        "steps": [],
        "status": "RUNNING",
        "formal_8000_touched": False,
        "formal_qdrant_write": False,
        "formal_sqlite_write": False,
    }
    restored = False
    try:
        report["steps"].append({"step": "V1_BASELINE", "runtime": verify_runtime(V1)})
        report["steps"].append({"step": "SWITCH_TO_V262", "runtime": restart(CANDIDATE)})
        candidate_smoke = [ask(*case, CANDIDATE) for case in SMOKE]
        report["steps"].append({"step": "V262_SMOKE", "results": candidate_smoke})
        report["steps"].append({"step": "ROLLBACK_TO_V1", "runtime": restart(V1)})
        v1_smoke = [ask(*case, V1) for case in SMOKE]
        report["steps"].append({"step": "V1_RESTORATION_SMOKE", "results": v1_smoke})
        if CONFIG.read_text(encoding="utf-8") != before_config:
            raise RuntimeError("V1 configuration snapshot was not restored byte-for-byte")
        if _port_open(8000):
            raise RuntimeError("8000 listener detected after rollback")
        restored = True
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        try:
            if primary_mode(CONFIG.read_text(encoding="utf-8")) != V1 or not _port_open(8010):
                restart(V1)
            if CONFIG.read_text(encoding="utf-8") != before_config:
                CONFIG.write_text(before_config, encoding="utf-8")
                run_script(STOP)
                run_script(START)
            restored = primary_mode(CONFIG.read_text(encoding="utf-8")) == V1 and not _port_open(8000)
        except Exception as rollback_error:
            report["rollback_error"] = f"{type(rollback_error).__name__}: {rollback_error}"
    finally:
        report["restored_to_v1"] = restored
        report["completed_at"] = now()
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "restored_to_v1": restored, "candidate_hash": report["candidate_hash"], "report": str(REPORT)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" and restored else 1


if __name__ == "__main__":
    raise SystemExit(main())
