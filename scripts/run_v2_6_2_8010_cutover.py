from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from scripts.run_v2_6_2_8010_rollback_drill import CANDIDATE, CONFIG, MANIFEST, V1, ask, get_json as base_get_json, primary_mode, restart
except ModuleNotFoundError:
    from run_v2_6_2_8010_rollback_drill import CANDIDATE, CONFIG, MANIFEST, V1, ask, get_json as base_get_json, primary_mode, restart


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


def main() -> int:
    before = CONFIG.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report: dict = {
        "schema_version": "knowledge_os_v2_6_2.8010_cutover",
        "started_at": now(),
        "authorization": "OWNER_CONFIRMED_8010_FORMAL_CUTOVER_AND_CANARY",
        "candidate_hash": manifest.get("candidate_hash"),
        "formal_8000_touched": False,
        "formal_qdrant_write": False,
        "formal_sqlite_write": False,
        "previous_primary_mode": primary_mode(before),
        "steps": [],
        "status": "RUNNING",
    }
    try:
        if primary_mode(before) != V1:
            raise RuntimeError("CUTOVER_REQUIRES_V1_PRIMARY_START")
        if port_open(8000):
            raise RuntimeError("CUTOVER_BLOCKED_8000_LISTENER_PRESENT")
        report["steps"].append({"step": "BASELINE", "primary_mode": V1, "port_8000_listener": False})
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
        report["status"] = "FAIL_ROLLED_BACK_TO_V1"
        report["error"] = f"{type(error).__name__}: {error}"
        try:
            restart(V1)
            report["rollback"] = {"status": "PASS", "primary_mode": primary_mode(CONFIG.read_text(encoding="utf-8")), "port_8000_listener": port_open(8000)}
        except Exception as rollback_error:
            report["rollback"] = {"status": "FAIL", "error": f"{type(rollback_error).__name__}: {rollback_error}"}
    finally:
        report["completed_at"] = now()
        report["config_primary_mode_at_close"] = primary_mode(CONFIG.read_text(encoding="utf-8"))
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "active_primary_mode": report.get("active_primary_mode") or report.get("config_primary_mode_at_close"), "candidate_hash": report["candidate_hash"], "report": str(REPORT)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS_ACTIVE_V262" else 1


if __name__ == "__main__":
    raise SystemExit(main())
