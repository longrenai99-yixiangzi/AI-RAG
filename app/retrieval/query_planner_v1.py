from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from app.bm25 import tokenize


SPECIALTIES = ("总图", "建筑", "结构", "机电", "电气", "暖通", "给排水", "BIM", "EPC", "消防", "幕墙", "景观", "室内")
METRICS = ("工期", "金额", "创效", "效益", "利润", "数量", "比例", "排名", "上传", "条数")
ORGANIZATIONS = ("中国建筑第三工程局", "中建三局", "第二建设公司", "二公司", "公司", "局")
ENTITY_RE = re.compile(r"([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,36}(?:项目|中心|医院|馆|园|厂房|学校))")


@dataclass(slots=True)
class QueryPlan:
    query_id: str
    original_question: str
    normalized_question: str
    query_type: str
    entities: list[str] = field(default_factory=list)
    organization: list[str] = field(default_factory=list)
    project: list[str] = field(default_factory=list)
    year: list[str] = field(default_factory=list)
    specialty: list[str] = field(default_factory=list)
    metric: list[str] = field(default_factory=list)
    document_type_hint: list[str] = field(default_factory=list)
    document_role_hint: list[str] = field(default_factory=list)
    authority_requirement: str = "ANY"
    scope_constraints: dict[str, list[str]] = field(default_factory=dict)
    subquestions: list[str] = field(default_factory=list)
    structured_query_hint: bool = False
    comparison_plan: list[str] = field(default_factory=list)
    aggregation_plan: list[str] = field(default_factory=list)
    planner_confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def plan_query(question: str) -> QueryPlan:
    normalized = " ".join(question.split())
    years = list(dict.fromkeys(re.findall(r"20\d{2}", normalized)))
    entities = _entities(normalized)
    specialties = [term for term in SPECIALTIES if term in normalized]
    metrics = [term for term in METRICS if term in normalized]
    organizations = [term for term in ORGANIZATIONS if term in normalized]
    aggregation = _aggregation_plan(normalized)
    comparison = _comparison_plan(normalized)
    query_type = _query_type(normalized, aggregation, comparison)
    document_types, roles = _document_hints(normalized, query_type)
    authority = "L2_OR_L3" if any(term in normalized for term in ("责任状", "制度", "图审", "规范", "正式", "要求")) or query_type == "METHOD_QUERY" or ("任务书" in normalized and not entities) else "ANY"
    scope = {key: value for key, value in {
        "organization": organizations,
        "project": entities,
        "year": years,
        "specialty": specialties,
    }.items() if value}
    subquestions = _subquestions(normalized, aggregation, entities)
    confidence = 0.45 + 0.12 * bool(years) + 0.14 * bool(entities) + 0.1 * bool(specialties) + 0.08 * bool(metrics) + 0.06 * bool(aggregation)
    return QueryPlan(
        query_id=str(uuid.uuid5(uuid.NAMESPACE_URL, normalized)),
        original_question=question,
        normalized_question=normalized,
        query_type=query_type,
        entities=entities,
        organization=organizations,
        project=entities,
        year=years,
        specialty=specialties,
        metric=metrics,
        document_type_hint=document_types,
        document_role_hint=roles,
        authority_requirement=authority,
        scope_constraints=scope,
        subquestions=subquestions,
        structured_query_hint=bool(aggregation) or query_type in {"STRUCTURED_QUERY", "AGGREGATION_QUERY"},
        comparison_plan=comparison,
        aggregation_plan=aggregation,
        planner_confidence=round(min(0.95, confidence), 3),
    )


def _entities(question: str) -> list[str]:
    values = []
    for match in ENTITY_RE.finditer(question):
        value = re.sub(r"^20\d{2}年", "", match.group(1)).strip("（）() ")
        if value and value not in {"设计示范项目", "EPC项目", "项目"} and not ("设计示范" in value and value.endswith("项目")) and not value.startswith(("设计", "示范", "当前")):
            values.append(value)
    return list(dict.fromkeys(values))


def _aggregation_plan(question: str) -> list[str]:
    operations = []
    if any(term in question for term in ("有哪些", "包含哪些", "包括哪些", "哪些专业", "哪几个专业", "列出")):
        operations.append("LIST_DISTINCT")
    if any(term in question for term in ("每个", "各专业", "分别", "按专业", "按项目", "分组")):
        operations.append("GROUP_BY")
    if any(term in question for term in ("多少条", "多少个", "合计", "总数")) or ("数量" in question and "是多少" not in question):
        operations.append("COUNT")
    if any(term in question for term in ("其中", "利润>0", "利润大于0", "满足条件", "增加效益")):
        operations.append("FILTER")
    if any(term in question for term in ("总金额", "金额合计", "总利润", "求和")):
        operations.append("SUM")
    return list(dict.fromkeys(operations))


def _comparison_plan(question: str) -> list[str]:
    return ["COMPARE_OPTIONS"] if any(term in question for term in ("比选", "比较", "区别", "优缺点", "方案")) else []


def _query_type(question: str, aggregation: list[str], comparison: list[str]) -> str:
    if comparison and not any(item in aggregation for item in ("GROUP_BY", "COUNT", "FILTER", "SUM")):
        return "COMPARISON_QUERY" if "比较" in question or "区别" in question else "OPTION_QUERY"
    if aggregation:
        return "AGGREGATION_QUERY" if any(item in aggregation for item in ("GROUP_BY", "COUNT", "SUM", "FILTER")) else "STRUCTURED_QUERY"
    if comparison:
        return "COMPARISON_QUERY" if "比较" in question or "区别" in question else "OPTION_QUERY"
    if any(term in question for term in ("责任状", "制度", "规定", "要求", "图审", "规范")):
        return "POLICY_QUERY"
    if any(term in question for term in ("如何", "怎么", "方法", "流程", "编制", "计算方式")):
        return "METHOD_QUERY"
    if any(term in question for term in ("案例", "经验", "复盘")):
        return "CASE_QUERY"
    if len(_entities(question)) >= 2:
        return "MULTI_HOP_QUERY"
    if any(term in question for term in ("多少", "日期", "时间", "金额")):
        return "SINGLE_FACT"
    return "MULTI_FACT" if "、" in question or "和" in question else "SOURCE_LOOKUP"


def _document_hints(question: str, query_type: str) -> tuple[list[str], list[str]]:
    if "责任状" in question:
        return ["RESPONSIBILITY_CONTRACT"], ["责任文件"]
    if "任务书" in question:
        return ["DESIGN_TASK_BOOK", "TEMPLATE"], ["标准模板", "管理指南"]
    if any(term in question for term in ("图审", "审核要点")):
        return ["TABLE_LEDGER", "MANAGEMENT_GUIDE"], ["管理指南", "标准模板"]
    if query_type in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"}:
        return ["TABLE_LEDGER", "PROJECT_PLAN"], ["台账", "项目策划"]
    if query_type == "POLICY_QUERY":
        return ["POLICY", "WORK_PLAN", "MANAGEMENT_GUIDE"], ["正式制度", "管理指南", "工作计划"]
    if query_type == "CASE_QUERY":
        return ["PROJECT_CASE", "RETROSPECTIVE"], ["项目案例"]
    if query_type == "METHOD_QUERY":
        return ["MANAGEMENT_GUIDE"], ["管理指南"]
    return [], []


def _subquestions(question: str, aggregation: list[str], entities: list[str]) -> list[str]:
    values = []
    if "LIST_DISTINCT" in aggregation:
        values.append("列出目标范围内的类别或专业")
    if "GROUP_BY" in aggregation and "COUNT" in aggregation:
        values.append("按目标分组统计每组数量")
    if "FILTER" in aggregation and "COUNT" in aggregation:
        values.append("按条件筛选后统计数量")
    if "督办" in question and any(term in question for term in ("什么", "哪些", "事项")):
        values.append("列出目标单位的全部督办事项")
    return list(dict.fromkeys(values))
