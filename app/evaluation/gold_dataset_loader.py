from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class GoldQuestion:
    id: str
    question: str
    expected_files: list[str]
    expected_topics: list[str]
    difficulty: str
    topic: str
    expected_document_role: str = ""
    expected_authority_level: str = ""
    expected_usage_scene: str = ""


def load_gold_questions(path: Path, minimum: int = 100) -> list[GoldQuestion]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_questions = payload.get("questions", [])
    if len(raw_questions) < minimum:
        raise ValueError(f"Gold Question 数量不足：{len(raw_questions)} < {minimum}")
    questions = [
        GoldQuestion(
            id=str(item["id"]),
            question=str(item["question"]),
            expected_files=[str(value) for value in item.get("expected_files", [])],
            expected_topics=[str(value) for value in item.get("expected_topics", [])],
            difficulty=str(item.get("difficulty", "medium")),
            topic=str(item.get("topic", "未分类")),
            expected_document_role=str(item.get("expected_document_role", "")),
            expected_authority_level=str(item.get("expected_authority_level", "")),
            expected_usage_scene=str(item.get("expected_usage_scene", "")),
        )
        for item in raw_questions
    ]
    _validate_unique_ids(questions)
    return questions


def _validate_unique_ids(questions: list[GoldQuestion]) -> None:
    ids = [question.id for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Gold Question ID 重复")
