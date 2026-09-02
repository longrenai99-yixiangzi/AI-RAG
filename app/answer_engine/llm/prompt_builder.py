from __future__ import annotations

import json
from dataclasses import dataclass

from app.answer_engine.answer_policy import AnswerPolicy
from app.answer_engine.evidence_selector import EvidenceBundle
from app.answer_engine.llm.response_schema import response_schema, schema_fields


@dataclass(slots=True)
class PromptPackage:
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, object]


def build_prompt(
    question: str,
    policy: AnswerPolicy,
    evidence: EvidenceBundle,
) -> PromptPackage:
    evidence_payload = [
        {
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "file_name": item.file_name,
            "document_role": item.document_role,
            "authority_level": item.authority_level,
            "usage_scene": item.usage_scene,
            "location": item.location,
            "evidence_status": item.evidence_status,
            "excerpt": item.excerpt,
        }
        for item in evidence.items
    ]
    schema = response_schema(policy)
    system_prompt = (
        "你是企业设计管理知识库助手，只能依据提供的 Evidence 回答。"
        "只返回 Minimal Answer Schema JSON，不返回 Markdown，不返回完整 Section 文本，不返回 Citation。"
        "不得补造条款、数字、版本或事实；证据不足时使用 evidence_insufficient。"
    )
    user_prompt = "\n".join(
        [
            f"问题：{question}",
            f"回答类型：{policy.intent}",
            f"section_map 字段：{', '.join(schema_fields(policy))}",
            "Evidence：",
            json.dumps(evidence_payload, ensure_ascii=False, indent=2),
            "必须严格符合以下 Minimal Answer Schema，不得改名、加字段或返回 Markdown 代码块：",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "claims 只保存最小事实单元；section_map 只保存 Claim ID 映射；evidence_ids 只能使用当前 Evidence 的 S1、S2……。",
            "后端会根据 claim_text、section_map 和 evidence_ids 确定性生成最终回答。",
        ]
    )
    return PromptPackage(system_prompt, user_prompt, schema)
