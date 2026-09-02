from __future__ import annotations

from dataclasses import dataclass

from .answer_policy import AnswerPolicy
from .citation_map import CitationMap
from .evidence_selector import EvidenceBundle


@dataclass(slots=True)
class ShadowAnswerResponse:
    question: str
    intent: str
    policy_name: str
    status: str
    answer_text: str
    evidence_bundle: EvidenceBundle
    citation_map: CitationMap


def build_shadow_response(
    question: str,
    policy: AnswerPolicy,
    evidence_bundle: EvidenceBundle,
    citation_map: CitationMap,
) -> ShadowAnswerResponse:
    if not evidence_bundle.items:
        answer_text = "当前知识库未检索到足够依据，暂不生成确定性结论。"
        status = "NO_EVIDENCE"
    else:
        lines = ["当前为 Shadow evidence-only 结果，未调用 LLM。"]
        for section in policy.sections:
            lines.append(f"## {section}")
            section_items = evidence_bundle.items[:2]
            if not section_items:
                lines.append("- 当前证据未覆盖该部分。")
                continue
            for item in section_items:
                lines.append(f"- [{item.source_id}] {item.excerpt[:240]}")
        answer_text = "\n".join(lines)
        status = "EVIDENCE_ONLY" if citation_map.valid else "CITATION_INVALID"
    return ShadowAnswerResponse(
        question=question,
        intent=policy.intent,
        policy_name=policy.name,
        status=status,
        answer_text=answer_text,
        evidence_bundle=evidence_bundle,
        citation_map=citation_map,
    )
