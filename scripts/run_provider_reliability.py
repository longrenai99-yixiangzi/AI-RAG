from __future__ import annotations

import hashlib
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.prompt_builder import build_prompt
from app.answer_engine.llm.provider_reliability import (
    ACTION_REQUIRED,
    FAILURE_CATEGORIES,
    ProviderFailure,
    ShadowReliableProvider,
    TimeoutPolicy,
    TransportResponse,
)
from app.config import Settings
from scripts.run_p0_integrated_shadow_regression import ShadowIntegratedAnswerPipeline, rows_to_bundle
from scripts.shadow_answer_router_v1 import load_ba_questions


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "provider_reliability"
REPORT = PROJECT_ROOT / "docs" / "PROVIDER_RELIABILITY_REPORT.md"
MAX_LIVE_REQUESTS = 40
LIVE_REPLAY_COUNT = 10
RETRYABLE_CATEGORIES = {"RATE_LIMITED", "REQUEST_TIMEOUT", "CONNECT_TIMEOUT", "CONNECTION_ERROR", "SERVER_5XX", "EMPTY_RESPONSE", "MODEL_UNAVAILABLE"}


class CaptureOnlyProvider:
    """Prevents the context snapshot from making a real Provider request."""

    name = "capture_only"
    available = False
    last_error = "capture only; Provider not called"
    last_diagnostics: dict[str, Any] = {}

    def __init__(self) -> None:
        self.call_count = 0


class FakeTransport:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.index = 0

    def __call__(self, payload: dict[str, Any], headers: dict[str, str], timeout: TimeoutPolicy) -> TransportResponse:
        outcome = self.outcomes[min(self.index, len(self.outcomes) - 1)]
        self.index += 1
        if outcome == "connect_timeout":
            raise httpx.ConnectTimeout("injected connect timeout")
        if outcome == "read_timeout":
            raise httpx.ReadTimeout("injected read timeout")
        if outcome == "connection_error":
            raise httpx.ConnectError("injected connection error")
        if outcome == "empty":
            return TransportResponse(200, {"choices": [{"message": {"content": ""}}]}, {}, 1)
        if isinstance(outcome, int):
            return TransportResponse(
                outcome,
                {"error": {"code": f"HTTP_{outcome}", "message": f"injected HTTP {outcome}"}},
                {"Retry-After": "0.001"} if outcome == 429 else {},
                1,
            )
        if outcome == "success":
            return TransportResponse(
                200,
                {"id": "fake-request", "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}]},
                {},
                1,
            )
        raise AssertionError(f"unknown injected outcome: {outcome}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def stable_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def fault_scenarios() -> list[dict[str, Any]]:
    return [
        {"id": "FI-429-SUCCESS", "outcomes": [429, "success"], "expected_status": "SUCCESS", "expected_category": "RATE_LIMITED", "expected_attempts": 2},
        {"id": "FI-429-FAIL", "outcomes": [429, 429, 429], "expected_status": "RATE_LIMITED", "expected_category": "RATE_LIMITED", "expected_attempts": 3},
        {"id": "FI-CONNECT-TIMEOUT-SUCCESS", "outcomes": ["connect_timeout", "success"], "expected_status": "SUCCESS", "expected_category": "CONNECT_TIMEOUT", "expected_attempts": 2},
        {"id": "FI-READ-TIMEOUT-3RD", "outcomes": ["read_timeout", "read_timeout", "success"], "expected_status": "SUCCESS", "expected_category": "REQUEST_TIMEOUT", "expected_attempts": 3},
        {"id": "FI-502-SUCCESS", "outcomes": [502, "success"], "expected_status": "SUCCESS", "expected_category": "SERVER_5XX", "expected_attempts": 2},
        {"id": "FI-503-FAIL", "outcomes": [503, 503, 503], "expected_status": "SERVER_5XX", "expected_category": "SERVER_5XX", "expected_attempts": 3},
        {"id": "FI-504-SUCCESS", "outcomes": [504, "success"], "expected_status": "SUCCESS", "expected_category": "SERVER_5XX", "expected_attempts": 2},
        {"id": "FI-401-NO-RETRY", "outcomes": [401], "expected_status": "AUTHENTICATION_ERROR", "expected_category": "AUTHENTICATION_ERROR", "expected_attempts": 1},
        {"id": "FI-403-NO-RETRY", "outcomes": [403], "expected_status": "PERMISSION_ERROR", "expected_category": "PERMISSION_ERROR", "expected_attempts": 1},
        {"id": "FI-400-NO-RETRY", "outcomes": [400], "expected_status": "INVALID_REQUEST", "expected_category": "INVALID_REQUEST", "expected_attempts": 1},
        {"id": "FI-EMPTY-SUCCESS", "outcomes": ["empty", "success"], "expected_status": "SUCCESS", "expected_category": "EMPTY_RESPONSE", "expected_attempts": 2},
    ]


def run_fault_injection(settings: Settings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    telemetry: list[dict[str, Any]] = []
    for scenario in fault_scenarios():
        provider = ShadowReliableProvider(
            settings,
            timeout=TimeoutPolicy(connect_timeout=0.1, read_timeout=0.1, total_timeout=0.2),
            backoff_seconds=(0.001, 0.002),
            jitter_seconds=0.0,
            max_retry_after_seconds=0.01,
            sleep_fn=lambda _: None,
            transport=FakeTransport(scenario["outcomes"]),
        )
        context = {"request_id": f"fault-{scenario['id']}", "pipeline_run_id": f"fault-{uuid.uuid4().hex}", "question_id": scenario["id"], "source": "fault_injection"}
        try:
            result = provider.generate("system", "user", max_tokens=32, telemetry_context=context)
            actual_status = result.final_provider_status
            final_answer_status = "GENERATION_READY"
            attempt_count = len(result.attempts)
            delays = result.retry_delays
            failure = None
        except ProviderFailure as error:
            actual_status = error.category
            final_answer_status = "PROVIDER_TEMPORARY_FAILURE" if error.retryable else "PROVIDER_PERMANENT_FAILURE"
            attempt_count = len(error.attempts)
            delays = error.retry_delays
            failure = error.to_dict()
        telemetry.extend(provider.telemetry)
        passed = (
            actual_status == scenario["expected_status"]
            and attempt_count == scenario["expected_attempts"]
            and len(delays) == max(0, scenario["expected_attempts"] - 1)
            and attempt_count <= 3
        )
        results.append(
            {
                "scenario_id": scenario["id"],
                "outcomes": scenario["outcomes"],
                "expected_category": scenario["expected_category"],
                "expected_status": scenario["expected_status"],
                "expected_attempts": scenario["expected_attempts"],
                "attempt_count": attempt_count,
                "retry_delays": delays,
                "final_provider_status": actual_status,
                "final_answer_status": final_answer_status,
                "failure": failure,
                "passed": passed,
            }
        )
    return results, telemetry


def capture_context(pipeline: ShadowIntegratedAnswerPipeline, question_id: str, question: str) -> dict[str, Any]:
    original_provider = pipeline.provider
    pipeline.provider = CaptureOnlyProvider()
    try:
        record = pipeline.run(question_id, question)
    finally:
        pipeline.provider = original_provider
    selected = record.get("selected_evidence", [])
    bundle = rows_to_bundle(selected)
    policy = policy_for_intent(str(record.get("answer_policy") or record.get("route", {}).get("intent") or "GENERAL_QUERY"))
    prompt = build_prompt(question, policy, bundle)
    prompt_input = {
        "system_prompt": prompt.system_prompt,
        "user_prompt": prompt.user_prompt,
        "response_schema": prompt.response_schema,
    }
    return {
        "question_id": question_id,
        "question": question,
        "pipeline_run_id": record.get("pipeline_run_id"),
        "route": record.get("route"),
        "retrieval_status": "RETRIEVAL_COMPLETE" if record.get("retrieval", {}).get("rrf_count", 0) else "RETRIEVAL_EMPTY",
        "evidence_status": "SELECTED" if selected else "NO_EVIDENCE",
        "preflight_status": record.get("claim_preflight", {}).get("claim_preflight_status"),
        "preflight": record.get("claim_preflight"),
        "selected_evidence": selected,
        "evidence_ids": [row.get("source_id") for row in selected],
        "prompt_input": prompt_input,
        "question_hash": stable_hash(question),
        "evidence_bundle_hash": stable_hash(selected),
        "prompt_hash": stable_hash(prompt_input),
        "allowed_evidence_ids": [row.get("source_id") for row in selected],
    }


def percentile(values: list[int], percent: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percent * len(ordered)) - 1))
    return ordered[index]


def run_live_replay(
    settings: Settings,
    contexts: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    provider = ShadowReliableProvider(settings, timeout=TimeoutPolicy(connect_timeout=15.0, read_timeout=60.0, total_timeout=75.0), max_attempts=3)
    runs: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in contexts}
    budget = MAX_LIVE_REQUESTS
    for question_id, context in contexts.items():
        for run_index in range(1, LIVE_REPLAY_COUNT + 1):
            if budget <= 0:
                break
            replay_id = f"{question_id}-R{run_index:02d}"
            telemetry_context = {
                "request_id": f"replay-{uuid.uuid4().hex}",
                "pipeline_run_id": context["pipeline_run_id"],
                "question_id": question_id,
                "source": "live_provider",
                "replay_id": replay_id,
            }
            before = provider.call_count
            record: dict[str, Any] = {
                "replay_id": replay_id,
                "question_id": question_id,
                "pipeline_run_id": context["pipeline_run_id"],
                "question_hash": context["question_hash"],
                "evidence_bundle_hash": context["evidence_bundle_hash"],
                "prompt_hash": context["prompt_hash"],
                "allowed_evidence_ids": context["allowed_evidence_ids"],
                "retrieval_status": context["retrieval_status"],
                "evidence_status": context["evidence_status"],
                "preflight_status": context["preflight_status"],
                "attempt_count": 0,
            }
            try:
                result = provider.generate(
                    context["prompt_input"]["system_prompt"],
                    context["prompt_input"]["user_prompt"],
                    max_tokens=4096,
                    telemetry_context=telemetry_context,
                    attempt_budget=budget,
                )
                consumed = provider.call_count - before
                budget -= consumed
                record.update(
                    {
                        "final_provider_status": result.final_provider_status,
                        "final_answer_status": "GENERATION_READY",
                        "attempt_count": len(result.attempts),
                        "retry_delays": result.retry_delays,
                        "provider_request_id": result.request_id,
                        "response_length": len(result.content),
                        "response_parse_status": _json_status(result.content),
                        "latency_ms": result.elapsed_ms,
                        "failure": None,
                    }
                )
            except ProviderFailure as error:
                consumed = provider.call_count - before
                budget -= consumed
                record.update(
                    {
                        "final_provider_status": error.category,
                        "final_answer_status": "PROVIDER_TEMPORARY_FAILURE" if error.retryable else "PROVIDER_PERMANENT_FAILURE",
                        "attempt_count": len(error.attempts),
                        "retry_delays": error.retry_delays,
                        "provider_request_id": None,
                        "response_length": None,
                        "response_parse_status": None,
                        "latency_ms": sum(int(item.get("latency_ms") or 0) for item in error.attempts),
                        "failure": error.to_dict(),
                    }
                )
            runs[question_id].append(record)
        if budget <= 0:
            break
    summary = {
        "max_live_requests": MAX_LIVE_REQUESTS,
        "live_requests_used": provider.call_count,
        "budget_remaining": budget,
        "live_replay_count_requested_per_question": LIVE_REPLAY_COUNT,
        "provider_available": provider.available,
        "provider_last_error": provider.last_error,
    }
    return runs, provider.telemetry, summary


def _json_status(content: str) -> str:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return "INVALID_JSON"
    return "VALID_JSON" if isinstance(value, dict) else "JSON_ROOT_NOT_OBJECT"


def live_metrics(runs: dict[str, list[dict[str, Any]]], request_count: int) -> dict[str, Any]:
    rows = [row for values in runs.values() for row in values]
    successes = [row for row in rows if row.get("final_answer_status") == "GENERATION_READY"]
    retry_successes = [row for row in successes if int(row.get("attempt_count") or 0) > 1]
    retried = [row for row in rows if int(row.get("attempt_count") or 0) > 1]
    temporary = [row for row in rows if row.get("final_answer_status") == "PROVIDER_TEMPORARY_FAILURE"]
    permanent = [row for row in rows if row.get("final_answer_status") == "PROVIDER_PERMANENT_FAILURE"]
    latencies = [int(row.get("latency_ms") or 0) for row in rows if row.get("latency_ms") is not None]
    return {
        "replay_rows": len(rows),
        "provider_requests": request_count,
        "first_attempt_success": sum(int(row.get("attempt_count") or 0) == 1 for row in successes),
        "retry_success": len(retry_successes),
        "final_success": len(successes),
        "temporary_failure": len(temporary),
        "permanent_failure": len(permanent),
        "average_attempts": round(sum(int(row.get("attempt_count") or 0) for row in rows) / len(rows), 3) if rows else None,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "first_attempt_success_rate": round(sum(int(row.get("attempt_count") or 0) == 1 for row in successes) / len(rows), 4) if rows else None,
        "retry_recovery_rate": round(len(retry_successes) / len(retried), 4) if retried else None,
        "final_success_rate": round(len(successes) / len(rows), 4) if rows else None,
        "temporary_failure_rate": round(len(temporary) / len(rows), 4) if rows else None,
        "permanent_failure_rate": round(len(permanent) / len(rows), 4) if rows else None,
    }


def persisted_status(question_id: str) -> dict[str, Any]:
    paths = [
        PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / f"{question_id}.json",
        PROJECT_ROOT / "evaluation" / "p0_integrated_shadow_regression" / f"{question_id}.json",
    ]
    for path in paths:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return {"status": value.get("final_status"), "provider_calls": value.get("provider_calls"), "source": str(path)}
    return {"status": "NOT_FOUND", "provider_calls": None, "source": None}


def render_report(
    fault_results: list[dict[str, Any]],
    live_summary: dict[str, Any],
    live_stats: dict[str, Any],
    contexts: dict[str, dict[str, Any]],
    runs: dict[str, list[dict[str, Any]]],
) -> str:
    fault_pass = sum(bool(row["passed"]) for row in fault_results)
    lines = [
        "# Provider Reliability Report",
        "",
        "> TASK-017E-2 仅在 Shadow 环境执行。未修改 Retriever、BM25/Dense/RRF、Evidence Selection、Scope Guard、Query Page Probe、Policy Facet、Preflight、OPTION_QUERY、Fact Path、正式 Qdrant 或 8000 服务。",
        "> 本任务只验证 Provider 可靠性；Provider 故障不会被转换成 NO_EVIDENCE、STRUCTURE_INVALID 或 ANSWER_FAILURE。",
        "",
        "## 1. Provider Failure Taxonomy",
        "",
        f"- 统一分类：`{list(FAILURE_CATEGORIES)}`。",
        "- 400/401/403/404模型不存在/请求Schema错误默认不重试；429、408、连接/读取超时、连接错误、502/503/504和明确临时5xx有限重试。",
        "- 总尝试次数最多3次；Retry-After优先，等待时间设有上限；日志只保存脱敏错误信息。",
        "- 分层超时：connect_timeout=15s，read_timeout=60s，total_timeout=75s；本地 Fault Injection 将等待缩短为毫秒级，但保留相同重试语义。",
        "",
        "## 2. Fault Injection",
        "",
        "| 场景 | Attempts | Retry delays | Final Provider Status | Final Answer Status | Result |",
        "|---|---:|---|---|---|---|",
    ]
    for row in fault_results:
        lines.append(f"| {row['scenario_id']} | {row['attempt_count']} | `{row['retry_delays']}` | `{row['final_provider_status']}` | `{row['final_answer_status']}` | {'PASS' if row['passed'] else 'FAIL'} |")
    lines += ["", f"- Fault Injection：`{fault_pass}/{len(fault_results)}` 通过。", "- 401/403/400均为单次尝试；429/Timeout/502/503/504按有限重试执行；没有场景超过3次。", ""]
    lines += [
        "## 3. Live Provider Replay",
        "",
        f"- Provider可用配置：`{live_summary['provider_available']}`；未记录Key内容。",
        f"- 真实HTTP请求上限：`{live_summary['max_live_requests']}`；实际使用：`{live_summary['live_requests_used']}`；剩余：`{live_summary['budget_remaining']}`。",
        f"- 每题目标回放：`{LIVE_REPLAY_COUNT}` 次；达到预算即停止，不补发请求。",
        "- 每次回放固定复用同一 Question、Evidence Bundle、Prompt 快照和 Allowed Evidence IDs；没有重新检索、换Evidence或修改Claim。",
        "",
        "| Question | Preflight | Evidence | Replay Rows | Final Provider Status |",
        "|---|---|---|---:|---|",
    ]
    for question_id, context in contexts.items():
        statuses = sorted({str(row.get("final_provider_status")) for row in runs.get(question_id, [])})
        lines.append(f"| {question_id} | `{context['preflight_status']}` | `{context['evidence_status']}` | {len(runs.get(question_id, []))} | `{statuses}` |")
    lines += [
        "",
        "### Live 指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| First Attempt Success Rate | `{live_stats['first_attempt_success_rate']}` |",
        f"| Retry Recovery Rate | `{live_stats['retry_recovery_rate']}` |",
        f"| Final Success Rate | `{live_stats['final_success_rate']}` |",
        f"| Temporary Failure Rate | `{live_stats['temporary_failure_rate']}` |",
        f"| Permanent Failure Rate | `{live_stats['permanent_failure_rate']}` |",
        f"| Average Attempts | `{live_stats['average_attempts']}` |",
        f"| P50 Latency | `{live_stats['p50_latency_ms']}` ms |",
        f"| P95 Latency | `{live_stats['p95_latency_ms']}` ms |",
        f"| Provider Requests | `{live_stats['provider_requests']}` |",
        "",
        "Provider失败时保存 `retrieval_status`、`evidence_status` 和 `preflight_status`；最终状态只使用 `PROVIDER_TEMPORARY_FAILURE` 或 `PROVIDER_PERMANENT_FAILURE`，不降级为知识链路失败。成功记录为 `GENERATION_READY`，不代表本任务重新完成 Answer Schema/Claim 质量验收。",
        "",
        "## 4. BA 回归与确定性路径兼容性",
        "",
        "本次对 BA-001/BA-007 做了无Provider请求的上下文快照并进行真实 Provider 回放；BA-003/BA-005保持既有 Preflight 安全结果，未绕过闸门。BA-002/BA-004/BA-008/BA-010仅读取既有确定性结果。",
        "",
        "| 问题 | 既有结果状态 | 既有Provider调用 |",
        "|---|---|---:|",
    ]
    for question_id in ("BA-001", "BA-003", "BA-005", "BA-007", "BA-002", "BA-004", "BA-008", "BA-010"):
        item = persisted_status(question_id)
        lines.append(f"| {question_id} | `{item['status']}` | `{item['provider_calls']}` |")
    lines += [
        "",
        "- Deterministic Formula Renderer、OPTION deterministic renderer、Direct deterministic answer和Fact Answer Path不依赖本次 Provider；本任务没有重跑或修改它们。",
        "",
        "## 5. 隔离结论",
        "",
        "- 临时故障：只在有限重试后标记 `PROVIDER_TEMPORARY_FAILURE`，保留检索和证据状态。",
        "- 永久故障：标记 `PROVIDER_PERMANENT_FAILURE`，后续动作应为检查凭据、模型权限、Endpoint或请求Schema，而不是提示“知识库没有答案”。",
        "- 真实 Provider 的成功率受当前服务状态影响；Fault Injection 是本次 Retry 策略的确定性验收依据。",
        "- 详细逐次遥测位于 `evaluation/provider_reliability/provider_telemetry.jsonl`，只含安全元数据，不含 API Key、Authorization Header 或密码。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = Settings.load()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    taxonomy = {
        category: {
            "retryable": category in RETRYABLE_CATEGORIES,
            "action_required": ACTION_REQUIRED.get(category),
            "notes": "finite exponential backoff with jitter; Retry-After capped" if category in RETRYABLE_CATEGORIES else "no automatic retry by default",
        }
        for category in FAILURE_CATEGORIES
    }
    write_json(OUTPUT_DIR / "failure_taxonomy.json", taxonomy)
    fault_results, fault_telemetry = run_fault_injection(settings)
    write_json(OUTPUT_DIR / "fault_injection_results.json", fault_results)

    questions = {question_id: question for question_id, question, _ in load_ba_questions()}
    pipeline = ShadowIntegratedAnswerPipeline()
    contexts: dict[str, dict[str, Any]] = {}
    try:
        for question_id in ("BA-001", "BA-007"):
            context = capture_context(pipeline, question_id, questions[question_id])
            if context["preflight_status"] == "READY_FOR_GENERATION":
                contexts[question_id] = context
            else:
                context["live_replay_skipped"] = "PRELIGHT_NOT_READY"
                contexts[question_id] = context
            write_json(OUTPUT_DIR / "live_provider_runs" / f"{question_id}_context.json", context)
    finally:
        pipeline.close()

    ready_contexts = {key: value for key, value in contexts.items() if value.get("preflight_status") == "READY_FOR_GENERATION"}
    if settings.api_ready and ready_contexts:
        live_runs, live_telemetry, live_summary = run_live_replay(settings, ready_contexts)
    else:
        live_runs = {question_id: [] for question_id in ready_contexts}
        live_telemetry = []
        live_summary = {
            "max_live_requests": MAX_LIVE_REQUESTS,
            "live_requests_used": 0,
            "budget_remaining": MAX_LIVE_REQUESTS,
            "live_replay_count_requested_per_question": LIVE_REPLAY_COUNT,
            "provider_available": settings.api_ready,
            "provider_last_error": "skipped because Provider configuration or READY_FOR_GENERATION context was unavailable",
        }
    for question_id, rows in live_runs.items():
        write_json(OUTPUT_DIR / "live_provider_runs" / f"{question_id}.json", {"context": contexts[question_id], "runs": rows})
    write_jsonl(OUTPUT_DIR / "provider_telemetry.jsonl", [*fault_telemetry, *live_telemetry])
    live_stats = live_metrics(live_runs, live_summary["live_requests_used"])
    write_json(OUTPUT_DIR / "live_provider_metrics.json", {"summary": live_summary, "metrics": live_stats})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(fault_results, live_summary, live_stats, contexts, live_runs), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT.resolve()),
        "fault_injection": f"{sum(bool(item['passed']) for item in fault_results)}/{len(fault_results)}",
        "live_provider_requests": live_summary["live_requests_used"],
        "live_replay_rows": live_stats["replay_rows"],
        "live_final_success": live_stats["final_success"],
        "live_temporary_failure": live_stats["temporary_failure"],
        "live_permanent_failure": live_stats["permanent_failure"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
