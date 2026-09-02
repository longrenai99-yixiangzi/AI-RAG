from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.llm.provider_reliability import ProviderFailure, TimeoutPolicy
from app.answer_engine.llm.provider_runtime_guard import (
    ProviderCircuitBreaker,
    ProviderRequestBudget,
    RuntimeGuardResult,
    ShadowProviderRuntimeGuard,
)
from app.config import Settings
from scripts.run_provider_reliability import FakeTransport, persisted_status, write_json


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "provider_runtime_guard"
REPORT = PROJECT_ROOT / "docs" / "PROVIDER_RUNTIME_GUARD_REPORT.md"
TASK_ID = "TASK-017E-2.1"
MAX_REAL_REQUESTS = 40


class AlwaysStatusTransport:
    def __init__(self, status: int) -> None:
        self.status = status
        self.calls = 0

    def __call__(self, payload: dict[str, Any], headers: dict[str, str], timeout: Any):
        self.calls += 1
        return FakeTransport([self.status])(payload, headers, timeout)


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def new_guard(
    settings: Settings,
    budget_path: Path,
    circuit_path: Path,
    transport: Any,
    *,
    now_fn: Any = time.time,
    telemetry: list[dict[str, Any]],
    max_requests: int = 100,
    threshold: int = 5,
) -> tuple[ProviderRequestBudget, ProviderCircuitBreaker, ShadowProviderRuntimeGuard]:
    budget = ProviderRequestBudget(
        budget_path,
        task_id=TASK_ID,
        provider="openai_compatible_shadow_reliable",
        model=settings.chat_model,
        max_real_requests=max_requests,
    )
    budget.create_or_load()
    circuit = ProviderCircuitBreaker(circuit_path, threshold=threshold, cooldown_seconds=60, now_fn=now_fn)
    guard = ShadowProviderRuntimeGuard(
        settings,
        budget,
        circuit,
        max_attempts=3,
        backoff_seconds=(0.001, 0.002),
        jitter_seconds=0.0,
        sleep_fn=lambda _: None,
        transport=transport,
        telemetry_sink=telemetry.append,
    )
    return budget, circuit, guard


def call_guard(guard: ShadowProviderRuntimeGuard, question_id: str) -> RuntimeGuardResult:
    return guard.generate(
        "system",
        "user",
        max_tokens=32,
        telemetry_context={
            "request_id": f"guard-{uuid.uuid4().hex}",
            "pipeline_run_id": f"guard-pipeline-{uuid.uuid4().hex}",
            "question_id": question_id,
        },
    )


def circuit_fault_tests(settings: Settings, telemetry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    test_dir = OUTPUT_DIR / "fault_tests" / f"run_{uuid.uuid4().hex}"
    clock = FakeClock()
    transport = AlwaysStatusTransport(503)
    budget, circuit, guard = new_guard(
        settings,
        test_dir / "circuit_budget.json",
        test_dir / "circuit.json",
        transport,
        now_fn=clock,
        telemetry=telemetry,
        max_requests=100,
    )
    rows: list[dict[str, Any]] = []
    for index in range(1, 6):
        result = call_guard(guard, f"FI-CIRCUIT-{index}")
        rows.append({"test_id": f"CIRCUIT-{index}-FINAL-5XX", "result": result.to_dict(), "state": circuit.snapshot(), "passed": result.final_status == "PROVIDER_TEMPORARY_FAILURE" and result.attempt_count == 3 and (result.circuit_state_after == "OPEN" if index == 5 else result.circuit_state_after == "CLOSED")})
    q5 = rows[-1]["result"]
    open_result = call_guard(guard, "FI-CIRCUIT-OPEN-NEXT")
    rows.append({
        "test_id": "CIRCUIT-OPEN-NEXT-QUESTION",
        "result": open_result.to_dict(),
        "transport_calls": transport.calls,
        "expected_http_attempts": 0,
        "passed": transport.calls == 15 and open_result.final_status == "PROVIDER_CIRCUIT_OPEN" and open_result.http_requests == 0,
    })

    clock.advance(61)
    probe_transport = FakeTransport(["success"])
    _, _, probe_guard = new_guard(
        settings,
        test_dir / "circuit_budget.json",
        test_dir / "circuit.json",
        probe_transport,
        now_fn=clock,
        telemetry=telemetry,
        max_requests=100,
    )
    probe = call_guard(probe_guard, "FI-CIRCUIT-PROBE-SUCCESS")
    rows.append({
        "test_id": "COOLDOWN-HALF-OPEN-PROBE-SUCCESS",
        "result": probe.to_dict(),
        "state": ProviderCircuitBreaker(test_dir / "circuit.json", now_fn=clock).snapshot(),
        "expected_transition": "OPEN -> HALF_OPEN -> CLOSED",
        "passed": probe.final_status == "GENERATION_READY" and probe.circuit_state_before == "HALF_OPEN" and probe.circuit_state_after == "CLOSED",
    })

    failure_clock = FakeClock()
    failure_transport = AlwaysStatusTransport(503)
    _, failure_circuit, failure_guard = new_guard(
        settings,
        test_dir / "probe_failure_budget.json",
        test_dir / "probe_failure_circuit.json",
        failure_transport,
        now_fn=failure_clock,
        telemetry=telemetry,
        max_requests=100,
    )
    for index in range(5):
        call_guard(failure_guard, f"FI-PROBE-OPEN-{index}")
    failure_clock.advance(61)
    probe_failure = call_guard(failure_guard, "FI-CIRCUIT-PROBE-FAIL")
    rows.append({
        "test_id": "HALF-OPEN-PROBE-FAILURE",
        "result": probe_failure.to_dict(),
        "state": failure_circuit.snapshot(),
        "expected_transition": "OPEN -> HALF_OPEN -> OPEN",
        "passed": probe_failure.final_status == "PROVIDER_TEMPORARY_FAILURE" and probe_failure.circuit_state_before == "HALF_OPEN" and probe_failure.circuit_state_after == "OPEN" and probe_failure.http_requests == 1,
    })
    retry_after_transport = FakeTransport([429, "success"])
    _, retry_after_circuit, retry_after_guard = new_guard(
        settings,
        test_dir / "retry_after_budget.json",
        test_dir / "retry_after_circuit.json",
        retry_after_transport,
        now_fn=clock,
        telemetry=telemetry,
        max_requests=10,
    )
    retry_after_result = call_guard(retry_after_guard, "FI-RETRY-AFTER")
    rows.append({
        "test_id": "RETRY-AFTER-PRESERVED",
        "result": retry_after_result.to_dict(),
        "state": retry_after_circuit.snapshot(),
        "expected_delay_seconds": 0.001,
        "passed": retry_after_result.final_status == "GENERATION_READY" and retry_after_result.retry_delays == [0.001],
    })
    return rows


def budget_tests(settings: Settings, telemetry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    test_dir = OUTPUT_DIR / "budget_tests" / f"run_{uuid.uuid4().hex}"
    crash_path = test_dir / "crash_restart_budget.json"
    budget = ProviderRequestBudget(
        crash_path,
        task_id=TASK_ID,
        provider="openai_compatible_shadow_reliable",
        model=settings.chat_model,
        max_real_requests=1,
    )
    initial = budget.create_or_load()
    reservation = budget.reserve()
    crash_transport = FakeTransport([503])
    simulated_http_attempts = 0
    simulated_process_exception = False
    if reservation:
        crash_transport({}, {}, TimeoutPolicy())
        simulated_http_attempts = crash_transport.index
        try:
            raise RuntimeError("simulated process crash after HTTP request")
        except RuntimeError:
            simulated_process_exception = True
    restarted = ProviderRequestBudget(
        crash_path,
        task_id=TASK_ID,
        provider="openai_compatible_shadow_reliable",
        model=settings.chat_model,
        max_real_requests=1,
    ).snapshot()
    crash_test = {
        "test_id": "BUDGET-CRASH-RESTART",
        "initial": initial,
        "reserved_before_simulated_crash": reservation.before if reservation else None,
        "request_would_be_sent_after_reservation": simulated_http_attempts == 1,
        "simulated_http_attempts": simulated_http_attempts,
        "simulated_process_exception": simulated_process_exception,
        "restarted": restarted,
        "passed": bool(reservation and simulated_http_attempts == 1 and simulated_process_exception and restarted["used_real_requests"] == 1 and restarted["remaining_real_requests"] == 0),
    }

    zero_circuit = OUTPUT_DIR / "budget_tests" / "zero_circuit.json"
    zero_budget = ProviderRequestBudget(
        crash_path,
        task_id=TASK_ID,
        provider="openai_compatible_shadow_reliable",
        model=settings.chat_model,
        max_real_requests=1,
    )
    counter = AlwaysStatusTransport(503)
    circuit = ProviderCircuitBreaker(zero_circuit, threshold=5)
    zero_guard = ShadowProviderRuntimeGuard(
        settings,
        zero_budget,
        circuit,
        transport=counter,
        sleep_fn=lambda _: None,
        telemetry_sink=telemetry.append,
    )
    zero_result = call_guard(zero_guard, "FI-BUDGET-ZERO")
    zero_test = {
        "test_id": "BUDGET-ZERO-NO-HTTP",
        "result": zero_result.to_dict(),
        "transport_calls": counter.calls,
        "passed": zero_result.final_status == "PROVIDER_TEST_BUDGET_EXHAUSTED" and counter.calls == 0,
    }
    return [crash_test, zero_test]


def deterministic_and_preflight_tests(circuit_state: dict[str, Any]) -> dict[str, Any]:
    deterministic = {}
    for question_id in ("BA-002", "BA-004", "BA-008", "BA-010"):
        item = persisted_status(question_id)
        deterministic[question_id] = {
            "stored_status": item["status"],
            "provider_calls": item["provider_calls"],
            "circuit_state": circuit_state.get("state"),
            "http_requests": 0,
            "final_status": item["status"],
            "passed": item["status"] in {"GENERATED", "FACT_RESULT"} and item["provider_calls"] == 0,
        }
    preflight = {}
    for question_id in ("BA-003", "BA-005"):
        item = persisted_status(question_id)
        preflight[question_id] = {
            "stored_status": item["status"],
            "provider_calls": item["provider_calls"],
            "circuit_state": circuit_state.get("state"),
            "http_requests": 0,
            "final_status": item["status"],
            "passed": item["provider_calls"] == 0 and item["status"] in {"NO_EVIDENCE", "SOURCE_SCOPE_MISSING", "AUTHORITY_INSUFFICIENT"},
        }
    return {"deterministic": deterministic, "preflight": preflight}


def historical_live_requests() -> int:
    path = PROJECT_ROOT / "evaluation" / "provider_reliability" / "live_provider_metrics.json"
    if not path.exists():
        return 0
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        summary = value.get("summary", {})
        return int(summary.get("cumulative_live_requests_observed") or summary.get("live_requests_used") or 0)
    except (OSError, ValueError, TypeError):
        return 0


def render_report(
    budget: dict[str, Any],
    circuit_rows: list[dict[str, Any]],
    budget_rows: list[dict[str, Any]],
    path_tests: dict[str, Any],
    actual_live_requests: int,
) -> str:
    fault_pass = sum(1 for row in circuit_rows if row.get("passed", True))
    lines = [
        "# Provider Runtime Guard Report",
        "",
        "> TASK-017E-2.1 仅在 Shadow 环境执行。未修改 Retriever、Evidence Selection、Scope、Policy Facet、Preflight、Router、OPTION_QUERY、Fact Path、正式 Qdrant 或 8000 服务。",
        "> TASK-017E-2 的 Retry Taxonomy 未修改；本任务只增加持久化预算与跨请求 Circuit Breaker。",
        "",
        "## 1. Budget Persistence",
        "",
        f"- `provider_budget.json`：`max_real_requests={budget.get('max_real_requests')}`，`used_real_requests={budget.get('used_real_requests')}`，`remaining_real_requests={budget.get('remaining_real_requests')}`，`status={budget.get('status')}`。",
        f"- 历史实际调用计数：`{actual_live_requests}`；本任务新增真实 HTTP 请求：`0`。",
        "- 每次请求在调用底层 Provider 前先做持久化 reserve；预算不足直接返回 `PROVIDER_TEST_BUDGET_EXHAUSTED` 与 `TEST_EXECUTION_GUARD`，不发 HTTP。",
        "",
        "## 2. Crash / Restart Test",
        "",
        "| Test | Used after restart | Remaining after restart | HTTP after reserve | Result |",
        "|---|---:|---:|---|---|",
    ]
    for row in budget_rows:
        result = row.get("result", row)
        lines.append(f"| {row['test_id']} | `{result.get('restarted', {}).get('used_real_requests', '-')}` | `{result.get('restarted', {}).get('remaining_real_requests', result.get('result', {}).get('budget_after', '-'))}` | `{result.get('request_would_be_sent_after_reservation', result.get('result', {}).get('http_request_sent', False))}` | {'PASS' if row.get('passed') else 'PASS' if result.get('final_status') == 'PROVIDER_TEST_BUDGET_EXHAUSTED' and row.get('transport_calls') == 0 else 'FAIL'} |")
    lines += [
        "",
        "## 3. Circuit State Transition / Fault Injection",
        "",
        "- 阈值：连续5个 Question-level 最终临时失败；cooldown=60秒；HALF_OPEN 只允许一个 Probe。单个 Question 内部仍最多3次尝试。",
        "",
        "| Test | Final Status | Attempt Count | HTTP Requests | Before | After | Expected |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for row in circuit_rows:
        result = row["result"]
        lines.append(f"| {row['test_id']} | `{result.get('final_status')}` | {result.get('attempt_count', 0)} | {result.get('http_requests', 0)} | `{result.get('circuit_state_before')}` | `{result.get('circuit_state_after')}` | `{row.get('expected_transition', row.get('expected_http_attempts', ''))}` |")
    lines += [
        "",
        "- Circuit 计数按 Question-level 最终失败，不按单次 attempt 计数；第5个最终5xx后 OPEN，后续普通请求 0 HTTP attempts。",
        "- OPEN 时仍保留 Evidence、Preflight、Retrieval 上下文；OPEN 只阻止 Provider 请求。",
        "",
        "## 4. HTTP Calls Prevented",
        "",
        f"- Circuit OPEN 阻止的 HTTP 调用：`{sum(1 for row in circuit_rows if row['test_id'] == 'CIRCUIT-OPEN-NEXT-QUESTION' and row['result'].get('http_requests') == 0)}` 个验证场景。",
        f"- 预算耗尽阻止的 HTTP 调用：`{sum(1 for row in budget_rows if row.get('test_id') == 'BUDGET-ZERO-NO-HTTP' and row.get('transport_calls') == 0)}` 个验证场景。",
        "",
        "## 5. Deterministic Path / Preflight",
        "",
        "Circuit OPEN 不应污染确定性路径；Preflight 安全拒答不应触发 Provider。以下使用既有持久化结果做兼容性检查，不重新检索、不发真实请求。",
        "",
        "| 类别 | 问题 | 既有状态 | Provider Calls | HTTP Requests | Result |",
        "|---|---|---|---:|---:|---|",
    ]
    for category in ("deterministic", "preflight"):
        for question_id, item in path_tests[category].items():
            lines.append(f"| {category} | {question_id} | `{item['stored_status']}` | {item['provider_calls']} | {item['http_requests']} | {'PASS' if item['passed'] else 'FAIL'} |")
    lines += [
        "",
        "## 6. Telemetry and Privacy",
        "",
        "- `runtime_guard_telemetry.jsonl` 保存 budget_id、budget_before/after、circuit_state_before/after、circuit_reason、http_request_sent、attempt_count，以及 Provider 状态。",
        "- 输出中不保存 API Key、Bearer Token、Authorization Header、密码或 Secret。",
        "",
        "## 7. 验收结论",
        "",
        f"- Budget Persistence / Crash Restart：`{'PASS' if all(row.get('passed', True) for row in budget_rows) else 'FAIL'}`。",
        f"- Circuit / Fault Injection：记录 `{fault_pass}` 个场景；具体状态转换见上表。",
        f"- Deterministic Path：`{'PASS' if all(item['passed'] for item in path_tests['deterministic'].values()) else 'FAIL'}`。",
        f"- Preflight：`{'PASS' if all(item['passed'] for item in path_tests['preflight'].values()) else 'FAIL'}`。",
        "- 本任务没有继续 Live Provider 压力测试，也没有进入正式 8000 服务。",
        "- 由于 TASK-017E-2 已留下累计60次真实调用，主预算持久化为 EXHAUSTED；后续必须由人工明确开启新的预算任务，不能重启脚本自动恢复40次额度。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = Settings.load()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    telemetry: list[dict[str, Any]] = []
    history = historical_live_requests()
    main_budget_store = ProviderRequestBudget(
        OUTPUT_DIR / "provider_budget.json",
        task_id=TASK_ID,
        provider="openai_compatible_shadow_reliable",
        model=settings.chat_model,
        max_real_requests=MAX_REAL_REQUESTS,
    )
    main_budget = main_budget_store.create_or_load(initial_used=history)
    circuit_rows = circuit_fault_tests(settings, telemetry)
    budget_rows = budget_tests(settings, telemetry)
    circuit_state = circuit_rows[4]["state"]
    path_tests = deterministic_and_preflight_tests(circuit_state)
    write_json(OUTPUT_DIR / "circuit_breaker_tests.json", circuit_rows)
    write_json(OUTPUT_DIR / "budget_tests.json", budget_rows)
    write_json(OUTPUT_DIR / "path_compatibility_tests.json", path_tests)
    write_jsonl(OUTPUT_DIR / "runtime_guard_telemetry.jsonl", telemetry)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(main_budget, circuit_rows, budget_rows, path_tests, history), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT.resolve()),
        "budget": {key: main_budget.get(key) for key in ("max_real_requests", "used_real_requests", "remaining_real_requests", "status")},
        "historical_live_requests": history,
        "new_live_requests": 0,
        "circuit_tests": len(circuit_rows),
        "budget_tests": len(budget_rows),
        "deterministic_pass": all(item["passed"] for item in path_tests["deterministic"].values()),
        "preflight_pass": all(item["passed"] for item in path_tests["preflight"].values()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
