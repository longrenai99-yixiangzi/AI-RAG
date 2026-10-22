from __future__ import annotations

import json
from dataclasses import dataclass

from app.answer_engine.answer_policy import AnswerPolicy
from app.answer_engine.evidence_selector import EvidenceBundle
from app.answer_engine.llm.response_schema import response_schema, response_schema_v2, schema_fields


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


def build_prompt_v2(question: str, policy: AnswerPolicy, evidence: EvidenceBundle) -> PromptPackage:
    """Offline candidate only; the existing generator and sealed requests keep V1."""
    from app.answer_engine.question_scope import question_scope
    prompt=build_prompt(question,policy,evidence);schema=response_schema_v2(policy)
    clarification={
        'candidate_prompt_version':'MINIMAL_ANSWER_V2_DRAFT',
        'fact_mapping':'claims只写由本批证据支持的事实；section_map中所有数组只放已存在的C编号，不放说明文字。',
        'scope_and_gaps':'evidence_boundary仍是事实编号数组；没有可映射的边界事实时用空数组。自然语言范围或背景备注写scope_notes；只有原问题确实要求但未覆盖的对象才写evidence_insufficient。两者不得混用。',
        'question_scope_hint':question_scope(question),
        'coverage':'范围提示是推断，不得覆盖原问题。负责人岗位人数不等于全团队人数；不要用岗位人数回答团队总数，也不要把未被问到的其他人数强行列为本题必需缺口。',
        'support':'优先引用回答当前问题的原文最小连续分句，保留适用条件、否定与例外。原文只有关键词或提到未披露，不代表有答案；不相关的原文事实不写入claims。完全未覆盖问题时claims为空、section_map各数组为空，并在evidence_insufficient写明本题缺口。'}
    marker='必须严格符合以下 Minimal Answer Schema，不得改名、加字段或返回 Markdown 代码块：\n'
    prefix,found,_=prompt.user_prompt.rpartition(marker)
    if not found:raise ValueError('V1 prompt schema boundary changed; refusing an ambiguous V2 draft')
    user=prefix+'必须严格符合以下候选V2格式，不得新增字段：\n'+json.dumps(schema,ensure_ascii=False,indent=2)+'\n候选协议说明：\n'+json.dumps(clarification,ensure_ascii=False,indent=2)
    return PromptPackage(prompt.system_prompt,user,schema)
