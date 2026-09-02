from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.answer_response import ShadowAnswerResponse
from app.evaluation.gold_dataset_loader import GoldQuestion
from app.retrieval.shadow_precision import analyze_precision_intent


@dataclass(slots=True)
class EvidenceQuestionResult:
    question_id: str
    intent: str
    expected_role: str
    top_role: str
    role_top1_match: bool
    role_any_match: bool
    authority_top1_match: bool
    authority_any_match: bool
    usage_scene_top1_match: bool
    usage_scene_any_match: bool
    expected_file_hit: bool
    intent_top1_match: bool
    intent_any_match: bool
    confusion: bool
    mixed_role_bundle: bool
    selected_roles: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceQualityReport:
    questions: list[EvidenceQuestionResult]

    def summary(self) -> dict[str, Any]:
        return {
            "questions": len(self.questions),
            "role_top1_match_rate": _rate(self.questions, "role_top1_match"),
            "role_any_match_rate": _rate(self.questions, "role_any_match"),
            "authority_top1_match_rate": _rate(self.questions, "authority_top1_match"),
            "authority_any_match_rate": _rate(self.questions, "authority_any_match"),
            "usage_scene_top1_match_rate": _rate(self.questions, "usage_scene_top1_match"),
            "usage_scene_any_match_rate": _rate(self.questions, "usage_scene_any_match"),
            "expected_file_hit_rate": _rate(self.questions, "expected_file_hit"),
            "intent_top1_match_rate": _rate(self.questions, "intent_top1_match"),
            "intent_any_match_rate": _rate(self.questions, "intent_any_match"),
            "confusion_rate": _rate(self.questions, "confusion"),
            "mixed_role_bundle_rate": _rate(self.questions, "mixed_role_bundle"),
            "by_intent": _by_intent(self.questions),
        }


def evaluate_evidence_quality(
    questions: Sequence[GoldQuestion],
    responses: Sequence[ShadowAnswerResponse],
) -> EvidenceQualityReport:
    if len(questions) != len(responses):
        raise ValueError("questions and responses must have the same length")
    results: list[EvidenceQuestionResult] = []
    for question, response in zip(questions, responses, strict=True):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        items = response.evidence_bundle.items
        roles = [item.document_role for item in items]
        top = items[0] if items else None
        expected_role = question.expected_document_role
        expected_authority = question.expected_authority_level
        expected_scene = question.expected_usage_scene
        preferred = set(policy.preferred_roles)
        expected_file_hit = any(
            expected.casefold() == item.file_name.casefold()
            for expected in question.expected_files
            for item in items
        )
        role_top1_match = bool(top and expected_role and top.document_role == expected_role)
        role_any_match = bool(expected_role and expected_role in roles)
        authority_top1_match = bool(
            top and expected_authority and top.authority_level == expected_authority
        )
        authority_any_match = bool(
            expected_authority
            and any(item.authority_level == expected_authority for item in items)
        )
        usage_top1_match = bool(top and expected_scene and top.usage_scene == expected_scene)
        usage_any_match = bool(
            expected_scene and any(item.usage_scene == expected_scene for item in items)
        )
        intent_top1_match = bool(top and top.document_role in preferred)
        intent_any_match = any(role in preferred for role in roles)
        if intent.question_type == "POLICY_QUERY":
            distractors = {"项目案例", "培训材料", "汇报材料"}
        elif intent.question_type == "CASE_QUERY":
            distractors = {"正式制度", "培训材料", "汇报材料"}
        elif intent.question_type == "TEMPLATE_QUERY":
            distractors = {"项目案例", "培训材料", "汇报材料"}
        else:
            distractors = set()
        confusion = bool(top and top.document_role in distractors)
        mixed_role_bundle = len(set(roles)) > 1 and bool(set(roles) & distractors)
        results.append(
            EvidenceQuestionResult(
                question_id=question.id,
                intent=intent.question_type,
                expected_role=expected_role,
                top_role=top.document_role if top else "",
                role_top1_match=role_top1_match,
                role_any_match=role_any_match,
                authority_top1_match=authority_top1_match,
                authority_any_match=authority_any_match,
                usage_scene_top1_match=usage_top1_match,
                usage_scene_any_match=usage_any_match,
                expected_file_hit=expected_file_hit,
                intent_top1_match=intent_top1_match,
                intent_any_match=intent_any_match,
                confusion=confusion,
                mixed_role_bundle=mixed_role_bundle,
                selected_roles=roles,
            )
        )
    return EvidenceQualityReport(results)


def _rate(items: Sequence[EvidenceQuestionResult], field: str) -> float:
    if not items:
        return 0.0
    return sum(bool(getattr(item, field)) for item in items) / len(items)


def _by_intent(items: Sequence[EvidenceQuestionResult]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[EvidenceQuestionResult]] = {}
    for item in items:
        grouped.setdefault(item.intent, []).append(item)
    return {
        intent: {
            "questions": len(group),
            "role_top1_match_rate": _rate(group, "role_top1_match"),
            "role_any_match_rate": _rate(group, "role_any_match"),
            "authority_top1_match_rate": _rate(group, "authority_top1_match"),
            "expected_file_hit_rate": _rate(group, "expected_file_hit"),
            "intent_top1_match_rate": _rate(group, "intent_top1_match"),
            "confusion_rate": _rate(group, "confusion"),
            "mixed_role_bundle_rate": _rate(group, "mixed_role_bundle"),
        }
        for intent, group in sorted(grouped.items())
    }
