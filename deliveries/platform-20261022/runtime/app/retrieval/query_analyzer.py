from __future__ import annotations

from dataclasses import dataclass, field

from app.bm25 import tokenize


QUESTION_RULES = {
    "TEMPLATE_QUERY": ("模板", "任务书", "表单", "栏目"),
    "POLICY_QUERY": ("制度", "规定", "要求", "规范", "评审", "变更"),
    "CASE_QUERY": ("案例", "经验", "项目", "复盘", "总结"),
    "METHOD_QUERY": ("如何", "怎么", "方法", "步骤", "编制", "策划"),
    "DISCIPLINE_QUERY": ("建筑", "结构", "机电", "BIM", "EPC"),
}

METADATA_RULES = {
    "board": ("设计管理", "技术管理", "科技管理"),
    "knowledge_type": ("制度", "案例", "方法", "模板", "会议资料", "培训资料"),
    "discipline": ("建筑", "结构", "机电", "BIM", "EPC"),
}

DISCIPLINE_TERMS = {
    "建筑": ("建筑",),
    "结构": ("结构",),
    "机电": ("机电", "暖通", "给排水", "电气"),
    "BIM": ("BIM",),
    "EPC": ("EPC",),
}


@dataclass(slots=True)
class MetadataCandidate:
    value: str
    confidence: float
    source: str = "question"


@dataclass(slots=True)
class QueryAnalysis:
    question: str
    question_type: str
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, MetadataCandidate] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return " ".join([self.question, *self.keywords])


def analyze_query(question: str) -> QueryAnalysis:
    normalized = question.strip()
    question_type = _question_type(normalized)
    keywords = list(dict.fromkeys(tokenize(normalized)))
    metadata: dict[str, MetadataCandidate] = {}
    for field_name, values in METADATA_RULES.items():
        terms = DISCIPLINE_TERMS if field_name == "discipline" else {
            value: (value,) for value in values
        }
        for value, aliases in terms.items():
            if any(alias in normalized for alias in aliases):
                metadata[field_name] = MetadataCandidate(value=value, confidence=0.95)
                break
    return QueryAnalysis(
        question=normalized,
        question_type=question_type,
        keywords=keywords,
        metadata={field_name: candidate for field_name, candidate in metadata.items()},
    )


def _question_type(question: str) -> str:
    if any(keyword in question for keyword in ("模板", "表单", "栏目")):
        return "TEMPLATE_QUERY"
    if any(keyword in question for keyword in ("制度", "规定", "规范", "要求")):
        return "POLICY_QUERY"
    if any(keyword in question for keyword in ("案例", "经验", "复盘")):
        return "CASE_QUERY"
    discipline_hits = sum(
        any(alias in question for alias in aliases)
        for aliases in DISCIPLINE_TERMS.values()
    )
    if discipline_hits >= 2 or (discipline_hits and "专业" in question):
        return "DISCIPLINE_QUERY"
    if "任务书" in question and not any(
        keyword in question for keyword in ("如何", "怎么", "编制", "步骤")
    ):
        return "TEMPLATE_QUERY"
    if any(keyword in question for keyword in QUESTION_RULES["METHOD_QUERY"]):
        return "METHOD_QUERY"
    if discipline_hits:
        return "DISCIPLINE_QUERY"
    return "GENERAL_QUERY"
