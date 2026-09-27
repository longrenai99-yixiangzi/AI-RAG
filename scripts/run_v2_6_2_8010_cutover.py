from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

try:
    from scripts.run_v2_6_2_8010_rollback_drill import CANDIDATE, CONFIG, MANIFEST, V1, ask, load_execution_authorization, primary_mode, restart, restore_runtime, sha256
except ModuleNotFoundError:
    from run_v2_6_2_8010_rollback_drill import CANDIDATE, CONFIG, MANIFEST, V1, ask, load_execution_authorization, primary_mode, restart, restore_runtime, sha256


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evaluation" / "knowledge_os_v2_6" / "v2_6_2_8010_cutover.json"
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


def port_open(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def get_json(path: str, timeout: int = 15) -> dict:
    with urlopen(f"http://127.0.0.1:8010{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def smoke_search() -> dict:
    result = get_json("/api/v2/knowledge/search?q=%E8%AE%BE%E8%AE%A1%E7%AE%A1%E7%90%86%E7%AD%96%E5%88%92&limit=5", timeout=180)
    items = result.get("items") or []
    if not items:
        raise RuntimeError("IMMEDIATE_SMOKE_SEARCH_EMPTY")
    return {"item_count": len(items), "query": result.get("query")}


def smoke_diagnostics() -> dict:
    overview = get_json("/api/v2/knowledge/diagnostics/overview", timeout=180)
    questions = get_json("/api/v2/knowledge/diagnostics/questions?limit=1", timeout=180)
    if not isinstance(overview, dict) or not isinstance(questions, dict):
        raise RuntimeError("IMMEDIATE_SMOKE_DIAGNOSTICS_INVALID")
    return {"overview_keys": sorted(overview.keys()), "question_keys": sorted(questions.keys())}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Precheck or explicitly execute the scoped 8010 candidate cutover.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-candidate-hash")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--target-port", type=int, default=8010)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if not args.execute:
        print(json.dumps({
            "status": "PRECHECK_ONLY_NO_CHANGES",
            "execute_required": True,
            "target_port": 8010,
            "required_arguments": ["--execute", "--expected-candidate-hash", "--authorization-file"],
        }))
        return 0
    if args.target_port != 8010:
        raise SystemExit("Cutover is restricted to target port 8010.")
    if not args.expected_candidate_hash or args.authorization_file is None:
        raise SystemExit("--execute requires --expected-candidate-hash and --authorization-file.")
    before = CONFIG.read_text(encoding="utf-8")
    before_bytes = CONFIG.read_bytes()
    service_was_running = port_open(8010)
    if primary_mode(before) != V1:
        raise SystemExit("Cutover requires V1_PRIMARY as the starting pointer.")
    if port_open(8000):
        raise SystemExit("Cutover blocked because port 8000 has a listener.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidate_hash = str(manifest.get("candidate_hash") or "")
    if not candidate_hash or candidate_hash != args.expected_candidate_hash:
        raise SystemExit("Cutover candidate does not match --expected-candidate-hash.")
    authorization = load_execution_authorization(args.authorization_file, candidate_hash, "8010_cutover")
    if REPORT.exists():
        archive = REPORT.with_name(f"{REPORT.stem}_pre_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}{REPORT.suffix}")
        archive.write_bytes(REPORT.read_bytes())
    report: dict = {
        "schema_version": "knowledge_os_v2_6_2.8010_cutover",
        "started_at": now(),
        "authorization": authorization,
        "candidate_hash": candidate_hash,
        "formal_8000_touched": False,
        "formal_qdrant_write": False,
        "formal_sqlite_write": False,
        "snapshot": {
            "config_sha256": sha256(CONFIG),
            "previous_primary_mode": V1,
            "service_running": service_was_running,
            "port_8000_listener": False,
        },
        "steps": [],
        "status": "RUNNING",
    }
    mutated = False
    try:
        report["steps"].append({"step": "BASELINE", "primary_mode": V1, "port_8000_listener": False, "service_running": service_was_running})
        mutated = True
        report["steps"].append({"step": "CUTOVER_TO_V262", "runtime": restart(CANDIDATE)})
        health = get_json("/api/health")
        enabled = get_json("/api/v2/enabled")
        if health.get("status") != "ok" or enabled.get("enabled") is not True:
            raise RuntimeError("IMMEDIATE_SMOKE_HEALTH_OR_ENABLED_FAILED")
        report["steps"].append({"step": "IMMEDIATE_SMOKE_HEALTH", "health": health.get("status"), "enabled": enabled.get("enabled"), "primary_mode": primary_mode(CONFIG.read_text(encoding="utf-8"))})
        report["steps"].append({"step": "IMMEDIATE_SMOKE_SEARCH", "result": smoke_search()})
        report["steps"].append({"step": "IMMEDIATE_SMOKE_DIAGNOSTICS", "result": smoke_diagnostics()})
        smoke_answer = ask(*CANARY[0], CANDIDATE)
        report["steps"].append({"step": "IMMEDIATE_SMOKE_QA_CITATION", "result": smoke_answer})
        canary_started = time.perf_counter()
        canary = [ask(*case, CANDIDATE) for case in CANARY]
        report["steps"].append({"step": "CANARY", "count": len(canary), "elapsed_ms": round((time.perf_counter() - canary_started) * 1000, 3), "results": canary})
        if primary_mode(CONFIG.read_text(encoding="utf-8")) != CANDIDATE or port_open(8000):
            raise RuntimeError("CANARY_RUNTIME_POINTER_OR_8000_GUARD_FAILED")
        report["status"] = "PASS_ACTIVE_V262"
        report["active_primary_mode"] = CANDIDATE
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if mutated:
            try:
                report["recovery"] = restore_runtime(before_bytes, service_was_running)
                report["status"] = "FAIL_RESTORED_PRE_EXECUTION_STATE" if report["recovery"]["status"] == "PASS" else "FAIL_RECOVERY_FAILED"
            except Exception as recovery_error:
                report["status"] = "FAIL_RECOVERY_FAILED"
                report["recovery"] = {"status": "FAIL", "error": f"{type(recovery_error).__name__}: {recovery_error}"}
        else:
            report["status"] = "FAIL_NO_MUTATION"
    finally:
        report["completed_at"] = now()
        report["config_primary_mode_at_close"] = primary_mode(CONFIG.read_text(encoding="utf-8"))
        report["config_restored_byte_for_byte"] = CONFIG.read_bytes() == before_bytes
        report["service_running_at_close"] = port_open(8010)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "active_primary_mode": report.get("active_primary_mode") or report.get("config_primary_mode_at_close"), "candidate_hash": report["candidate_hash"], "report": str(REPORT)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS_ACTIVE_V262" else 1


if __name__ == "__main__":
    raise SystemExit(main())
