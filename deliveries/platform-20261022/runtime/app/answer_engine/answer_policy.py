from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnswerPolicy:
    intent: str
    name: str
    sections: tuple[str, ...]
    preferred_roles: tuple[str, ...]
    preferred_knowledge_types: tuple[str, ...]
    evidence_mode: str


POLICIES = {
    "POLICY_QUERY": AnswerPolicy(
        intent="POLICY_QUERY",
        name="制度要求回答",
        sections=("结论", "管理要求", "依据"),
        preferred_roles=("正式制度", "管理指南", "标准模板"),
        preferred_knowledge_types=("制度", "方法", "模板"),
        evidence_mode="direct_first",
    ),
    "CASE_QUERY": AnswerPolicy(
        intent="CASE_QUERY",
        name="项目案例回答",
        sections=("背景", "措施", "效果", "经验"),
        preferred_roles=("项目案例", "管理指南"),
        preferred_knowledge_types=("案例", "方法"),
        evidence_mode="case_facts",
    ),
    "METHOD_QUERY": AnswerPolicy(
        intent="METHOD_QUERY",
        name="方法步骤回答",
        sections=("流程", "步骤", "注意事项"),
        preferred_roles=("管理指南", "标准模板", "正式制度"),
        preferred_knowledge_types=("方法", "模板", "制度"),
        evidence_mode="ordered_steps",
    ),
    "TEMPLATE_QUERY": AnswerPolicy(
        intent="TEMPLATE_QUERY",
        name="模板使用回答",
        sections=("模板用途", "字段说明", "使用方法"),
        preferred_roles=("标准模板", "管理指南"),
        preferred_knowledge_types=("模板", "方法"),
        evidence_mode="structure_first",
    ),
    "DISCIPLINE_QUERY": AnswerPolicy(
        intent="DISCIPLINE_QUERY",
        name="专业问题回答",
        sections=("专业结论", "适用条件", "检查点", "依据与边界"),
        preferred_roles=("管理指南", "项目案例", "标准模板"),
        preferred_knowledge_types=("方法", "案例", "制度", "模板"),
        evidence_mode="discipline_context",
    ),
    "GENERAL_QUERY": AnswerPolicy(
        intent="GENERAL_QUERY",
        name="通用证据摘要",
        sections=("已检索信息", "证据边界", "待补充项"),
        preferred_roles=("正式制度", "管理指南", "项目案例", "标准模板"),
        preferred_knowledge_types=("制度", "方法", "案例", "模板"),
        evidence_mode="evidence_only",
    ),
}


def policy_for_intent(intent: str) -> AnswerPolicy:
    return POLICIES.get(intent, POLICIES["GENERAL_QUERY"])
