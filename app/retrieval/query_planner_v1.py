from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from app.bm25 import tokenize
from app.document_overview_v1 import overview_title


SPECIALTIES = ("总图", "建筑", "结构", "机电", "电气", "暖通", "给排水", "BIM", "EPC", "消防", "幕墙", "景观", "室内")
METRICS = ("工期", "面积", "合同额", "风险", "金额", "创效", "效益", "利润", "量差率", "数量", "比例", "排名", "上传", "条数")
ORGANIZATION_ALIASES = {
    "中建三局第二建设公司": ("中建三局第二建设公司", "中建三局二公司", "第二建设公司", "二公司"),
    "中建三局": ("中国建筑第三工程局", "中建三局"),
}
PROJECT_RE = re.compile(r"([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,48}项目)")
VALUE_CREATION_LEDGER_SCOPE_RE = re.compile(r"设计价值创造统计台账[（(]\s*([^（）()]{2,48}?)\s*[）)]")
ENTITY_RE = re.compile(r"([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,48}(?:项目|中心|医院|馆|园|厂房|学校))")
GENERIC_PROJECT_MARKERS = ("多少", "几个", "哪些", "所有", "各个", "累计", "共计", "成功打造", "打造为", "完成了", "项目数", "最大", "最多", "最高", "最小", "最少", "台账中")

# A project constraint is hard: _direct_candidate requires scope.project == "MATCH", and
# an unsatisfiable constraint silently drops every candidate (verified_evidence == 0).
# So a *wrong* value here is worse than no value at all, and these patterns all produced
# a bogus project name out of a descriptive phrase in the question.
PROJECT_PHRASE_MARKERS = ("的", "作为", "管项目", "层面", "及以上", "分别", "如何", "怎么", "服务", "有条件采取")
GENERIC_PROJECT_STEMS = {
    "数据", "数据中心", "级数据", "海外", "项目", "项目及",
    "中建三局", "中建三局第二建设公司", "公司层面重点管控",
    "直属分公司EPC", "厂房", "工业厂房", "电子厂房", "标准厂房", "创新", "科技创新", "科研", "医院", "EPC",
}


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
    period: str = ""
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
    overview = overview_title(normalized)
    years = list(dict.fromkeys(re.findall(r"20\d{2}", normalized)))
    period = _period_scope(normalized)
    projects = _projects(normalized)
    entities = _entities(normalized)
    specialties = [term for term in SPECIALTIES if term in normalized]
    metrics = [term for term in METRICS if term in normalized]
    organizations = _organizations(normalized)
    aggregation = _aggregation_plan(normalized)
    comparison = _comparison_plan(normalized)
    query_type = _query_type(normalized, aggregation, comparison)
    document_types, roles = _document_hints(normalized, query_type)
    authority = "L2_OR_L3" if any(term in normalized for term in ("责任状", "制度", "图审", "规范", "正式", "要求")) or query_type == "METHOD_QUERY" or ("任务书" in normalized and not projects) else "ANY"
    scope = {key: value for key, value in {
        "organization": organizations,
        "project": projects,
        "year": years,
        "period": [period] if period else [],
        "specialty": specialties,
    }.items() if value}
    transfer = _project_fact_transfer(normalized)
    reference = re.match(r'^(?:请问|请|根据|依据)?[《“"]?(.{2,45}?(?:课件|手册|细则|报告|资料))[》”"]?(?:里|中|的|规定)', normalized)
    if not reference:
        reference = re.match(r'^(?:按(?:照)?|依据|根据)[《“"]?(.{2,80}?(?:指南|办法|标准|规定))[》”"]?[，,：:]', normalized)
    if reference and projects:
        label = reference[1]
        for project in projects:
            label = label.replace(project, '')
        if label in {'原报告', '报告', '评估报告'}:
            reference = None
    if reference:
        scope['source_reference'] = [re.sub(r'20\d{2}年(?:\d{1,2}月)?(?:版)?', '', reference[1])]
    if overview:
        years, projects, entities, specialties, metrics, organizations = [], [], [], [], [], []
        aggregation, comparison, document_types, roles = [], [], [], []
        period, authority = '', 'ANY'
        scope = {'source_reference':[overview]}
    if transfer:
        scope["project_fact_transfer"] = transfer
    if not projects and re.search(r'我的(?:项目|工程|办公楼|建筑)|本项目|本工程|该项目', normalized) and re.search(r'是多少|有多少|金额|面积', normalized):
        scope['unidentified_subject'] = ['需要明确项目或资料，不能采用其他项目数值']
    kind = annual_plan_kind(normalized)
    if kind:
        scope['annual_plan_kind'] = [kind]
    constraints = _response_constraints(normalized)
    if constraints:
        scope["response_constraints"] = constraints
    subquestions = _subquestions(normalized, aggregation, projects)
    confidence = 0.45 + 0.12 * bool(years) + 0.14 * bool(projects) + 0.1 * bool(specialties) + 0.08 * bool(metrics) + 0.06 * bool(aggregation)
    return QueryPlan(
        query_id=str(uuid.uuid5(uuid.NAMESPACE_URL, normalized)),
        original_question=question,
        normalized_question=normalized,
        query_type=query_type,
        entities=entities,
        organization=organizations,
        project=projects,
        year=years,
        period=period,
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


def _period_scope(question: str) -> str:
    month = re.search(r'(20\d{2})年(\d{1,2})月.{0,35}(?:推进会|会议|督办|监督任务|工作任务|任务表|待办|工作总结|检查记录|工作情况|工作计划|台账)', question)
    if month and 1 <= int(month[2]) <= 12:
        return f'MONTH:{month[1]}-{int(month[2]):02d}'
    if not re.search(r'20\d{2}', question) and annual_plan_kind(question) and any(term in question for term in ('如何', '怎么', '怎样')):
        return ''
    if any(marker in question for marker in ("\u4e0a\u534a\u5e74", "\u534a\u5e74")):
        return "H1"
    if any(marker in question for marker in ("\u5168\u5e74", "\u5e74\u5ea6", "\u5e74\u7ec8", "\u5168\u5e74\u5ea6")):
        return "FULL_YEAR"
    return ""


def _projects(question: str) -> list[str]:
    values = [
        _strip_date_prefix(match.group(1).strip())
        for match in VALUE_CREATION_LEDGER_SCOPE_RE.finditer(question)
        if _is_named_project(match.group(1).strip())
    ]
    for match in PROJECT_RE.finditer(question):
        value = _strip_date_prefix(re.sub(r'^.+?(?:工作计划|进度计划|年度计划)(?:和|与|以及|及|、)', '', match.group(1)))
        if _is_named_project(value):
            values.append(value)
    return list(dict.fromkeys(values))


def _strip_date_prefix(value: str) -> str:
    """Normalise "2025年老谷南项目" / "2025 年老谷南项目" / "年老谷南项目" -> "老谷南项目"."""
    value = re.sub(r'^(?:不存在的|尚未收录的|未收录的)', '', value)
    value = re.sub(r"^20\d{2}\s*年", "", value)
    value = re.sub(r"^年", "", value)
    value = re.sub(r"^\d{1,2}月(?:\d{1,2}日)?", "", value)
    return value.strip("（）() ")


def _entities(question: str) -> list[str]:
    values = []
    for match in ENTITY_RE.finditer(question):
        value = _strip_date_prefix(match.group(1))
        if value and not _is_generic_project_phrase(value) and value not in {"设计示范项目", "EPC项目", "项目"} and not value.startswith(("设计", "示范", "当前")):
            values.append(value)
    return list(dict.fromkeys(values))


def _is_named_project(value: str) -> bool:
    if re.fullmatch(r"(?:不填(?:写)?|不要填写|无需填写)(?:本|当前)?项目", value):
        return False
    if not value or value in {"设计示范项目", "EPC项目", "项目"}:
        return False
    if _is_generic_project_phrase(value):
        return False
    if value.startswith(("设计", "示范", "当前")):
        return False
    # Descriptive phrases are not project names. Extracting one of these poisons the
    # whole verification stage: the constraint can never be satisfied, so every
    # candidate is dropped and the answer degrades to an unrelated excerpt dump.
    if any(marker in value for marker in PROJECT_PHRASE_MARKERS):
        return False
    # Leftover from stripping a year, e.g. "2025 年老谷南项目" -> "年老谷南项目".
    if value.startswith("年"):
        return False
    stem = value
    for suffix in ("项目", "工程"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = stem.strip("（）() ")
    if len(stem) < 2:
        return False
    if stem in GENERIC_PROJECT_STEMS:
        return False
    # Fragment split off a preceding qualifier, e.g. "内蒙古电力 A 级数据中心项目"
    # where the space broke the match and left "级数据中心项目".
    if stem.startswith("级"):
        return False
    return True


def _is_generic_project_phrase(value: str) -> bool:
    stem = value
    for suffix in ("项目", "工程"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if re.fullmatch(r'(?:新开|新承接|在建|竣工)(?:(?:和|与|及)(?:新开|新承接|在建|竣工))*', stem):
        return True
    return (
        bool(re.match(r"^度(?:设计|多少|有|成功|最终)", value))
        or any(marker in value for marker in GENERIC_PROJECT_MARKERS)
        or stem.strip("（）() ") in GENERIC_PROJECT_STEMS
    )


def _organizations(question: str) -> list[str]:
    values = []
    for canonical, aliases in ORGANIZATION_ALIASES.items():
        if any(alias in question for alias in aliases):
            values.append(canonical)
    return values


def _aggregation_plan(question: str) -> list[str]:
    if design_deliverable_stages(question):
        return []
    operations = []
    if any(term in question for term in ("有哪些", "包含哪些", "包括哪些", "哪些专业", "哪几个专业", "列出")):
        operations.append("LIST_DISTINCT")
    if any(term in question for term in ("每个", "各专业", "按专业", "按项目", "分组")):
        operations.append("GROUP_BY")
    sum_request = any(term in question for term in (
        "总金额", "金额合计", "合计金额", "总利润", "利润合计", "合计利润",
        "总创效", "创效合计", "合计创效", "总合同额", "合同额合计", "合计合同额",
        "总收益", "收益合计", "总效益", "效益合计", "求和",
    )) or ("合计" in question and any(term in question for term in ("金额", "利润", "创效", "合同额", "收益", "效益", "收入", "费用", "成本", "产值", "造价", "投资额", "万元", "亿元")))
    if re.search(r"(?:多少|几)(?:个|条|项|家|份|次|人|座)", question) or "总数" in question or ("合计" in question and not sum_request) or ("数量" in question and re.search(r'统计|数一数|总数量|数量合计', question)):
        operations.append("COUNT")
    numeric_filter = bool(re.search(r'(?:大于|小于|超过|高于|低于|不低于|不超过|至少|至多|>=|<=|>|<)\s*-?\d', question))
    subset_count_lookup = bool(re.search(r"其中[^？?；;]{1,40}(?:多少|几)(?:件|项|次|个)", question)) and not numeric_filter and not any(term in question for term in ("利润>0", "利润大于0", "满足条件", "增加效益", "筛选", "哪些"))
    aggregate_target = bool(operations) or sum_request or any(term in question for term in ('最大','最多','最高','最小','最少','最低'))
    if any(term in question for term in ("利润>0", "利润大于0", "满足条件", "增加效益")) or ("其中" in question and aggregate_target and not subset_count_lookup) or (numeric_filter and any(op in operations for op in ('COUNT', 'LIST_DISTINCT'))):
        operations.append("FILTER")
    if sum_request:
        operations.append("SUM")
    if any(term in question for term in ("最大", "最多", "最高")):
        operations.append("MAX")
    if any(term in question for term in ("最小", "最少", "最低")):
        operations.append("MIN")
    return list(dict.fromkeys(operations))


def _comparison_plan(question: str) -> list[str]:
    if re.search(r'(?:汇编|案例库|手册|比选案例).*(?:哪些|几个|多少|包含|包括|章节|目录)', question) and not any(term in question for term in ('优缺点', '区别', '比较', '怎么比选', '如何比选')):
        return []
    return ["COMPARE_OPTIONS"] if any(term in question for term in ("比选", "比较", "区别", "优缺点")) else []


def _project_fact_transfer(question: str) -> list[str]:
    # Preserve an applicability question even when it contains count/amount numbers.
    match = re.search(r"^([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,40})的[^？?；;]{1,80}?(?:能否|是否|可否)直接(?:采用|套用)([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,40})的(?=\d)", question)
    if not match:
        return []
    target, source = match.groups()
    if target in source or source in target or not any(marker in target for marker in ("项目", "工程", "学校", "中学", "医院", "厂房", "大楼", "园区", "校区")):
        return []
    return [target, source]




def _query_type(question: str, aggregation: list[str], comparison: list[str]) -> str:
    if overview_title(question):
        return 'DOCUMENT_OVERVIEW'
    stages = design_depth_stages(question) or design_deliverable_stages(question)
    if stages:
        return 'MULTI_FACT' if len(stages) > 1 else 'POLICY_QUERY'
    if _project_fact_transfer(question):
        return "PROJECT_FACT_APPLICABILITY"
    if definition_target(question):
        return "DEFINITION_QUERY"
    if any(term in question for term in ("评审", "会议", "会审")) and any(term in question for term in ("参加", "参会", "参与")) and any(term in question for term in ("单位", "部门", "专家", "谁")) and not any(op in aggregation for op in ("COUNT", "SUM", "MAX", "MIN", "FILTER")):
        return "MEETING_PARTICIPANTS"
    if comparison and not any(item in aggregation for item in ("GROUP_BY", "COUNT", "FILTER", "SUM", "MAX", "MIN")):
        return "COMPARISON_QUERY" if "比较" in question or "区别" in question else "OPTION_QUERY"
    if re.search(r"[ABC]级", question) and any(term in question for term in ("做法", "品牌", "供应商")):
        return "STRUCTURED_QUERY"
    if aggregation == ['LIST_DISTINCT']:
        if re.search(r'哪些(?:步骤|流程|环节)', fact_request(question)):
            return 'METHOD_QUERY'
        if any(term in question for term in ('图审', '审核要点')):
            return 'POLICY_QUERY'
        if any(term in question for term in ('经验', '复盘', '教训')):
            return 'CASE_QUERY'
    if aggregation:
        return "AGGREGATION_QUERY" if any(item in aggregation for item in ("GROUP_BY", "COUNT", "SUM", "FILTER", "MAX", "MIN")) else "STRUCTURED_QUERY"
    if comparison:
        return "COMPARISON_QUERY" if "比较" in question or "区别" in question else "OPTION_QUERY"
    if any(term in question for term in ("责任状", "制度", "规定", "要求", "图审", "规范")):
        return "POLICY_QUERY"
    if any(term in question for term in ("如何", "怎么", "怎样", "方法", "流程", "编制", "计算方式", "计算公式", "公式")):
        return "METHOD_QUERY"
    if any(term in question for term in ("案例", "经验", "复盘")):
        return "CASE_QUERY"
    if _parallel_fact_subquestions(question):
        return "MULTI_FACT"
    if len(_projects(question)) >= 2:
        return "MULTI_HOP_QUERY"
    if any(term in question for term in ("多少", "日期", "时间", "金额")):
        return "SINGLE_FACT"
    return "MULTI_FACT" if "、" in question or "和" in question else "SOURCE_LOOKUP"


def definition_target(question: str) -> str:
    text = question.strip().rstrip('？?。 ').removeprefix('请问')
    match = re.fullmatch(r'(.{2,30}?)的?(?:定义|含义|概念)(?:是什么)?|什么是(.{2,30})|([^的，,、；;]{2,20})是什么', text)
    target = next((part for part in match.groups() if part), '') if match else ''
    if text.endswith('是什么') and re.search(r'(?:节点|条款|范围|清单|章节|构成|组成|流程|步骤|工期|面积|付款|支付|单位|人员|格式|用途|归属|指标|限额|经验|教训)(?:安排|要求)?$', target):
        return ''
    if any(term in target for term in ('金额', '日期', '型号', '品牌', '数量', '负责人', '分值', '评分', '做法', '公式', '关系式', '计算方式', '计算方法', 'A级', 'B级', 'C级', '项目中')):
        return ''
    return target.strip()


def _document_hints(question: str, query_type: str) -> tuple[list[str], list[str]]:
    if query_type == "MEETING_PARTICIPANTS":
        return ["MEETING_MINUTES"], ["会议纪要"]
    if query_type == "PROJECT_FACT_APPLICABILITY":
        return ["PROJECT_CASE", "RETROSPECTIVE"], ["项目案例"]
    if "责任状" in question:
        return ["RESPONSIBILITY_CONTRACT"], ["责任文件"]
    if "任务书" in question:
        return ["DESIGN_TASK_BOOK", "TEMPLATE"], ["标准模板", "管理指南"]
    if any(term in question for term in ("图审", "审核要点")):
        return ["TABLE_LEDGER", "MANAGEMENT_GUIDE"], ["管理指南", "标准模板"]
    if query_type == "AGGREGATION_QUERY" and re.search(r"20\d{2}(?:年|年度)", question) and "项目" in question:
        return ["WORK_SUMMARY", "RESPONSIBILITY_CONTRACT", "TABLE_LEDGER", "PROJECT_PLAN"], ["工作总结", "责任文件", "台账"]
    if query_type in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"}:
        return ["TABLE_LEDGER", "PROJECT_PLAN"], ["台账", "项目策划"]
    if query_type == "POLICY_QUERY":
        return ["POLICY", "WORK_PLAN", "MANAGEMENT_GUIDE"], ["正式制度", "管理指南", "工作计划"]
    if query_type == "CASE_QUERY":
        return ["PROJECT_CASE", "RETROSPECTIVE"], ["项目案例"]
    if query_type == "METHOD_QUERY":
        return ["MANAGEMENT_GUIDE"], ["管理指南"]
    return [], []


def _response_constraints(question: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", question)[1:] if any(term in part for term in ("不得写成", "不要填写", "无需填写")) and not any(term in part for term in ("？", "?", "是否", "为什么", "怎么", "如何", "哪些", "多少"))]


def _subquestions(question: str, aggregation: list[str], entities: list[str]) -> list[str]:
    if overview_title(question):
        return [question]
    depths = design_depth_stages(question)
    if depths:
        if re.search(r'按什么文件|依据什么|依据哪|执行什么文件', question):
            return [stage + '的设计深度按什么文件执行？' for stage in depths]
        return [stage + '的设计深度要求是什么？' for stage in depths]
    if annual_plan_kind(question) == 'BOTH':
        return ['公司年度工作计划如何检查执行情况？', '项目年度设计进度计划如何检查与纠偏？']
    stages = design_deliverable_stages(question)
    if stages:
        if re.search(r'经济(?:文件|成果)', question):
            return [stage + '阶段应提交哪些经济文件？' for stage in stages]
        return [stage + '的提交成果要求是什么？' for stage in stages]
    if _query_type(question, aggregation, []) == "MEETING_PARTICIPANTS":
        return [question]
    values = []
    task_book_count = "任务书" in question and any(marker in question for marker in ("多少个项目", "收录多少", "收录了多少"))
    task_book_coverage = "任务书" in question and "覆盖" in question and any(marker in question for marker in ("业态", "专业"))
    if task_book_count:
        values.append("任务书汇编收录的项目数量")
    if task_book_coverage:
        values.append("任务书覆盖的业态范围")
    if task_book_count or task_book_coverage:
        return values
    if task_list_request(question, aggregation):
        return ['列出目标单位的全部督办事项']
    clauses = [value.strip() for value in re.split(r"[？?；;]+", question) if value.strip()]
    constraints = set(_response_constraints(question))
    clauses = [clause for clause in clauses if clause not in constraints]
    if len(clauses) > 1:
        return clauses
    if re.search(r"(?:哪|哪些)\s*[0-9一二三四五六七八九十]+\s*(?:个|项|条|步|维度|方面)", question):
        return [question]
    if "组织架构" in question and "人员配置" in question:
        return ["组织架构", "人员配置"]
    if "组织架构" in question or ("组织" in question and "岗位" in question):
        return [
            "组织定位和隶属关系",
            "各层级的岗位或机构设置",
            "适用条件或选设边界",
        ]
    if aggregation == ['LIST_DISTINCT'] and _query_type(question, aggregation, []) in {'CASE_QUERY', 'POLICY_QUERY'}:
        return [question]
    parallel = [] if any(operation in aggregation for operation in ('GROUP_BY', 'FILTER')) else _parallel_fact_subquestions(question)
    if parallel:
        return parallel
    if "LIST_DISTINCT" in aggregation:
        values.append("列出目标范围内的类别或专业")
    if "GROUP_BY" in aggregation and "COUNT" in aggregation:
        values.append("按目标分组统计每组数量")
    if "FILTER" in aggregation and "COUNT" in aggregation:
        values.append("按条件筛选后统计数量")
    if "MAX" in aggregation or "MIN" in aggregation:
        values.append("按目标指标从同一完整表格行中确定极值")
    if "督办" in question and any(term in question for term in ("什么", "哪些", "事项")):
        values.append("列出目标单位的全部督办事项")
    return list(dict.fromkeys(values))


def design_deliverable_stages(question: str) -> list[str]:
    if re.search(r'费用|金额|工期|审批|验收|多少|几套|几份|几张|日期|时间', question):
        return []
    if not re.search(r'成果|交付物|提交物|经济文件', question) or not re.search(r'提交|交付|区分|区别|差异|不同|分别|应包括|应包含|成果(?:要求|清单|有哪些|包括|包含)', question):
        return []
    names = re.findall(r'方案(?:设计)?|初步设计|施工图(?:设计)?', question)
    return list(dict.fromkeys(name if name.endswith('设计') else name + '设计' for name in names))


def fact_request(question: str) -> str:
    text=re.sub(r'^(?:请问|请|根据|依据)', '', question).strip(' ：:')
    text=re.sub(r'^(?:按(?:照)?|根据|依据)?[^，,：:？?]{2,80}(?:指南|手册|细则|办法|规定|标准)》?(?:规定|要求|里|中)?[，,：:]', '', text)
    reference=re.match(r'^([^，,：:？?]{2,60})责任(?:状|书)(?:要求|规定|中的?|里|对|关于|[，,：:])[，,：:]?',text)
    if reference and ('公司' not in reference[1] or reference[1].count('公司')==1 and any('公司' in value for value in _organizations(reference[1]))):
        text=text[reference.end():]
    text=re.sub(r'^20\d{2}年\d{1,2}月[^，,：:？?]{0,30}(?:推进会|会议)(?:上|中|后)[，,：:]?', '', text)
    text=re.sub(r'^[^，,：:？?]{2,65}(?:任务表|台账|清单|手册)(?:里|中)[，,：:]?', '', text)
    text=re.sub(r'^(?:设计|技术)管理制度(?:中|里)?(?=(?:如何|怎么|怎样)(?:进行|开展|组织)[^？?，,]{2,24}(?:检查|核查|考核|复核)[？?]?$)', '', text)
    return text


def task_list_request(question: str, operations: list[str] | None = None) -> bool:
    return (any(term in question for term in ('督办', '监督任务', '工作任务', '待办'))
            and any(term in question for term in ('什么', '哪些', '列出'))
            and not re.search(r'已经完成|已完成|完成情况|完成状态|已办结|已经办结', question)
            and not set(operations or []) & {'COUNT', 'SUM', 'GROUP_BY', 'FILTER', 'MAX', 'MIN'})


def _parallel_fact_subquestions(question: str) -> list[str]:
    """Split a shared-predicate question when it explicitly asks about joined targets."""
    question = fact_request(question)
    # Comma-separated project/topic framing is scope, not another requested value.
    question = re.sub(r'^[^，,？?；;]+项目[，,]\s*', '', question)
    question = re.sub(r'^[^，,？?；;]+方面[，,]\s*', '', question)
    fields = r'(?:数量|金额|月份|时间|期限|日期|比例|完整度|深度)'
    scalar = re.fullmatch(r'(.*?)的?(' + fields + r'(?:(?:和|与|及|、)' + fields + r')+)((?:分别|各)?(?:有什么要求|有何规定|是多少|是什么|为多少))[？?]?', question)
    if scalar:
        subject = scalar[1].removesuffix('的')
        return [subject + field + scalar[3] for field in re.split(r'和|与|及|、', scalar[2])]
    if not re.search(r'分别|各自', question) and re.search(r'(?:如何|怎么|怎样)(?:共同|协同|配合)', question):
        return []
    question = re.sub(r'^[^，,：:？?]{2,45}(?:课件|手册|细则|报告|资料)(?:(?:里|中|的)[，,：:]?|规定[，,：:])', '', question)
    question = re.sub(r'^[^，,：:？?]{2,60}(?:任务书|计划|清单|台账)[，,：:]', '', question)
    shared_relation = r'计入|归入|纳入|计列|属于|归属'
    if '分别' not in question and len(re.findall(shared_relation, question)) == 1 and re.search(r'(?:'+shared_relation+r')(?:哪里|哪[^？?]{0,12}|什么[^？?]{0,12})[？?]?$', question):
        return []
    # A list of work areas before a shared "的 ... 做法/标准" phrase is query scope,
    # not a set of independently requested facts.
    if "分别" not in question and re.search(r"[^，,；;、]{1,16}、[^，,；;、]{1,12}的[^？?]*?(?:做法|标准|要求|指标)", question):
        return []
    match = re.search(
        r"((?:分别|各)?(?:是多少|是什么|是哪[^？?]*|什么|如何[^？?]*|哪些[^？?]*|哪[^？?]*|多少[^？?]*|各指[^？?]*|分别指[^？?]*))\s*[？?]?\s*$",
        question,
    )
    if not match:
        return []
    prefix = question[: match.start()].strip(" ，,。 ")
    if re.search(r"[？?；;]", prefix):
        return []
    if prefix.count('的') == 1:
        scope, fields = prefix.rsplit('的', 1)
        if re.search(r'和|与|及|、', fields):
            question = fields + match.group(1)
            prefix = fields
    parentheticals = []
    protected_projects = []
    named_titles = []

    def protect_parenthetical(match: re.Match[str]) -> str:
        parentheticals.append(match.group(0))
        return f"\x00{len(parentheticals) - 1}\x00"

    def protect_title_value(value: str) -> str:
        named_titles.append(value)
        return f"\x02{len(named_titles) - 1}\x02"

    def protect_named_title(match: re.Match[str]) -> str:
        return protect_title_value(match.group(0))

    split_prefix = re.sub(r"（[^（）]*）|\([^()]*\)", protect_parenthetical, prefix)
    split_prefix = re.sub(r"《[^《》]+》", protect_named_title, split_prefix)
    title = "EPC项目设计管理方法与实务"
    if title in split_prefix:
        split_prefix = split_prefix.replace(title, protect_title_value(title))
    for project in sorted(set(_projects(prefix)), key=len, reverse=True):
        if not any(marker in project for marker in ('和', '与', '及')) or project not in split_prefix:
            continue
        placeholder = f"\x01{len(protected_projects)}\x01"
        split_prefix = split_prefix.replace(project, placeholder)
        protected_projects.append(project)
    raw_parts = re.split(r"以及|并且|同时|和|及|与|[、,，]", split_prefix)
    raw_parts = [
        re.sub(
            r"\x01(\d+)\x01",
            lambda match: protected_projects[int(match.group(1))],
            re.sub(
                r"\x02(\d+)\x02",
                lambda match: named_titles[int(match.group(1))],
                re.sub(r"\x00(\d+)\x00", lambda match: parentheticals[int(match.group(1))], part),
            ),
        )
        for part in raw_parts
    ]
    full_parts = [*raw_parts[:-1], raw_parts[-1] + match.group(1)]
    independent_questions = [
        part.strip(" ，,。 \\\"'“”‘’（）()《》【】")
        for part in full_parts
        if re.search(r"(?:多少|几|哪|什么|如何|是否|吗)", part)
    ]
    if len(independent_questions) >= 2:
        return independent_questions
    if named_titles and len(independent_questions) == 1:
        return []
    parts = []
    for raw in raw_parts:
        focus = raw.rsplit("，", 1)[-1].rsplit(",", 1)[-1]
        if "的" in focus:
            focus = focus.rsplit("的", 1)[-1]
        focus = re.sub(r"^(?:同时|并且)", "", focus)
        focus = focus.strip(" \\\"'“”‘’（）()《》【】,，、")
        if focus and not focus.endswith(("中", "内", "上", "下")):
            parts.append(focus)
    if len(parts) < 2:
        return []
    suffix = match.group(1).strip()
    return [f"{part}{suffix}" for part in parts]


def annual_plan_kind(question: str) -> str:
    if not re.search(r'年度|20\d{2}年', question) or '计划' not in question or not re.search(r'检查|执行|落实|考核|纠偏', question):
        return ''
    corporate = bool(re.search(r'公司|分公司|总部|设计与技术|设计管理工作计划', question))
    project = bool(re.search(r'项目|工程|设计进度|出图|图纸需求', question))
    if corporate and project:
        return 'BOTH' if re.search(r'两类|分别|各自|以及|和|与', question) else 'PROJECT_DESIGN_SCHEDULE'
    return 'CORPORATE_WORK_PLAN' if corporate else 'PROJECT_DESIGN_SCHEDULE' if project else 'UNSPECIFIED'


def design_depth_stages(question: str) -> list[str]:
    if '深度' not in question or re.search(r'费用|金额|工期|审批|验收|多少|几套|几份|几张|日期|时间|清单|交付物|提交物', question):
        return []
    names = re.findall(r'方案(?:设计)?|初步设计|施工图(?:设计)?', question)
    return list(dict.fromkeys(name if name.endswith('设计') else name + '设计' for name in names))
