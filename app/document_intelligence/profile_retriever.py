from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.answer_engine.answer_policy import AnswerPolicy
from app.bm25 import tokenize


@dataclass(slots=True)
class ProfileCandidate:
    document_id: str
    document_name: str
    score: float
    rank: int
    profile: dict[str, Any]


class DocumentProfileRetriever:
    """Deterministic Shadow document-level retriever."""

    def __init__(self, profiles: Iterable[dict[str, Any]]) -> None:
        self.profiles = list(profiles)

    @classmethod
    def from_jsonl(cls, path: Path) -> "DocumentProfileRetriever":
        profiles = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(profiles)

    def search(
        self,
        question: str,
        policy: AnswerPolicy,
        *,
        limit: int = 30,
    ) -> list[ProfileCandidate]:
        ranked = [
            (
                self._score_profile(question, policy, profile),
                str(profile.get("document_id") or ""),
                profile,
            )
            for profile in self.profiles
        ]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            ProfileCandidate(
                document_id=str(profile.get("document_id") or ""),
                document_name=str(profile.get("document_name") or ""),
                score=float(score),
                rank=index,
                profile=profile,
            )
            for index, (score, _, profile) in enumerate(ranked[:limit], start=1)
        ]

    @staticmethod
    def _score_profile(
        question: str,
        policy: AnswerPolicy,
        profile: dict[str, Any],
    ) -> float:
        profile_text = " ".join(
            [
                str(profile.get("document_name") or ""),
                str(profile.get("document_role") or ""),
                str(profile.get("authority_level") or ""),
                str(profile.get("usage_scene") or ""),
                " ".join(str(item) for item in profile.get("contains_topics", [])),
                " ".join(
                    str(item)
                    for values in (profile.get("scope") or {}).values()
                    for item in values
                ),
            ]
        )
        query_terms = set(tokenize(question))
        profile_terms = set(tokenize(profile_text))
        lexical = len(query_terms & profile_terms) / max(1, len(query_terms))
        topic_hits = sum(
            1 for topic in profile.get("contains_topics", []) if str(topic) in question
        )
        scope_hits = sum(
            1
            for values in (profile.get("scope") or {}).values()
            for value in values
            if str(value) in question
        )
        role_score = (
            1.0
            if profile.get("document_role") in policy.preferred_roles
            else 0.0
        )
        authority_score = {
            "L1": 1.0,
            "L2": 0.9,
            "L3": 0.75,
            "L4": 0.55,
            "L5": 0.30,
            "L6": 0.15,
            "UNKNOWN": 0.0,
        }.get(str(profile.get("authority_level") or "UNKNOWN"), 0.0)
        not_for_penalty = 0.0
        for limitation in profile.get("not_for", []):
            if any(term in question for term in str(limitation).split("：")[-1].split()):
                not_for_penalty += 0.05
        return max(
            0.0,
            0.45 * lexical
            + 0.20 * min(1.0, topic_hits / 2)
            + 0.15 * min(1.0, scope_hits / 2)
            + 0.12 * role_score
            + 0.08 * authority_score
            - not_for_penalty,
        )
