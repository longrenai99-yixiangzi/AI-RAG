from __future__ import annotations

import json
import os
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import Settings

from .provider_reliability import ProviderFailure, ShadowReliableProvider, TimeoutPolicy, Transport


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class BudgetReservation:
    budget_id: str
    before: int
    after: int


class ProviderRequestBudget:
    """Small locked JSON ledger for Shadow HTTP request reservations."""

    def __init__(self, path: Path, *, task_id: str, provider: str, model: str, max_real_requests: int) -> None:
        self.path = path
        self.task_id = task_id
        self.provider = provider
        self.model = model
        self.max_real_requests = max(0, int(max_real_requests))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def create_or_load(self, *, initial_used: int = 0) -> dict[str, Any]:
        with self._lock():
            current = self._read_unlocked()
            if current is None:
                used = max(0, int(initial_used))
                current = self._state(
                    budget_id=f"budget-{uuid.uuid4().hex}",
                    used=used,
                    status="EXHAUSTED" if used >= self.max_real_requests else "ACTIVE",
                )
                self._write_unlocked(current)
            return current

    def snapshot(self) -> dict[str, Any]:
        with self._lock():
            current = self._read_unlocked()
            if current is None:
                current = self._state(
                    budget_id=f"budget-{uuid.uuid4().hex}",
                    used=0,
                    status="ACTIVE",
                )
                self._write_unlocked(current)
            return current

    def reserve(self, count: int = 1) -> BudgetReservation | None:
        count = max(1, int(count))
        with self._lock():
            current = self._read_unlocked() or self._state(
                budget_id=f"budget-{uuid.uuid4().hex}",
                used=0,
                status="ACTIVE",
            )
            remaining = int(current.get("remaining_real_requests") or 0)
            if remaining < count:
                current["status"] = "EXHAUSTED"
                current["updated_at"] = utc_now()
                self._write_unlocked(current)
                return None
            before = int(current.get("used_real_requests") or 0)
            after = before + count
            current["used_real_requests"] = after
            current["remaining_real_requests"] = max(0, int(current["max_real_requests"]) - after)
            current["status"] = "EXHAUSTED" if current["remaining_real_requests"] == 0 else "ACTIVE"
            current["updated_at"] = utc_now()
            self._write_unlocked(current)
            return BudgetReservation(str(current["budget_id"]), before, after)

    def close(self) -> dict[str, Any]:
        with self._lock():
            current = self._read_unlocked()
            if current is None:
                current = self._state(
                    budget_id=f"budget-{uuid.uuid4().hex}",
                    used=0,
                    status="ACTIVE",
                )
            current["status"] = "CLOSED"
            current["updated_at"] = utc_now()
            self._write_unlocked(current)
            return current

    def _state(self, *, budget_id: str, used: int, status: str) -> dict[str, Any]:
        return {
            "budget_id": budget_id,
            "task_id": self.task_id,
            "provider": self.provider,
            "model": self.model,
            "max_real_requests": self.max_real_requests,
            "used_real_requests": used,
            "remaining_real_requests": max(0, self.max_real_requests - used),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "status": status,
        }

    def _read_unlocked(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _write_unlocked(self, value: dict[str, Any]) -> None:
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Windows is the target, this keeps tests portable.
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ProviderCircuitBreaker:
    def __init__(self, path: Path, *, threshold: int = 5, cooldown_seconds: float = 60.0, now_fn: Callable[[], float] = time.time) -> None:
        self.path = path
        self.threshold = max(1, int(threshold))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.now_fn = now_fn
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._new_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._new_state()
        return value if isinstance(value, dict) else self._new_state()

    def before_request(self) -> tuple[str, dict[str, Any]]:
        state = self.snapshot()
        now = self.now_fn()
        if state.get("state") == "OPEN":
            opened_until = float(state.get("opened_until") or 0.0)
            if now < opened_until:
                return "OPEN", state
            state["state"] = "HALF_OPEN"
            state["half_open_probe_used"] = False
            state["last_reason"] = "COOLDOWN_ELAPSED"
            self._write(state)
        if state.get("state") == "HALF_OPEN":
            if state.get("half_open_probe_used"):
                return "OPEN", state
            state["half_open_probe_used"] = True
            state["last_reason"] = "HALF_OPEN_PROBE_RESERVED"
            self._write(state)
        return str(state.get("state") or "CLOSED"), state

    def record_success(self) -> dict[str, Any]:
        state = self.snapshot()
        state.update(
            {
                "state": "CLOSED",
                "consecutive_final_failures": 0,
                "half_open_probe_used": False,
                "opened_until": None,
                "last_reason": "PROVIDER_SUCCESS",
                "updated_at": utc_now(),
            }
        )
        self._write(state)
        return state

    def record_final_failure(self, category: str) -> dict[str, Any]:
        state = self.snapshot()
        circuit_categories = {"SERVER_5XX", "RATE_LIMITED", "REQUEST_TIMEOUT", "CONNECT_TIMEOUT", "CONNECTION_ERROR"}
        if category not in circuit_categories:
            state["consecutive_final_failures"] = 0
            state["last_reason"] = f"NON_CIRCUIT_FAILURE:{category}"
        else:
            state["consecutive_final_failures"] = int(state.get("consecutive_final_failures") or 0) + 1
            state["last_reason"] = f"FINAL_PROVIDER_FAILURE:{category}"
        if state.get("state") == "HALF_OPEN" or int(state.get("consecutive_final_failures") or 0) >= self.threshold:
            state["state"] = "OPEN"
            state["opened_until"] = self.now_fn() + self.cooldown_seconds
            state["half_open_probe_used"] = False
            state["last_reason"] = f"CIRCUIT_OPEN:{category}"
        state["updated_at"] = utc_now()
        self._write(state)
        return state

    def _new_state(self) -> dict[str, Any]:
        return {
            "state": "CLOSED",
            "threshold": self.threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "consecutive_final_failures": 0,
            "half_open_probe_used": False,
            "opened_until": None,
            "last_reason": "INITIAL",
            "updated_at": utc_now(),
        }

    def _write(self, value: dict[str, Any]) -> None:
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)


@dataclass(slots=True)
class RuntimeGuardResult:
    final_status: str
    final_provider_status: str
    content: str = ""
    attempt_count: int = 0
    http_requests: int = 0
    retry_delays: list[float] | None = None
    failures: list[dict[str, Any]] | None = None
    budget_before: int | None = None
    budget_after: int | None = None
    circuit_state_before: str = "CLOSED"
    circuit_state_after: str = "CLOSED"
    circuit_reason: str | None = None
    http_request_sent: bool = False
    provider_request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_status": self.final_status,
            "final_provider_status": self.final_provider_status,
            "content": self.content,
            "attempt_count": self.attempt_count,
            "http_requests": self.http_requests,
            "retry_delays": self.retry_delays or [],
            "failures": self.failures or [],
            "budget_before": self.budget_before,
            "budget_after": self.budget_after,
            "circuit_state_before": self.circuit_state_before,
            "circuit_state_after": self.circuit_state_after,
            "circuit_reason": self.circuit_reason,
            "http_request_sent": self.http_request_sent,
            "provider_request_id": self.provider_request_id,
        }


class ShadowProviderRuntimeGuard:
    """Adds persistent request budget and cross-question circuit protection."""

    def __init__(
        self,
        settings: Settings,
        budget: ProviderRequestBudget,
        circuit: ProviderCircuitBreaker,
        *,
        max_attempts: int = 3,
        backoff_seconds: tuple[float, float] = (1.0, 2.0),
        jitter_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        transport: Transport | None = None,
        telemetry_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.budget = budget
        self.circuit = circuit
        self.max_attempts = max(1, min(3, int(max_attempts)))
        self.backoff_seconds = backoff_seconds
        self.jitter_seconds = max(0.0, jitter_seconds)
        self.sleep_fn = sleep_fn
        self.rng = rng or random.Random()
        self.transport = transport
        self.telemetry_sink = telemetry_sink

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2_048,
        telemetry_context: dict[str, Any] | None = None,
    ) -> RuntimeGuardResult:
        context = telemetry_context or {}
        before_state, _ = self.circuit.before_request()
        budget_start = self.budget.snapshot()
        budget_before = int(budget_start.get("remaining_real_requests") or 0)
        if before_state == "OPEN":
            result = RuntimeGuardResult(
                "PROVIDER_CIRCUIT_OPEN",
                "PROVIDER_CIRCUIT_OPEN",
                budget_before=budget_before,
                budget_after=budget_before,
                circuit_state_before="OPEN",
                circuit_state_after="OPEN",
                circuit_reason="COOLDOWN_NOT_ELAPSED_OR_PROBE_IN_USE",
                http_request_sent=False,
            )
            self._emit(context, result, 0)
            return result
        if budget_before <= 0:
            result = RuntimeGuardResult(
                "PROVIDER_TEST_BUDGET_EXHAUSTED",
                "PROVIDER_TEST_BUDGET_EXHAUSTED",
                budget_before=budget_before,
                budget_after=budget_before,
                circuit_state_before=before_state,
                circuit_state_after=before_state,
                circuit_reason="TEST_EXECUTION_GUARD",
                http_request_sent=False,
            )
            self._emit(context, result, 0)
            return result

        attempts_allowed = 1 if before_state == "HALF_OPEN" else self.max_attempts
        failures: list[dict[str, Any]] = []
        delays: list[float] = []
        budget_after = budget_before
        for attempt in range(1, attempts_allowed + 1):
            reservation = self.budget.reserve()
            if reservation is None:
                result = RuntimeGuardResult(
                    "PROVIDER_TEST_BUDGET_EXHAUSTED",
                    "PROVIDER_TEST_BUDGET_EXHAUSTED",
                    attempt_count=attempt - 1,
                    http_requests=attempt - 1,
                    retry_delays=delays,
                    failures=failures,
                    budget_before=budget_before,
                    budget_after=0,
                    circuit_state_before=before_state,
                    circuit_state_after=self.circuit.snapshot().get("state", before_state),
                    circuit_reason="TEST_EXECUTION_GUARD",
                    http_request_sent=attempt > 1,
                )
                self._emit(context, result, attempt - 1)
                return result
            budget_after = max(0, self.budget.snapshot().get("remaining_real_requests", 0))
            provider = ShadowReliableProvider(
                self.settings,
                timeout=TimeoutPolicy(),
                max_attempts=1,
                sleep_fn=lambda _: None,
                transport=self.transport,
            )
            try:
                generation = provider.generate(
                    system_prompt,
                    user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    attempt_budget=1,
                    telemetry_context={**context, "attempt": attempt},
                )
                after_state = self.circuit.record_success()
                result = RuntimeGuardResult(
                    "GENERATION_READY",
                    "SUCCESS",
                    content=generation.content,
                    attempt_count=attempt,
                    http_requests=attempt,
                    retry_delays=delays,
                    failures=failures,
                    budget_before=budget_before,
                    budget_after=budget_after,
                    circuit_state_before=before_state,
                    circuit_state_after=str(after_state.get("state")),
                    circuit_reason=str(after_state.get("last_reason")),
                    http_request_sent=True,
                    provider_request_id=generation.request_id,
                )
                self._emit(context, result, attempt)
                return result
            except ProviderFailure as failure:
                failures.append(failure.to_dict())
                if failure.retryable and attempt < attempts_allowed:
                    delay = self._retry_delay(attempt, provider.last_response_headers)
                    delays.append(delay)
                    self.sleep_fn(delay)
                    continue
                after_state = self.circuit.record_final_failure(failure.category)
                final_status = "PROVIDER_TEMPORARY_FAILURE" if failure.retryable else "PROVIDER_PERMANENT_FAILURE"
                result = RuntimeGuardResult(
                    final_status,
                    failure.category,
                    attempt_count=attempt,
                    http_requests=attempt,
                    retry_delays=delays,
                    failures=failures,
                    budget_before=budget_before,
                    budget_after=budget_after,
                    circuit_state_before=before_state,
                    circuit_state_after=str(after_state.get("state")),
                    circuit_reason=str(after_state.get("last_reason")),
                    http_request_sent=True,
                )
                self._emit(context, result, attempt)
                return result
        raise AssertionError("runtime guard exhausted without a result")

    def _retry_delay(self, attempt: int, headers: dict[str, str] | None = None) -> float:
        for key, value in (headers or {}).items():
            if key.lower() == "retry-after":
                try:
                    return min(10.0, max(0.0, float(value)))
                except (TypeError, ValueError):
                    break
        base = self.backoff_seconds[min(attempt - 1, len(self.backoff_seconds) - 1)]
        return max(0.0, float(base) + self.rng.uniform(0.0, self.jitter_seconds))

    def _emit(self, context: dict[str, Any], result: RuntimeGuardResult, attempt_count: int) -> None:
        if self.telemetry_sink is None:
            return
        budget = self.budget.snapshot()
        self.telemetry_sink(
            {
                "budget_id": budget.get("budget_id"),
                "budget_before": result.budget_before,
                "budget_after": result.budget_after,
                "circuit_state_before": result.circuit_state_before,
                "circuit_state_after": result.circuit_state_after,
                "circuit_reason": result.circuit_reason,
                "http_request_sent": result.http_request_sent,
                "attempt_count": attempt_count,
                "request_id": context.get("request_id"),
                "pipeline_run_id": context.get("pipeline_run_id"),
                "question_id": context.get("question_id"),
                "provider": "openai_compatible_shadow_reliable",
                "model": self.settings.chat_model,
                "final_provider_status": result.final_provider_status,
                "final_status": result.final_status,
                "http_requests": result.http_requests,
                "retry_delays": result.retry_delays or [],
            }
        )
