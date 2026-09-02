from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMResponse:
    content: str
    request_id: str | None
    elapsed_ms: int
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    response_length: int | None = None


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_error: str | None = None
        self.last_diagnostics: dict[str, Any] = {}

    def complete(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 2_048
    ) -> LLMResponse:
        if not self.settings.api_ready:
            raise LLMError("RAG API 配置不完整")
        messages = [{"role": "user", "content": user_prompt}]
        if system_prompt.strip():
            messages.insert(0, {"role": "system", "content": system_prompt})
        payload = {
            "model": self.settings.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        started = time.perf_counter()
        for attempt in range(3):
            self.last_diagnostics = {
                "finish_reason": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "max_tokens": max_tokens,
                "response_length": None,
                "elapsed_ms": None,
                "http_status": None,
            }
            try:
                with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                    response = client.post(
                        f"{self.settings.api_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    self.last_diagnostics["http_status"] = response.status_code
                    response.raise_for_status()
                body = response.json()
                choices = body.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise ValueError("response choices is missing")
                choice = choices[0]
                if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                    raise ValueError("response message is missing")
                usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
                content = choice["message"].get("content")
                self.last_diagnostics.update(
                    {
                        "finish_reason": choice.get("finish_reason"),
                        "prompt_tokens": _int_or_none(usage.get("prompt_tokens")),
                        "completion_tokens": _int_or_none(usage.get("completion_tokens")),
                        "total_tokens": _int_or_none(usage.get("total_tokens")),
                        "response_length": len(content) if isinstance(content, str) else 0,
                        "elapsed_ms": round((time.perf_counter() - started) * 1_000),
                    }
                )
                if not isinstance(content, str) or not content.strip():
                    if choice.get("finish_reason") == "length":
                        raise ValueError("provider stopped before returning the final answer")
                    raise ValueError("response content is missing")
                self.last_error = None
                return LLMResponse(
                    content=content.strip(),
                    request_id=response.headers.get("x-request-id") or body.get("id"),
                    elapsed_ms=round((time.perf_counter() - started) * 1_000),
                    finish_reason=choice.get("finish_reason"),
                    prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
                    completion_tokens=_int_or_none(usage.get("completion_tokens")),
                    total_tokens=_int_or_none(usage.get("total_tokens")),
                    response_length=len(content),
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
                last_error = error
                if isinstance(error, httpx.HTTPStatusError):
                    self.last_diagnostics["http_status"] = error.response.status_code
                self.last_diagnostics["elapsed_ms"] = round((time.perf_counter() - started) * 1_000)
                if attempt < 2:
                    time.sleep(attempt + 1)
        self.last_error = type(last_error).__name__ if last_error else "UnknownError"
        raise LLMError("生成模型请求失败；请检查网络连接、模型权限和服务状态") from last_error

    def health_check(self) -> bool:
        try:
            response = self.complete("", "只回复：OK", temperature=0, max_tokens=512)
            return response.content.upper().startswith("OK")
        except LLMError:
            return False


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
