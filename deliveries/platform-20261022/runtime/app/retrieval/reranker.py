from __future__ import annotations

from typing import Protocol, Sequence


class RerankerProvider(Protocol):
    def score(self, question: str, passages: Sequence[str]) -> list[float] | None: ...


class DisabledReranker:
    """Shadow-stage provider; always leaves the RRF order unchanged."""

    def score(self, question: str, passages: Sequence[str]) -> list[float] | None:
        return None
