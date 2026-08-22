from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import Settings


class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMResponse:
    content: str
    request_id: str | None
    elapsed_ms: int


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_error: str | None = None

    def complete(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 2_048
    ) -> LLMResponse:
        if not self.settings.api_ready:
            raise LLMError("未发现完整的 RAG API 配置。请检查 Windows 用户环境变量。")
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
            try:
                with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                    response = client.post(
                        f"{self.settings.api_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                body = response.json()
                choices = body.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise ValueError("响应中没有 choices")
                choice = choices[0]
                if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                    raise ValueError("响应中没有标准 message")
                content = choice["message"].get("content")
                if not isinstance(content, str) or not content.strip():
                    # This endpoint exposes DeepSeek reasoning separately. A small output
                    # budget can finish during reasoning before the final answer is emitted.
                    if choice.get("finish_reason") == "length":
                        raise ValueError("模型在生成最终回答前达到输出上限")
                    raise ValueError("响应中没有可用文本")
                self.last_error = None
                return LLMResponse(
                    content=content.strip(),
                    request_id=response.headers.get("x-request-id") or body.get("id"),
                    elapsed_ms=round((time.perf_counter() - started) * 1_000),
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(attempt + 1)
        self.last_error = type(last_error).__name__ if last_error else "UnknownError"
        raise LLMError("生成模型请求失败；请检查内网连接、模型权限和服务状态。") from last_error

    def health_check(self) -> bool:
        try:
            response = self.complete(
                "",
                "只回复：OK",
                temperature=0,
                max_tokens=512,
            )
            return response.content.upper().startswith("OK")
        except LLMError:
            return False
