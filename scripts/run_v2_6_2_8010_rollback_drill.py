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
CANARY = [
    ("CANARY-001", "设计管理策划书通常包含哪几个章节板块？", ("项目概况", "报批报建管理")),
    ("CANARY-002", '孝感奥体中心项目的建设规模与"一场两馆"座位数是多少？', ("14.76", "30000", "8000", "1500")),
    ("CANARY-003", "海南中心塔冠施工设置多少个支撑胎架？针对主梁变形采取了什么措施？", ("22个胎架", "预起拱40mm")),
    ("CANARY-004", "《设计方案比选提示清单》覆盖多少项比选内容？每项包含哪些字段？", ("18+", "专业类别", "比选阶段")),
    ("CANARY-005", "中建三局 AIDC 业务 2030 年的量化发展目标是多少？", ("920", "550", "33", "6%")),
    ("CANARY-006", "深圳华为百草园城市更新项目的合同额、工期与主要建筑指标是多少？", ("10.9", "1277", "1949")),
    ("CANARY-007", "中国气象局超算中心（和林格尔）项目的工期与运维转化成果是什么？", ("5955.22", "183", "242.29")),
    ("CANARY-008", "中国移动（呼和浩特）方舱式数据中心项目的规模、装机能力与工期节点是多少？", ("54170.7", "2876", "656")),
    ("CANARY-009", '西安医学院第一附属医院沣东院区项目"三个一"管理模式的效益率与主材自购率是多少？', ("41.98", "68%", "117")),
    ("CANARY-010", "金盛兰储能电站一期项目的设计单位、超概风险与结算上限是什么？", ("陕西君奥电力", "超概", "结算上限")),
]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_mode(text: str | bytes) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    match = re.search(r"(?m)^v2_primary_mod[LOCAL_PATH_REDACTED]*['\"]?([^'\"\s#]+)", text)
    return match.group(1).upper() if match else V1


def set_primary_mode(mode: str) -> None:
    original = CONFIG.read_bytes()
    replacement = f"v2_primary_mode: '{mode}'".encode("utf-8")
    updated, count = re.subn(rb"(?m)^v2_primary_mode:[^\r\n]*", replacement, original, count=1)
    if count == 0:
        newline = b"\r\n" if b"\r\n" in original else b"\n"
        separator = b"" if not original or original.endswith((b"\n", b"\r")) else newline
        updated = original + separator + replacement + newline
    if updated == original:
        return
    CONFIG.write_bytes(updated)


def _validate_smoke_result(
    case_id: str,
    result: dict,
    required_terms: tuple[str, ...],
    expected_mode: str,
    expected_candidate_hash: str | None = None,
) -> dict:
    runtime = (result.get("debug") or {}).get("runtime_pointer") or {}
    pointer = runtime.get("mode")
    answer = str(result.get("answer") or "")
    citations = result.get("citations") or []
    if expected_mode == CANDIDATE:
        if pointer != CANDIDATE or result.get("answer_status") != "ANSWERED":
            raise RuntimeError(f"{case_id} candidate response is not verified")
        if not expected_candidate_hash or runtime.get("candidate_hash") != expected_candidate_hash:
            raise RuntimeError(f"{case_id} candidate hash mismatch: expected={expected_candidate_hash}, got={runtime.get('candidate_hash')}")
        missing = [term for term in required_terms if term not in answer]
        if missing or not citations:
            raise RuntimeError(f"{case_id} candidate smoke failed: missing={missing}, citations={len(citations)}")
    else:
        if pointer not in {None, V1} or not answer.strip():
            raise RuntimeError(f"{case_id} V1 restoration smoke failed: runtime_pointer={pointer}")
    return {
        "case_id": case_id,
        "question": result.get("question"),
        "answer_status": result.get("answer_status"),
        "citation_count": len(citations),
        "query_run_id": result.get("query_run_id"),
        "runtime_pointer": pointer or (V1 if expected_mode == V1 else None),
        "candidate_hash": runtime.get("candidate_hash"),
        "answer_excerpt": answer[:500],
    }


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
    launcher = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 660
    while launcher.poll() is None and time.monotonic() < deadline:
        time.sleep(0.5)
    if launcher.poll() is None:
        launcher.terminate()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()
        raise RuntimeError("Internal Trial Service start script did not finish after warmup")
    if launcher.returncode != 0:
        raise RuntimeError(f"Internal Trial Service start script exited with {launcher.returncode}")
    get_json("/api/health")

def get_json(path: str) -> dict:
    with urlopen(f"http://127.0.0.1:8010{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_runtime(expected_mode: str) -> dict:
    health = get_json("/api/health")
    if health.get("status") != "ok":
        raise RuntimeError("8010 health check failed")
    if _port_open(8000):
        raise RuntimeError("8000 listener detected during 8010-only drill")
    configured = primary_mode(CONFIG.read_bytes())
    if configured != expected_mode:
        raise RuntimeError(f"primary pointer mismatch: expected {expected_mode}, got {configured}")
    return {"health": health.get("status"), "configured_primary_mode": configured, "port_8000_listener": False}


def ask(case_id: str, question: str, required_terms: tuple[str, ...], expected_mode: str, expected_candidate_hash: str | None = None) -> dict:
    result = query_result(case_id, question)
    return _validate_smoke_result(case_id, result, required_terms, expected_mode, expected_candidate_hash)


def query_result(case_id: str, question: str) -> dict:
    payload = json.dumps(
        {"question": question, "trial_user": "reviewer-001", "conversation_id": "v262-rollback-drill", "node_id": case_id},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request("http://127.0.0.1:8010/api/v2/query", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def candidate_canary_result(case_id: str, question: str, required_terms: tuple[str, ...], result: dict, candidate_hash: str) -> dict:
    try:
        checked = _validate_smoke_result(case_id, result, required_terms, CANDIDATE, candidate_hash)
        return {**checked, "canary_status": "PASS"}
    except RuntimeError as error:
        runtime = (result.get("debug") or {}).get("runtime_pointer") or {}
        return {
            "case_id": case_id,
            "question": question,
            "answer_status": result.get("answer_status"),
            "citation_count": len(result.get("citations") or []),
            "query_run_id": result.get("query_run_id"),
            "runtime_pointer": runtime.get("mode"),
            "candidate_hash": runtime.get("candidate_hash"),
            "answer_excerpt": str(result.get("answer") or "")[:500],
            "canary_status": "FAIL",
            "failure": str(error),
        }


def ask_canary(case: tuple[str, str, tuple[str, ...]], candidate_hash: str) -> dict:
    case_id, question, required_terms = case
    return candidate_canary_result(case_id, question, required_terms, query_result(case_id, question), candidate_hash)


def _port_open(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port_release(port: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_open(port):
            return
        time.sleep(0.25)
    raise RuntimeError(f"port {port} did not release after the scoped trial stop")


def restart(mode: str) -> dict:
    set_primary_mode(mode)
    run_script(STOP)
    _wait_for_port_release(8010)
    start_service()
    return verify_runtime(mode)


def main() -> int:
    if "--execute" not in sys.argv:
        raise SystemExit("Refusing to alter 8010 without --execute.")
    before_config = CONFIG.read_bytes()
    if primary_mode(before_config) != V1:
        raise SystemExit("Rollback drill requires V1_PRIMARY as the starting pointer.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidate_hash = str(manifest.get("candidate_hash") or "")
    if not candidate_hash:
        raise SystemExit("Rollback drill requires a candidate manifest hash.")
    if REPORT.exists():
        archive = REPORT.with_name(f"{REPORT.stem}_pre_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}{REPORT.suffix}")
        archive.write_bytes(REPORT.read_bytes())
    report = {
        "schema_version": "knowledge_os_v2_6_2.8010_rollback_drill",
        "started_at": now(),
        "authorization": "OWNER_CONFIRMED_8010_ONLY_V1_TO_V262_TO_V1",
        "candidate_hash": candidate_hash,
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
        candidate_smoke = [ask(*case, CANDIDATE, candidate_hash) for case in SMOKE]
        report["steps"].append({"step": "V262_SMOKE", "results": candidate_smoke})
        canary_started = time.perf_counter()
        candidate_canary = []
        for case in CANARY:
            try:
                candidate_canary.append(ask_canary(case, candidate_hash))
            except Exception as error:
                candidate_canary.append({"case_id": case[0], "question": case[1], "canary_status": "ERROR", "error": f"{type(error).__name__}: {error}"})
                break
        candidate_canary.extend({"case_id": case[0], "question": case[1], "canary_status": "NOT_RUN"} for case in CANARY[len(candidate_canary):])
        report["candidate_canary_status"] = "PASS" if all(row["canary_status"] == "PASS" for row in candidate_canary) else "NOT_CLEARED"
        report["steps"].append({"step": "V262_CANARY", "count": len(candidate_canary), "pass_count": sum(row["canary_status"] == "PASS" for row in candidate_canary), "fail_count": sum(row["canary_status"] != "PASS" for row in candidate_canary), "elapsed_ms": round((time.perf_counter() - canary_started) * 1000, 3), "results": candidate_canary})
        report["steps"].append({"step": "ROLLBACK_TO_V1", "runtime": restart(V1)})
        v1_smoke = [ask(*case, V1) for case in SMOKE]
        report["steps"].append({"step": "V1_RESTORATION_SMOKE", "results": v1_smoke})
        if CONFIG.read_bytes() != before_config:
            raise RuntimeError("V1 configuration snapshot was not restored byte-for-byte")
        if _port_open(8000):
            raise RuntimeError("8000 listener detected after rollback")
        report["final_config_sha256"] = sha256(CONFIG)
        restored = True
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        try:
            if primary_mode(CONFIG.read_bytes()) != V1 or not _port_open(8010):
                restart(V1)
            if CONFIG.read_bytes() != before_config:
                CONFIG.write_bytes(before_config)
                run_script(STOP)
                start_service()
            runtime = verify_runtime(V1)
            restored = CONFIG.read_bytes() == before_config and runtime["health"] == "ok" and not _port_open(8000)
        except Exception as rollback_error:
            report["rollback_error"] = f"{type(rollback_error).__name__}: {rollback_error}"
    finally:
        report["restored_to_v1"] = restored
        report["final_config_sha256"] = sha256(CONFIG)
        report["completed_at"] = now()
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "restored_to_v1": restored, "candidate_hash": report["candidate_hash"], "report": str(REPORT)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" and restored else 1


if __name__ == "__main__":
    raise SystemExit(main())
