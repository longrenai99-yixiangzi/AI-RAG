from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import httpx

from app.config import Settings


FAILURE_CATEGORIES = (
    "RATE_LIMITED",
    "REQUEST_TIMEOUT",
    "CONNECT_TIMEOUT",
    "CONNECTION_ERROR",
    "SERVER_5XX",
    "EMPTY_RESPONSE",
    "AUTHENTICATION_ERROR",
    "PERMISSION_ERROR",
    "INVALID_REQUEST",
    "MODEL_UNAVAILABLE",
    "UNKNOWN_PROVIDER_ERROR",
)

ACTION_REQUIRED = {
    "AUTHENTICATION_ERROR": "CHECK_CREDENTIALS",
    "PERMISSION_ERROR": "CHECK_MODEL_PERMISSION",
    "INVALID_REQUEST": "CHECK_REQUEST_SCHEMA",
    "MODEL_UNAVAILABLE": "CHECK_MODEL_PERMISSION",
}


@dataclass(slots=True)
class TimeoutPolicy:
    connect_timeout: float = 15.0
    read_timeout: float = 60.0
    total_timeout: float = 75.0


@dataclass(slots=True)
class TransportResponse:
    status_code: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: int | None = None


@dataclass(slots=True)
class ProviderFailure(Exception):
    category: str
    retryable: bool
    http_status: int | None = None
    provider_code: str | None = None
    provider_message: str | None = None
    attempt: int = 1
    retry_reason: str | None = None
    retry_after_ms: int | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    retry_delays: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.safe_message)
        if self.category not in FAILURE_CATEGORIES:
            self.category = "UNKNOWN_PROVIDER_ERROR"

    @property
    def safe_message(self) -> str:
        return redact_message(self.provider_message or self.category)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "retryable": self.retryable,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "provider_message": redact_message(self.provider_message),
            "attempt": self.attempt,
            "retry_reason": self.retry_reason,
            "retry_after_ms": self.retry_after_ms,
            "action_required": ACTION_REQUIRED.get(self.category),
        }


@dataclass(slots=True)
class ReliableGenerationResult:
    content: str
    request_id: str | None
    elapsed_ms: int
    diagnostics: dict[str, Any]
    attempts: list[dict[str, Any]]
    retry_delays: list[float]
    final_provider_status: str = "SUCCESS"


class Transport(Protocol):
    def __call__(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: TimeoutPolicy,
    ) -> TransportResponse: ...


def redact_message(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(?:api[_ -]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", "[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "sk-[REDACTED]", text)
    return text[:500]


def _body_error(body: Any) -> tuple[str | None, str | None]:
    if not isinstance(body, dict):
        return None, None
    error = body.get("error") if isinstance(body.get("error"), dict) else body
    code = error.get("code") or error.get("type") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return (str(code) if code is not None else None, redact_message(message))


def _classify_status(status: int, code: str | None, message: str | None) -> tuple[str, bool]:
    if status == 408:
        return "REQUEST_TIMEOUT", True
    if status == 429:
        return "RATE_LIMITED", True
    if status in {401}:
        return "AUTHENTICATION_ERROR", False
    if status in {403}:
        return "PERMISSION_ERROR", False
    if status == 404:
        return "MODEL_UNAVAILABLE", False
    if status == 400:
        return "INVALID_REQUEST", False
    if status in {500, 502, 503, 504}:
        return "SERVER_5XX", True
    if 500 <= status < 600:
        return "SERVER_5XX", False
    if code and "model" in code.lower() and "unavailable" in code.lower():
        return "MODEL_UNAVAILABLE", True
    if message and "model" in message.lower() and "temporar" in message.lower():
        return "MODEL_UNAVAILABLE", True
    return "UNKNOWN_PROVIDER_ERROR", False


class ShadowReliableProvider:
    """Shadow-only OpenAI-compatible client with explicit retry semantics."""

    name = "openai_compatible_shadow_reliable"

    def __init__(
        self,
        settings: Settings,
        *,
        timeout: TimeoutPolicy | None = None,
        max_attempts: int = 3,
        backoff_seconds: tuple[float, float] = (1.0, 2.0),
        jitter_seconds: float = 0.25,
        max_retry_after_seconds: float = 10.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.settings = settings
        self.timeout = timeout or TimeoutPolicy()
        self.max_attempts = max(1, min(3, int(max_attempts)))
        self.backoff_seconds = backoff_seconds
        self.jitter_seconds = max(0.0, jitter_seconds)
        self.max_retry_after_seconds = max(0.0, max_retry_after_seconds)
        self.sleep_fn = sleep_fn
        self.rng = rng or random.Random()
        self.transport = transport or self._httpx_transport
        self.available = bool(settings.api_ready)
        self.last_error: str | None = None
        self.last_failure: ProviderFailure | None = None
        self.telemetry: list[dict[str, Any]] = []
        self.call_count = 0
        self.last_response_headers: dict[str, str] = {}

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2_048,
        telemetry_context: dict[str, Any] | None = None,
        attempt_budget: int | None = None,
    ) -> ReliableGenerationResult:
        if not self.available:
            failure = ProviderFailure(
                "AUTHENTICATION_ERROR",
                False,
                provider_message="LLM configuration is incomplete",
            )
            self.last_failure = failure
            self.last_error = failure.safe_message
            raise failure

        allowed_attempts = max(1, min(self.max_attempts, int(attempt_budget or self.max_attempts)))
        payload = {
            "model": self.settings.chat_model,
            "messages": ([{"role": "system", "content": system_prompt}] if system_prompt.strip() else [])
            + [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        started_total = time.perf_counter()
        attempts: list[dict[str, Any]] = []
        retry_delays: list[float] = []
        for attempt in range(1, allowed_attempts + 1):
            self.call_count += 1
            started = time.perf_counter()
            started_iso = datetime.now(timezone.utc).isoformat()
            failure: ProviderFailure | None = None
            response: TransportResponse | None = None
            try:
                response = self.transport(payload, headers, self.timeout)
                self.last_response_headers = dict(response.headers)
                content, request_id, diagnostics = self._parse_response(response, attempt)
                elapsed_ms = round((time.perf_counter() - started) * 1_000)
                event = self._telemetry_event(
                    telemetry_context,
                    attempt,
                    started_iso,
                    elapsed_ms,
                    response.status_code,
                    None,
                    False,
                    None,
                    0.0,
                    "SUCCESS",
                    response,
                )
                attempts.append(event)
                self.telemetry.append(event)
                self.last_failure = None
                self.last_error = None
                return ReliableGenerationResult(
                    content=content,
                    request_id=request_id,
                    elapsed_ms=round((time.perf_counter() - started_total) * 1_000),
                    diagnostics=diagnostics,
                    attempts=attempts,
                    retry_delays=retry_delays,
                )
            except ProviderFailure as error:
                failure = error
            except Exception as error:  # transport exceptions are mapped, parser bugs are isolated.
                failure = self._classify_exception(error)

            assert failure is not None
            failure.attempt = attempt
            delay = 0.0
            should_retry = failure.retryable and attempt < allowed_attempts
            if should_retry:
                delay = self._retry_delay(attempt, response.headers if response else {})
                retry_delays.append(delay)
                failure.retry_reason = failure.category
                self.sleep_fn(delay)
            event = self._telemetry_event(
                telemetry_context,
                attempt,
                started_iso,
                round((time.perf_counter() - started) * 1_000),
                failure.http_status,
                failure.provider_code,
                failure.retryable,
                failure.retry_reason,
                delay,
                failure.category,
                response,
            )
            attempts.append(event)
            self.telemetry.append(event)
            if not should_retry:
                failure.attempts = attempts
                failure.retry_delays = retry_delays
                self.last_failure = failure
                self.last_error = failure.safe_message
                raise failure
        raise AssertionError("retry loop exhausted without a provider result")

    def _parse_response(self, response: TransportResponse, attempt: int) -> tuple[str, str | None, dict[str, Any]]:
        status = int(response.status_code)
        if status < 200 or status >= 300:
            code, message = _body_error(response.body)
            category, retryable = _classify_status(status, code, message)
            raise ProviderFailure(category, retryable, status, code, message, attempt=attempt)
        body = response.body
        if not isinstance(body, dict):
            raise ProviderFailure("UNKNOWN_PROVIDER_ERROR", False, status, provider_message="response body is not an object", attempt=attempt)
        choices = body.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ProviderFailure("EMPTY_RESPONSE", True, status, provider_message="provider returned empty content", attempt=attempt)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        diagnostics = {
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "response_length": len(content),
            "http_status": status,
            "max_tokens": None,
        }
        request_id = body.get("id") if isinstance(body.get("id"), str) else None
        return content.strip(), request_id, diagnostics

    def _classify_exception(self, error: Exception) -> ProviderFailure:
        if isinstance(error, httpx.ConnectTimeout):
            return ProviderFailure("CONNECT_TIMEOUT", True, provider_message=str(error))
        if isinstance(error, httpx.ReadTimeout):
            return ProviderFailure("REQUEST_TIMEOUT", True, provider_message=str(error))
        if isinstance(error, httpx.TimeoutException):
            return ProviderFailure("REQUEST_TIMEOUT", True, provider_message=str(error))
        if isinstance(error, httpx.ConnectError):
            return ProviderFailure("CONNECTION_ERROR", True, provider_message=str(error))
        if isinstance(error, httpx.NetworkError):
            return ProviderFailure("CONNECTION_ERROR", True, provider_message=str(error))
        if isinstance(error, httpx.RequestError):
            return ProviderFailure("CONNECTION_ERROR", True, provider_message=str(error))
        return ProviderFailure("UNKNOWN_PROVIDER_ERROR", False, provider_message=str(error))

    def _retry_delay(self, attempt: int, headers: dict[str, str]) -> float:
        retry_after = next((value for key, value in headers.items() if key.lower() == "retry-after"), None)
        if retry_after is not None:
            try:
                return min(self.max_retry_after_seconds, max(0.0, float(retry_after)))
            except (TypeError, ValueError):
                pass
        base = self.backoff_seconds[min(attempt - 1, len(self.backoff_seconds) - 1)]
        return max(0.0, float(base) + self.rng.uniform(0.0, self.jitter_seconds))

    def _telemetry_event(
        self,
        context: dict[str, Any] | None,
        attempt: int,
        started_iso: str,
        elapsed_ms: int,
        http_status: int | None,
        provider_code: str | None,
        retryable: bool,
        retry_reason: str | None,
        retry_delay: float,
        final_provider_status: str,
        response: TransportResponse | None,
    ) -> dict[str, Any]:
        context = context or {}
        return {
            "request_id": context.get("request_id"),
            "pipeline_run_id": context.get("pipeline_run_id"),
            "question_id": context.get("question_id"),
            "attempt": attempt,
            "provider": self.name,
            "model": self.settings.chat_model,
            "start_time": started_iso,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "latency_ms": elapsed_ms,
            "connect_elapsed": None,
            "provider_elapsed": elapsed_ms,
            "total_elapsed": elapsed_ms,
            "http_status": http_status,
            "provider_code": provider_code,
            "retryable": retryable,
            "retry_reason": retry_reason,
            "retry_delay_ms": round(retry_delay * 1_000),
            "final_provider_status": final_provider_status,
            "response_http_elapsed_ms": response.elapsed_ms if response else None,
        }

    def _httpx_transport(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: TimeoutPolicy,
    ) -> TransportResponse:
        started = time.perf_counter()
        limits = httpx.Timeout(
            connect=timeout.connect_timeout,
            read=timeout.read_timeout,
            write=timeout.read_timeout,
            pool=timeout.connect_timeout,
        )
        with httpx.Client(timeout=limits) as client:
            response = client.post(
                f"{self.settings.api_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        elapsed_ms = round((time.perf_counter() - started) * 1_000)
        if elapsed_ms > timeout.total_timeout * 1_000:
            raise ProviderFailure("REQUEST_TIMEOUT", True, provider_message="total timeout exceeded")
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError):
            # Preserve the HTTP status so a text/plain 401/403/5xx is still
            # classified correctly; only successful responses require JSON.
            body = response.text
        return TransportResponse(response.status_code, body, dict(response.headers), elapsed_ms)
