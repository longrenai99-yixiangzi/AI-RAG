from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings
from app.llm import LLMClient, LLMError


@dataclass(slots=True)
class GenerationResult:
    content: str
    request_id: str | None
    elapsed_ms: int
    diagnostics: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    available: bool
    last_error: str | None
    last_diagnostics: dict[str, Any]

    def probe(self) -> bool: ...

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2_048,
    ) -> GenerationResult: ...


class OpenAICompatibleProvider:
    """Shadow adapter around the existing OpenAI-compatible LLM client."""

    name = "openai_compatible_shadow"

    def __init__(self, settings: Settings) -> None:
        self.client = LLMClient(settings)
        self.available = bool(settings.api_ready)
        self.last_error: str | None = None
        self.last_diagnostics: dict[str, Any] = {}

    def probe(self) -> bool:
        if not self.available:
            self.last_error = "LLM configuration is incomplete"
            return False
        try:
            self.client.complete(
                "Return only OK.",
                "Reply with OK.",
                temperature=0,
                max_tokens=512,
            )
        except LLMError as error:
            self.last_diagnostics = dict(self.client.last_diagnostics)
            self.last_error = f"{type(error).__name__}: {error}"
            return False
        self.last_diagnostics = dict(self.client.last_diagnostics)
        return True

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2_048,
    ) -> GenerationResult:
        if not self.available:
            raise LLMError(self.last_error or "LLM provider unavailable")
        try:
            response = self.client.complete(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMError as error:
            self.last_diagnostics = dict(self.client.last_diagnostics)
            self.last_error = f"{type(error).__name__}: {error}"
            raise
        self.last_diagnostics = dict(self.client.last_diagnostics)
        return GenerationResult(
            content=response.content,
            request_id=response.request_id,
            elapsed_ms=response.elapsed_ms,
            diagnostics=self.last_diagnostics,
        )


class UnavailableLLMProvider:
    name = "unavailable"
    available = False

    def __init__(self, reason: str) -> None:
        self.last_error = reason
        self.last_diagnostics: dict[str, Any] = {}

    def probe(self) -> bool:
        return False

    def generate(self, *args: object, **kwargs: object) -> GenerationResult:
        raise LLMError(self.last_error)
