from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .metadata import load_metadata_rules


@dataclass(slots=True)
class QueryAnalysis:
    question: str
    intent: str
    filters: dict[str, Any]
    matched_terms: list[str]
    normalized_query: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _match_intent(question: str, rules: dict[str, Any]) -> str:
    folded = question.casefold()
    scores: list[tuple[int, str]] = []
    for intent, keywords in (rules.get("intent_keywords") or {}).items():
        count = sum(1 for keyword in keywords or [] if str(keyword).casefold() in folded)
        if count:
            scores.append((count, str(intent)))
    return max(scores, default=(0, "GENERAL_RAG"))[1]


def analyze_question(question: str, rules_path: str | Path | None = None) -> QueryAnalysis:
    rules = load_metadata_rules(rules_path or Path(__file__).resolve().parents[1] / "config" / "metadata_rules.yaml")
    filters: dict[str, Any] = {}
    matched_terms: list[str] = []
    folded = question.casefold()
    for field, field_rules in (rules.get("fields") or {}).items():
        matches: list[tuple[int, str]] = []
        for value, config in (field_rules.get("values") or {}).items():
            keywords = config.get("keywords", []) if isinstance(config, dict) else config
            matched = [str(keyword) for keyword in keywords or [] if str(keyword).casefold() in folded]
            if matched:
                matches.append((max(map(len, matched)), str(value)))
                matched_terms.extend(matched)
        if matches:
            matches.sort(key=lambda item: (-item[0], item[1]))
            values = [value for _, value in matches]
            filters[field] = sorted(set(values)) if field_rules.get("multi") else values[0]

    for project in rules.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        aliases = [str(x) for x in project.get("keywords", [])]
        if any(alias.casefold() in folded for alias in aliases):
            filters["project_name"] = str(project.get("value", ""))
            matched_terms.extend(alias for alias in aliases if alias.casefold() in folded)
            break

    return QueryAnalysis(
        question=question,
        intent=_match_intent(question, rules),
        filters=filters,
        matched_terms=sorted(set(matched_terms)),
        normalized_query=" ".join(question.split()),
    )
