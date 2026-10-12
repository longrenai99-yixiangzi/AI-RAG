from __future__ import annotations

import math
import hashlib
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.bm25 import tokenize


def search_record_role(record: dict[str, Any]) -> str:
    """Separate reviewed cards, direct body and navigation without granting authority."""
    if (record.get("knowledge_card") or {}).get("approval_status") == "OWNER_CONFIRMED":
        return "REVIEWED_KNOWLEDGE"
    path = str(record.get("source_path") or "").replace("\\", "/").lower()
    if any(marker in path for marker in ("/06_索引/", "/wiki/sources/")) or Path(path).name in {"index.md", "log.md"}:
        return "NAVIGATION"
    text = str(record.get("raw_text") or record.get("text") or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if path.endswith('.md') and lines and sum('file://' in line or '[[' in line for line in lines) >= len(lines) * .6:
        return "LINK_REGISTRATION"
    return "PRIMARY_BODY"


def search_role_priority(record: dict[str, Any], query: str) -> int:
    role = search_record_role(record)
    navigation = any(term in query for term in ("目录", "索引", "登记", "导航"))
    if navigation:
        return 0 if role in {"NAVIGATION", "LINK_REGISTRATION"} else 1
    if '原件' in query or re.search(r'\.(?:docx?|xlsx?|pdf|pptx?|wps)\b', query, re.I):
        return {"PRIMARY_BODY": 0, "REVIEWED_KNOWLEDGE": 1, "LINK_REGISTRATION": 2, "NAVIGATION": 3}[role]
    return {"REVIEWED_KNOWLEDGE": 0, "PRIMARY_BODY": 1, "LINK_REGISTRATION": 2, "NAVIGATION": 3}[role]


def search_match_kind(record: dict[str, Any], query: str) -> str:
    """Match the requested subject in the body, not noisy document metadata."""
    ignored = {'设计', '项目', '资料', '内容', '与', '和', '的', '及', '相关', '请', '查询', '搜索', '期间', '指标'}
    terms = list(dict.fromkeys(t for t in tokenize(query) if len(t) >= 2 and t not in ignored))
    if not terms:
        terms = [query.strip().casefold()]
    card = record.get('knowledge_card') or {}
    title = str(card.get('title') or record.get('heading_path') or '') + ' ' + ('' if card else str(record.get('file_name') or ''))
    body = str(record.get('raw_text') or record.get('text') or '')
    reference_only=search_record_role(record) in {'NAVIGATION','LINK_REGISTRATION'} and not any(term in query for term in ('目录','索引','导航','登记'))
    if '设计计划' in query:
        phrases=('设计计划','设计进度','设计节点','专项设计')
        if any(p in title for p in phrases):return 'RELATED' if reference_only else 'DIRECT'
        if any(p in body for p in phrases):return 'RELATED' if card or reference_only else 'BODY'
        return ''
    if all(t.casefold() in title.casefold() for t in terms):
        return 'RELATED' if reference_only else 'DIRECT'
    if all(t.casefold() in body.casefold() for t in terms):
        return 'RELATED' if card or reference_only else 'BODY'
    return ''


def document_title_matches(file_name: str, query: str) -> bool:
    """Find requested files by their names; body mentions do not make a document."""
    name=re.sub(r'\s+','',file_name).casefold()
    compact=re.sub(r'\s+','',query).casefold()
    terms=list(dict.fromkeys(t.casefold() for t in tokenize(query) if re.fullmatch(r'[\w\u3400-\u9fff.]+',t) and t not in {'查','找','搜索','文件','资料','的'}))
    if not terms or not all(re.sub(r'\s+','',term) in name for term in terms):
        return False
    if '设计任务书' in compact:
        return '设计任务书' in name and not any(t in name for t in ('经验总结','汇编','目录','流程','方法','操作骨架','要点','指南','说明','培训','管理手册','管理细则','审查意见'))
    return True


def reviewed_method_card_matches(candidate: dict[str, Any], question: str, plan: dict[str, Any]) -> bool:
    card = candidate.get("knowledge_card") or {}
    body = str(candidate.get("raw_text") or candidate.get("text") or "")
    if card.get("approval_status") != "OWNER_CONFIRMED" or card.get("response_format") != "METHOD_GUIDE" or not candidate.get("source_version"):
        return False
    if card.get("approved_content_sha256") != hashlib.sha256(body.encode("utf-8")).hexdigest():
        return False
    if plan.get("project") or plan.get("year") or any(op in plan.get("aggregation_plan", []) for op in ("COUNT", "SUM", "MAX", "MIN")):
        return False
    if re.search(r"(?:金额|费用|造价|面积|比例|评分|分值|日期|时间|工期).{0,12}(?:是多少|为多少|多少|几[分天])|(?:哪种|哪一个).{0,8}(?:最优|最好|更好)|(?:何时|哪天|谁)(?:批准|审批|完成)", question):
        return False
    return any(term in question for term in card.get("topic_terms") or []) and any(term in question for term in ("骨架", "要点", "目录", "清单", "依据表", "复核", "编制", "应包含", "包含哪些内容", "包括哪些内容"))


def reviewed_fact_rows(candidate: dict[str, Any], question: str, plan: dict[str, Any]) -> list[str]:
    card = candidate.get("knowledge_card") or {}
    body = str(candidate.get("raw_text") or candidate.get("text") or "")
    if card.get("response_format") != "VERIFIED_FACT_SHEET" or card.get("approval_status") != "OWNER_CONFIRMED" or not candidate.get("source_version"):
        return []
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != card.get("approved_content_sha256"):
        return []
    if any(term in question for term in ("能否直接", "是否直接", "可以直接", "套用", "断定同口径")):
        return []
    if card.get("project_terms") and plan.get("project") and not all(any(term in name for term in card["project_terms"]) for name in plan["project"]):
        return []
    if card.get("project_terms") and not any(term in question for term in card["project_terms"]):
        return []
    years = list(plan.get("year") or [])
    if not card.get("year") and years and not all(year + "年" in body for year in years):
        return []
    if card.get("year") and ((years and years != [str(card["year"])]) or (not years and not card.get("project_terms")) or plan.get("period") not in {"", card.get("period")}):
        return []
    if plan.get("organization") and not all(value in body for value in plan["organization"]):
        return []
    rows = [row["text"] for row in card.get("fact_rows") or [] if any(term in question for term in row.get("topic_terms") or [])]
    if '合同范围' in body and '提前交付' in body:
        asks_contract='合同范围' in question
        asks_delivery=any(t in question for t in ('提前','验收','入住','交付','日前'))
        if asks_contract != asks_delivery:
            rows=[part for text in rows for part in text.split('；') if ('合同范围' in part if asks_contract else '提前交付' in part)]
    return rows if rows and all(text in body for text in rows) else []


def reviewed_fact_missing(candidate: dict[str, Any], question: str, plan: dict[str, Any]) -> list[str]:
    """A matching topic does not prove that all requested facts are supported."""
    rows = reviewed_fact_rows(candidate, question, plan)
    if not rows:
        return [question]
    card = candidate.get("knowledge_card") or {}
    supported = " ".join(rows + [str(term) for row in card.get("fact_rows") or [] for term in row.get("topic_terms") or []])
    clauses = list(plan.get("subquestions") or []) if len(plan.get("subquestions") or []) > 1 else []
    if not clauses:
        clauses = [part for part in re.split(r"[，,；;？?]|以及|同时|并(?:请|且)?|(?<=[\u3400-\u9fff])(?:和|及|与)(?=[\u3400-\u9fff])", question) if part.strip()]
    aliases = {"金额": ("万元", "亿元", "元"), "收益": ("节约", "创效", "工期"), "上限": ("最高", "上限"), "赔偿": ("赔偿", "赔付", "元"), "次数": ("次",), "形式": ("固定总价", "价格形式")}
    ignored = {"多少", "哪些", "什么", "是什么", "是否", "分别", "其中", "项目", "预计", "预估", "怎样", "调整", "各", "多少万元", "万元", "元", "万平方米", "平方米", "记载", "总结", "合同", "暂定", "最高", "各部门", "单位", "参加", "参与", "参会"}
    missing = []
    for clause in clauses:
        # Keep property words, while removing the project context and question verbs.
        clean = clause
        for project in plan.get("project") or []:
            clean = clean.replace(project, "")
        # A currency unit alone cannot support a different qualified measurement.
        qualified = re.findall(r"([\u3400-\u9fff]{2})(?:金额|面积|用量|人数|高度|长度|数量)", clean)
        if any(prefix not in supported and prefix not in {"预计", "预估", "估算", "合计", "各自"} for prefix in qualified):
            missing.append(clause)
            continue
        terms = [term for term in query_terms(clean) if term not in ignored and not any(term in value for value in card.get("project_terms") or []) and not term.isdigit()]
        hits = [term for term in terms if term in supported or any(alias in supported for alias in aliases.get(term, ()))]
        if terms and not hits:
            missing.append(clause)
    return missing


def cross_period_comparison(question: str) -> bool:
    return bool(re.search(r"(?:能否|是否|可否|断定|直接).{0,100}(?:同口径|增长|增量|同比|相减)", question) and any(term in question for term in ("上半年", "半年")) and any(term in question for term in ("全年", "年度")) and len(set(re.findall(r"20\d{2}", question))) >= 2)


def definition_sentence(text: str, target: str) -> str:
    if not target:
        return ''
    subject = r'\s*'.join(re.escape(char) for char in target)
    match = re.search(r'(?<![\u3400-\u9fffA-Za-z0-9])' + subject + r'\s*(?:是\s*指|指\s*的\s*是|定义\s*为|是)([^。；;]{5,500})[。；;]?', text)
    if not match:
        return ''
    sentence = ''.join(match.group(0).split())
    if '《' in sentence or '认证依据' in sentence or '采用标准' in sentence:
        return ''
    return sentence.rstrip('；;') + ('' if sentence.endswith('。') else '。')


def organization_placement(text: str) -> bool:
    return bool(re.search(r'(?:中心|机构)[^。；;]{0,50}(?<![不未非])(?:隶属|归属|作为)[^。；;]{0,35}(?:部室|部门|管理部)', text))


def design_procedure_question(question: str) -> bool:
    """Keep procedure ranking from changing unrelated file or delivery lookups."""
    return bool(re.search(r'设计(?:成果|文件)?质量|图纸质量', question) or all(term in question for term in ('设计交付', '施工', '衔接')))


def business_term_aliases(question: str) -> dict[str, tuple[str, ...]]:
    aliases={'交付':('交付','提交','移交','设计交底','设计质量交底','图纸会审'),'衔接':('衔接','移交','交底','会审','施工配合','配合施工')}
    if re.search(r'设计(?:成果|文件)?质量|图纸质量', question):
        aliases['质量检查'] = ('质量检查', '质量审查', '成果审查', '图纸审查', '审查意见')
        aliases['质量'] = ('质量', '成果审查', '文件审查', '图纸审查')
        aliases['检查'] = ('检查', '审查', '复查', '复核')
    aliases['数量'] = ('数量', '个', '项', '份', '件', '条', '次', '座', '家', '人')
    aliases['总体'] = ('总体', '整体', '合计')
    aliases['月份'] = ('月份', '月')
    aliases['几月份'] = ('月份', '月')
    aliases['实施'] = ('实施', '开展')
    aliases['组织机构'] = ('组织机构', '组织架构')
    if '组织机构' in question:
        aliases['机构'] = ('机构', '架构')
    aliases['几分'] = ('分',)
    aliases['职责'] = ('职责', '负责')
    if any(term in question for term in ('经验', '复盘', '教训')):
        aliases['经验总结'] = ('经验总结', '实践教训', '经验', '教训')
        aliases['复用'] = ('复用', '借鉴', '建议后续', '后续项目')
        aliases['值得'] = ('值得', '建议', '借鉴')
    if '中心' in question:
        aliases['隶属'] = ('隶属', '作为', '归属')
    if '评估' in question and any(term in question for term in ('哪些方面', '哪几个方面')):
        aliases['文件'] = ('文件', '设计完整度', '设计深度')
    if any(term in question for term in ('文件','文档','图纸','版本','交付')) and re.search(r'如何|怎么|怎样',question) and '运行状态' not in question:
        aliases['状态']=('状态','接收','发放','移交','归档')
    return aliases


def scalar_fact_parts(question: str, text: str) -> dict[str, list[str]] | None:
    from app.retrieval.query_planner_v1 import fact_request
    fields = r'(?:数量|金额|月份|时间|期限|日期|比例)'
    request = re.fullmatch(r'([^，,：:？?；;和与及、]*?)的?(' + fields + r'(?:(?:和|与|及|、)' + fields + r')*)(?:分别|各)?(?:有什么要求|有何规定|是多少|是什么|为多少)[？?]?', fact_request(question))
    if not request:
        return None
    subject = query_terms(request[1].removesuffix('的'))
    parts = [part for part in re.split(r'[。；;|\n]', text) if all(term.casefold() in part.casefold() for term in subject)]
    result = {}
    for field in re.split(r'和|与|及|、', request[2]):
        if field == '数量':
            result[field] = [part for part in parts if re.search(r'(?<!第)(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*(?:个(?!百分点)|项|份|件|条|次|座|家|人)|数量[^。；;|]{0,12}\d+', part)]
        elif field == '月份':
            result[field] = [part for part in parts if re.search(r'(?:\d{1,2}|[一二三四五六七八九十]+)月', part)]
        else:
            result[field] = parts
    return result


def equation_lines(text: str) -> list[str]:
    return re.sub(r'([=＝+＋*/÷×])[ \t]*\n[ \t]*', r'\1', text).splitlines()


def answer_support_gap(question: str, text: str, plan: dict[str, Any] | None = None) -> str:
    """Check the requested fact and answer form, using body text rather than rank."""
    from app.retrieval.query_planner_v1 import definition_target, fact_request
    from app.ingestion.normalization.markdown_normalizer import strip_markdown_links
    body = re.sub(r'\s+', '', strip_markdown_links(text)).casefold()
    if not body:
        return '未取得可用于回答的正文。'
    clean = question
    for project in (plan or {}).get('project') or []:
        clean = clean.replace(str(project), '')
    clean = fact_request(clean)
    clean = re.sub(r'^(?:的)?(?:原报告|报告|原文|原件|原表)(?:中(?:记载|记录)?|所述|记载|记录|的)?(?:的)?[，,：:]?', '', clean)
    if re.search(r'未评估|未评范围|没有评分|没评分',clean):
        objects=[p for p in ('电气','风电场','升压站','集电线路') if p in clean]
        return '' if '未评估' in body and all(p in body for p in objects) else '正文未明确所问的未评估对象或状态。'
    assessment = assessment_value_parts(clean, text)
    if assessment is not None:
        return '' if assessment else '原文未将所问专业或总体与对应的完整度、深度数值逐项匹配；分项值、表头和权重不能代替。'
    if '图纸' in clean and re.search(r'什么阶段|哪个阶段|投标图纸|初步设计图纸',clean):
        if not re.search(r'(?:投标|初步设计|施工图|方案设计)(?:阶段)?图纸',body):
            return '正文未明确所问图纸的阶段或资料类型。'
        if re.search(r'多少张|几张',clean) and not (re.search(r'\d+张',body) or '数量' in body and re.search(r'行：[\s\S]*\d',text)):
            return '正文未同时给出所问图纸的数量。'
        return ''
    if re.search(r'多少张|几张', clean) and not (re.search(r'\d+张',body) or '数量' in body and '图纸' in body and re.search(r'行：[\s\S]*\d',text)):
        return '正文未给出与所问图纸对应的数量。'
    if '截止日期' in clean or '截至日期' in clean:
        return '' if re.search(r'(?:截止|截至)[^。\n]{0,8}20\d{2}年\d{1,2}月\d{1,2}日', text) else '正文未明确资料截止日期。'
    if re.search(r'哪些问题|什么问题|存在哪些问题|主要问题',clean):
        if not re.search(r'缺少|缺失|缺设计|未提供|未体现|未设计|不满足|不足|不一致|偏小|偏大|无法|不完善',body):
            return '正文只有评估范围或检查要点，没有该专业的具体问题记录。'
    aspects=re.search(r'从(?:哪|哪些)([一二三四五六七八九十\d]+)个方面',clean)
    if aspects:
        source_aspects=re.search(r'从([^。\n]{3,120}?)(?:等)?([一二三四五六七八九十\d]+)个方面',text)
        numbers={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        value=lambda s:numbers.get(s,int(s) if s.isdigit() else -1)
        return '' if source_aspects and value(aspects[1])==value(source_aspects[2]) else '正文未完整列明所问数量的评估方面。'
    clean = clean.replace('施工实施','施工')
    procedure = re.search(r'^([^，,]{2,24}?)(?:实施|开展)(?:有)?哪些(?:步骤|流程|环节)', clean)
    if procedure:
        target = re.escape(procedure[1].casefold())
        if not re.search(target+r'.{0,4}(?:实施|开展|流程|步骤)|(?:实施|开展|组织|进行|准备).{0,6}'+target, body):
            return '正文未将所问对象与实施流程对应，编制依据或原则介绍不能代替步骤。'
    from app.retrieval.query_planner_v1 import design_deliverable_stages, design_depth_stages, annual_plan_kind
    depths = design_depth_stages(clean)
    if depths:
        name = str((plan or {}).get('evidence_file_name') or '')
        excerpts = [design_depth_excerpt(text, stage, name) for stage in depths]
        if not any(excerpts):
            return '正文未给出所问阶段的设计深度要求，成果清单不能代替。'
        if re.search(r'按什么文件|依据什么|依据哪|执行什么文件', clean) and not any(re.search(r'《[^》]+》', excerpt) for excerpt in excerpts):
            return '正文未明确所问深度依据的文件名称，不能用图纸清单或“本规定”代替。'
        return ''
    kind = annual_plan_kind(clean)
    if kind == 'UNSPECIFIED':
        return '请先明确公司年度工作计划还是项目年度设计进度计划。'
    if kind == 'CORPORATE_WORK_PLAN' and not re.search(r'年度(?:设计管理)?(?:工作)?计划|20\d{2}年设计与技术', body):
        return '公司年度工作计划不能由项目出图进度、专项检查或其他业务年度计划替代。'
    if kind == 'PROJECT_DESIGN_SCHEDULE' and not re.search(r'设计进度计划|年度设计计划|图纸需求计划', body):
        return '项目年度设计进度计划不能由公司年度工作目标或年底考核通知替代。'
    stages = design_deliverable_stages(clean)
    if stages:
        return '' if any(design_deliverable_excerpt(text, stage, clean) for stage in stages) else '正文没有将所问设计阶段与具体提交成果对应，阶段分类或其他阶段清单不能代替。'
    if any(term in clean for term in ('经验', '复盘', '教训')) and re.search(r'未(?:记录|形成|提供|总结)|待完善|待补充', body) and not re.search(r'导致|影响|不足|缺乏|无法|滞后|超概|返工|延误', body):
        return '正文只是待编或待补录的说明，没有可复用的具体问题或教训。'
    if '中心' in clean and '隶属' in clean and not organization_placement(body):
        return '正文没有明确所问中心的隶属关系，不能用名称或搜索提示代替。'
    if '中心' in clean and '隶属' in clean and re.search(r'哪(?:一)?个部门|哪个部门', clean):
        parent = re.search(r'(?:隶属|归属|作为)([^。；;，,]{2,35}?部)(?!室)', body)
        if parent is None or re.search(r'某|相关|有关|其他|待定|未明确', parent[1]):
            return '正文只说明机构层级或泛称部门，没有给出明确的上级部门名称。'
    scalar = scalar_fact_parts(clean, text)
    if scalar is not None and any(not parts for parts in scalar.values()):
        return '正文未将所问对象、动作与相应数值或时间对应；其他事项、检查时间或评分条件不能代替。'
    if re.search(r'已经完成|已完成|完成情况|完成状态|已办结|已经办结', clean) and re.search(r'工作任务|督办事项|监督任务', body) and not re.search(r'完成情况|实际完成|已完成|完成状态|已办结', body):
        return '正文列的是任务要求，未提供实际完成情况，不能用任务替代执行结果。'
    if '数量' in clean and not re.search(r'(?<!第)(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*(?:个|项|份|件|条|次|座|家|人)', body) and '数量' not in body:
        return '正文没有所问数量的数值及计量单位。'
    if '月份' in clean and not re.search(r'(?:\d{1,2}|[一二三四五六七八九十]+)月', body):
        return '正文未提供所问月份。'
    if re.search(r'扣几分|扣多少分', clean) and not re.search(r'扣\d+(?:\.\d+)?分', body):
        return '正文未提供所问扣分数值，表头或其他数字不能代替。'
    if '年度工作计划' in clean and kind != 'PROJECT_DESIGN_SCHEDULE' and not re.search(r'年度(?:设计管理)?(?:工作)?计划', body):
        return '正文没有对应年度工作计划，不能用年度指标或检查排名代替。'
    inspection=re.search(r'(?:如何|怎么|怎样)(?:进行|开展|组织)?([^？?，,]{2,24}?)(?:检查|核查|考核|复核)',clean)
    inspection=inspection or re.search(r'(?:如何|怎么|怎样)(?:进行|开展|组织)?(设计(?:成果|文件)?质量|图纸质量)(?:审查)',clean)
    inspection=inspection or re.search(r'(?:如何|怎么|怎样)(?:组织|开展|进行)?(?:检查|核查|考核|复核|审查)([^？?，,]{2,24})',clean)
    inspection=inspection or re.search(r'(设计(?:成果|文件)?质量|图纸质量)(?:如何|怎么|怎样)(?:组织|开展|进行)?(?:检查|核查|考核|复核|审查)',clean)
    if inspection:
        target=re.escape(inspection[1]).replace('年度工作计划',r'年度(?:设计管理)?(?:工作)?计划')
        if kind == 'CORPORATE_WORK_PLAN':
            target = r'(?:年度(?:设计管理)?(?:工作)?计划|20\d{2}年设计与技术(?:（科技）)?工作计划)'
        elif kind == 'PROJECT_DESIGN_SCHEDULE':
            target = r'(?:设计进度计划|年度设计计划|图纸需求计划)'
        actions=r'检查|核查|考核|复核|督导|跟踪'
        if inspection[1] in {'设计质量', '设计成果质量', '设计文件质量', '图纸质量'}:
            target=r'(?:设计质量|图纸质量|设计(?:成果|文件)(?:质量)?)'
            actions += r'|审查|复查'
        direct=list(re.finditer(r'(?<![未不])(?:'+actions+r'|对)([^。；;，,、|]{0,12})'+target,body))
        direct_object=any(not re.search(r'根据|按照|依据|依照|按|等|决定|影响|包括|体系|提升|提高|优化|以',match[1]) for match in direct)
        organized=list(re.finditer(r'(?<![未不])(?:组织|开展|进行|安排|负责)([^。；;，,、|]{0,10})'+target+r'(?:的)?(?:'+actions+r')',body))
        direct_object=direct_object or any(not re.search(r'根据|按照|依据|依照|按|等|决定|影响|包括|体系|提升|提高|优化',match[1]) for match in organized)
        execution_object=bool(re.search(target+r'[^。；;]{0,60}(?:'+actions+r')[^。；;]{0,15}(?:执行|落实|完成)(?:情况|进度|成效)',body) or re.search(target+r'[^。；;]{0,15}(?:执行|落实|完成)(?:情况|进度|成效)[^。；;]{0,30}(?:'+actions+r')',body))
        if kind == 'PROJECT_DESIGN_SCHEDULE':
            direct_object = direct_object or bool(re.search(target + r'(?:的)?(?:检查|考核|纠偏)', body) and re.search(r'延误|原因|措施|标准|报送', body))
        if not direct_object and not execution_object:
            return '正文未说明怎样检查所问对象，不能用“按该计划检查其他事项”代替计划执行检查。'
    if re.search(r'如何(?:进行)?管理|怎么管理|怎样管理', clean) and not re.search(r'接收|发放|变更|修订|签收|审核|审批|发布|归档|作废|核对|登记|记录|更新|建立|编制|组织|控制|维护|跟踪|确认|检查|调整', body):
        return '正文只有相关字段或名称，尚未给出管理动作。'
    cooperation=re.search(r'(?:如何|怎么|怎样)(?:共同|协同|配合)(?:完成|开展|进行)?([^？?，,]{2,24})',clean)
    if cooperation:
        objects=query_terms(cooperation[1])
        related=[part for part in re.split(r'[。；;]',body) if objects and all(term.casefold() in part for term in objects)]
        if not any(not re.search(r'未(?:说明|提供|建立)|尚未|待补充',part) and re.search(r'共同|双方|协同|配合|协调|专业间',part) and re.search(r'提资|反馈|校核|复核|会审|交底|沟通|调整|修改',part) for part in related):
            return '正文没有所问事项的具体协作动作，不能用年度业绩或单项优化案例代替共同完成的方法。'
    target = definition_target(clean)
    if target:
        return '' if definition_sentence(text, target) else '正文没有提供所问概念的直接定义。'
    clean = re.sub(r'^[^，,：:？?]{2,45}(?:课件|手册|细则|报告|资料)(?:(?:里|中|的)[，,：:]?|规定[，,：:])', '', clean)
    clean = re.sub(r'^[^，,：:？?]{2,60}(?:任务书|计划|清单|台账)[，,：:]', '', clean)
    clean = re.sub(r'^[^，,：:？?]{2,45}(?:清单|台账|表)(?:中|里)[，,：:]?', '', clean)
    clean = re.sub(r'(\d+)号(楼|栋|机|线)', r'\1#\2', clean)
    body = re.sub(r'(\d+)号(楼|栋|机|线)', r'\1#\2', body)
    formation = re.search(r'如何形成([^？?，,]{2,20})', clean)
    if formation:
        method_parts = [part for part in re.split(r'[。；;]', body) if formation[1].casefold() in part]
        if not any(re.search(r'应|需|步骤|流程|编制|收集|提炼|归档|报送|审核', part) for part in method_parts):
            return '问题要求形成方法，正文只有相关成果或完成情况，尚未给出操作方法。'
    service = re.search(r'(.{2,20}?)(?:应用)?如何服务', clean)
    if service and not re.search(r'(?:应用|通过|采用|利用).{0,15}'+re.escape(service[1].casefold()), body):
        return '正文未说明所问技术或管理手段如何应用，不能用服务范围清单代替。'
    if '设计交付' in clean:
        deliveries = [part for part in re.split(r'[。；;]', body) if not re.search(r'装修交付|竣工交付|实体交付|交付运维', part)]
        if not any(re.search(r'(?:设计成果|图纸|图模|模型|设计文件).{0,80}(?:交付|提交|输出|移交)|(?:交付|提交|输出|移交).{0,80}(?:设计成果|图纸|图模|模型|设计文件)', part) or ('施工' in part and re.search(r'组织.{0,20}(?:设计(?:质量)?交底|图纸会审)',part)) for part in deliveries):
            return '正文未对应设计成果、模型或图纸的交付，不能用装修或实体交付代替。'
        if '施工' in clean and '衔接' in clean and not any(re.search(r'施工.{0,70}(?:设计(?:质量)?交底|图纸会审)|(?:设计成果|图纸|图模|模型|设计文件)[^，,、]{0,30}(?:交付|移交|提交)[^，,、]{0,30}施工', part) for part in deliveries):
            return '正文未说明设计成果怎样进入施工实施，不能用价值创造或一般成果提交代替。'
    if any(term in clean for term in ('经验', '复盘', '教训')) and not any(len(part.strip()) >= 25 and re.search(r'应|需|通过|组织|协调|明确|建立|落实|优化|导致|建议|缺乏|不足|统一|负责|提高', part) for part in re.split(r'[。；;\n]', text)):
        return '正文只有经验栏目或相关标题，尚未提供具体做法、问题或教训。'
    if (plan or {}).get('query_type') == 'CASE_QUERY' and (plan or {}).get('project') and re.fullmatch(r'(?:的)?设计(?:管理)?(?:复盘)?(?:有哪[些几]经验|经验是什么|有哪些经验)[？?]?', clean):
        return ''
    workflow_subject = re.search(r'([^，,的]{2,24})的(?:流程|步骤)', clean)
    if workflow_subject and workflow_subject[1].casefold() not in body:
        return '正文未给出所问阶段或对象的流程，不能用总体介绍代替。'
    identifiers = re.findall(r'\d+\s*[#号](?:楼|栋|机|线)', clean)
    if identifiers and not all(re.sub(r'\s+', '', identifier).replace('号', '#').casefold() in body.replace('号', '#') for identifier in identifiers):
        return '正文未对应所问的具体编号，不能拿其他楼栋或设备的数据代替。'
    ignored = {'怎么', '如何', '计算', '公式', '方式', '方法', '需要', '应当', '应该', '包含', '包括', '是否', '哪些', '整体', '建筑', '其中', '分别', '是多少', '是什么', '价是', '暂定', '最高', '最低', '章节', '特点', '主要', '相关', '资料', '课件', '手册', '文件', '模板', '正文', '说明', '给出', '提供', '列出', '步骤', '怎样', '总结', '范围', '单位', '负责', '参加', '哪里', '事项', '哪些方面', '哪几个方面', '哪个'}
    subject = re.sub(r'计算公式|计算方式|计算方法|如何计算|怎么计算|怎么算|公式|分为', '', clean)
    terms = [term for term in query_terms(subject) if term not in ignored and not term.isdigit() and not (service and term == '服务')]
    # Keep named-project checks separate from the generic EPC prefix on a procedure question.
    if re.match(r'^EPC项目设计', clean, re.I) and re.search(r'如何|怎么|怎样', clean) and not (plan or {}).get('project'):
        terms = [term for term in terms if term != 'epc']
    terms = list(dict.fromkeys(terms))
    aliases = {'限价': ('限价', '估算'), '签约': ('签约', '合同价格'), '付款': ('付款', '支付'), '进度': ('进度', '节点'), '组织': ('组织', '部门', '岗位'), '能效': ('能效',), '发电量': ('发电量',), '冷源': ('冷源', '冷热源'), '协同': ('协同', '协调'), '专业': ('专业', '专项'), '输入': ('输入', '依据', '基础资料'), '交付': ('交付', '提交', '成果'), '边界': ('边界', '界面', '范围'), '用于': ('用于', '应用', '挂钩'), '复盘': ('复盘', '总结', '经验'), '经验': ('经验', '亮点', '教训')}
    aliases.update(business_term_aliases(clean))
    if kind == 'PROJECT_DESIGN_SCHEDULE':
        aliases['年度'] = ('年度', '年、季、月、周')
    hits = [term for term in terms if any(value in body for value in aliases.get(term, (term,)))]
    if not terms or len(hits) * 3 < len(terms) * 2:
        return '正文没有充分覆盖问题所问的对象或事项。'
    if not re.search(r'计算|怎么算|怎么.*算|如何.*算|公式', clean) and terms[0] not in hits:
        return '正文缺少所问对象，不能用同主题的其他内容代替。'
    if '用于' in clean and any(word in clean for word in ('哪些', '什么', '事项')):
        relations = [part for part in re.split(r'[。；;，,\n]', text) if re.search(r'用于|应用于|挂钩', part) and not re.search(r'不用于|未用于|尚未|尚无|没有|无应用', part)]
        if not relations:
            return '正文未明确说明所问的应用关系，不能只凭相关词作答。'
    if re.search(r'计算|怎么算|怎么.*算|如何.*算|公式', clean):
        # An equation for a different object is not a calculation answer.
        lines = [re.sub(r'\s+', '', line).casefold() for line in equation_lines(text) if re.search(r'[=＝]|乘以|除以|相乘|相加|相减|求和|加总', line)]
        def matches_expression(line: str) -> bool:
            expression = re.split(r'[=＝]|乘以|除以|相乘|相加|相减|求和|加总', line, maxsplit=1)
            if len(expression) < 2 or not re.search(r'\w', expression[1]):
                return False
            lhs = expression[0]
            critical = terms[-2:] if len(terms) >= 2 else terms
            return sum(any(value in line for value in aliases.get(term, (term,))) for term in terms) * 3 >= len(terms) * 2 and all(any(value in lhs for value in aliases.get(term, (term,))) for term in critical)
        if not any(matches_expression(line) for line in lines):
            return '问题要求计算依据，但正文未提供对应关系式或计算步骤。'
    expected = re.search(r'(?:哪|哪些)\s*([0-9]+|[一二三四五六七八九十]+)\s*(?:个|项|条|步|章|章节|维度|方面)', clean)
    if expected:
        from app.verified_answer_engine_v2 import _explicit_list_item_count
        count = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}.get(expected[1], int(expected[1]) if expected[1].isdigit() else 0)
        if count and _explicit_list_item_count(text, question=clean) < count:
            return '正文尚未支持问题要求的完整条目数量。'
    if any(word in clean for word in ('多少', '几次', '几项', '几条', '几个', '何时', '日期', '时间')) and not re.search(r'\d|[一二三四五六七八九十百千万]+(?:元|项|条|个|次|天|月|年)', body):
        return '正文没有提供所问的数值或日期。'
    unit = re.search(r'(?:多少|几)\s*(天|日|次|项|条|个|年|月|万元|亿元|元|平方米|米)', clean)
    if unit and not re.search(r'(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)'+re.escape(unit[1]), body):
        return '正文没有提供所问单位的数值，其他数字不能代替。'
    return ''


def design_deliverable_excerpt(text: str, stage: str, question: str = '') -> str:
    match = re.search(re.escape(stage) + r'阶段提交的成果要求[^：:\n]*[：:]\s*([\s\S]+)', text)
    if not match:
        return ''
    excerpt = re.split(r'\n(?:第[一二三四五六七八九十]+章|3\.[1-9])', match[1], maxsplit=1)[0].strip()
    if re.search(r'经济(?:文件|成果)', question):
        excerpt = '\n'.join(line for line in excerpt.splitlines() if re.search(r'估算书|概算书|预算书', line))
    return excerpt if re.search(r'图|说明|模型|计算书|估算书|概算书|预算书|电子版文件', excerpt) else ''


@lru_cache(maxsize=256)
def source_statement_reviews(question: str) -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parents[2] / 'source_review_notes.json'
    if not path.is_file():
        return ()
    issues = json.loads(path.read_text(encoding='utf-8'))['issues']
    return tuple(issue for issue in issues if any(term in question for term in issue['topic_terms']) and any(term in question for term in issue['property_terms']))


COMMON_TERMS = {
    "设计",
    "项目",
    "管理",
    "问题",
    "哪些",
    "什么",
    "如何",
    "需要",
    "可以",
    "进行",
    "要求",
    "内容",
    "多少",
    "分别",
    "其中",
}


def search_atomic_evidence(
    query: str, records: Iterable[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    records = list(records)
    terms = query_terms(query)
    if not terms:
        return []
    token_sets = []
    query_phrases = phrases(query)
    for record in records:
        searchable = " ".join(str(record.get(field) or "") for field in ("search_context", "text", "heading_path", "file_name", "source_path"))
        token_sets.append((searchable, set(_tokenize_cached(searchable))))
    document_frequency = {
        term: sum(term in tokens or (len(term) >= 3 and term in searchable) for searchable, tokens in token_sets)
        for term in terms
    }
    total_records = max(1, len(records))
    facets = query_facets(query)
    results: list[dict[str, Any]] = []
    for record, (searchable, record_terms) in zip(records, token_sets, strict=True):
        matched = sorted(
            {
                term
                for term in terms
                if term in record_terms or (len(term) >= 3 and term in searchable)
            },
            key=len,
            reverse=True,
        )
        if not matched:
            continue
        score = sum(math.log((total_records + 1) / (document_frequency[term] + 1)) + 1 for term in matched)
        identity_text = " ".join(str(record.get(field) or "") for field in ("file_name", "heading_path", "source_path"))
        identity_matches = [term for term in matched if term in identity_text]
        score += sum(math.log((total_records + 1) / (document_frequency[term] + 1)) for term in identity_matches)
        if query.strip() and query.strip().lower() in searchable.lower():
            score += 20
        record_text = str(record.get("text") or "")
        phrase_matches = [phrase for phrase in query_phrases if phrase.lower() in record_text.lower()]
        score += sum(2.0 for phrase in phrase_matches)
        if record_text.startswith("#"):
            score -= 5.0
        if record.get("file_type") == ".md" and any(marker in record_text for marker in ("file://", "[[")):
            score -= 4.0
        if len(record_text) >= 24 and not record_text.startswith("#"):
            score += 0.5
        normalized_searchable = _compact(searchable)
        normalized_text = _compact(record_text)
        year_matches = [year for year in facets["years"] if year in normalized_searchable]
        metric_matches = [term for term in facets["metrics"] if term in normalized_searchable]
        text_metric_matches = [term for term in facets["metrics"] if term in normalized_text]
        entity_matches = _maximal_matches(facets["entities"], identity_text)
        text_entity_matches = _maximal_matches(facets["entities"], record_text)
        cell_headers = " ".join(str(cell.get("header") or "") for cell in record.get("cells", []))
        field_matches = _maximal_matches(facets["fields"], f"{record_text} {cell_headers}")
        if facets["years"]:
            score += 3.0 * len(year_matches) - 2.0 * (len(facets["years"]) - len(year_matches))
        score += 1.5 * len(metric_matches)
        score += 2.0 * len(text_metric_matches)
        score += 2.0 * len(field_matches)
        score += 2.5 * len(entity_matches)
        score += 3.0 * len(text_entity_matches)
        if facets["metrics"] and not (metric_matches or text_metric_matches):
            score -= 1.5 * len(facets["metrics"])
        if facets["fields"] and not field_matches:
            score -= 1.5 * len(facets["fields"])
        results.append(
            {
                "score": round(score, 6),
                "matched_terms": matched,
                "identity_match_terms": [term for term in identity_matches if not term.isdigit()],
                "phrase_matches": phrase_matches,
                "year_matches": year_matches,
                "metric_matches": metric_matches,
                "text_metric_matches": text_metric_matches,
                "entity_matches": entity_matches,
                "text_entity_matches": text_entity_matches,
                "field_matches": field_matches,
                "facet_reasons": _facet_reasons(
                    facets,
                    year_matches,
                    metric_matches,
                    text_metric_matches,
                    entity_matches,
                    text_entity_matches,
                    field_matches,
                ),
                "record": record,
            }
        )
    return sorted(
        results,
        key=lambda item: (-item["score"], str(item["record"].get("evidence_id") or "")),
    )[:limit]


def query_terms(query: str) -> list[str]:
    return list(
        dict.fromkeys(
            term.lower()
            for term in tokenize(query)
            if len(term.strip()) > 1 and term.strip() not in COMMON_TERMS
        )
    )


def scoring_target_phrase(query: str) -> str | None:
    from app.retrieval.query_planner_v1 import fact_request
    query = fact_request(query)
    standard = re.fullmatch(r'(?:分公司|公司|项目)?(.{2,32}?)(?:的)?(?:标准分值|标准分)(?:是多少|为多少|是几分|多少分|是什么)[？?]?', query)
    if standard:
        return standard[1].removesuffix('的')
    if not any(marker in query for marker in ("评分", "扣分", "得分", "扣几分", "扣多少分")):
        return None
    match = re.search(
        r"(?:关于|针对|围绕|就)\s*([^，,。；;：:？?！!]{2,32}?)\s*(?:的)?(?:评分标准|评分办法|评分规则|扣分标准|得分标准|扣几分|扣多少分)",
        query,
    )
    if match:
        target = match.group(1).strip().removeprefix("关于").strip(" 的")
        return re.sub(r"[\s（）()《》〈〉“”\"'「」『』]", "", target) or None
    quoted = re.search(r"[《〈“\"「『]([^》〉”\"」』]{2,40})[》〉”\"」』]", query)
    return re.sub(r"\s+", "", quoted.group(1)) if quoted else None


def phrases(query: str) -> list[str]:
    tokens = [term for term in tokenize(query) if len(term.strip()) > 1 and term.strip() not in COMMON_TERMS]
    phrases = [term for term in tokens if len(term) >= 3]
    phrases.extend(
        tokens[index] + tokens[index + 1]
        for index in range(len(tokens) - 1)
        if len(tokens[index]) + len(tokens[index + 1]) >= 4
        and not tokens[index].isascii()
        and not tokens[index + 1].isascii()
    )
    return list(dict.fromkeys(phrases))


def query_facets(query: str) -> dict[str, list[str]]:
    years = list(dict.fromkeys(re.findall(r"20\d{2}", query)))
    metrics = [
        term
        for term in (
            "工期",
            "金额",
            "多少天",
            "数量",
            "专业",
            "效益",
            "创效",
            "利润",
            "比选",
            "方案",
            "督办",
            "责任状",
            "示范项目",
        )
        if term in query
    ]
    fields = [
        term
        for term in (
            "工期",
            "总工期",
            "设计工期",
            "金额",
            "创效金额",
            "利润",
            "数量",
            "上传数量",
            "专业",
            "方案",
            "比选",
            "督办",
            "责任状",
            "示范项目",
        )
        if term in query
    ]
    entities = []
    entity_pattern = re.compile(
        r"([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,32}(?:项目|中心|医院|馆|园|厂房|学校))"
    )
    for match in entity_pattern.finditer(query):
        candidate = match.group(1).strip("（）() ")
        candidate = re.sub(r"^20\d{2}年", "", candidate)
        if not candidate:
            continue
        if candidate.endswith("的") or candidate.startswith(("设计", "示范", "当前", "具体")):
            continue
        if candidate in {"项目", "设计中心", "公司中心"}:
            continue
        entities.append(candidate)
    return {
        "years": years,
        "metrics": list(dict.fromkeys(metrics)),
        "fields": list(dict.fromkeys(fields)),
        "entities": list(dict.fromkeys(entities)),
    }


def _maximal_matches(candidates: list[str], text: str) -> list[str]:
    matched = [candidate for candidate in candidates if candidate and candidate in text]
    selected: list[str] = []
    for candidate in sorted(set(matched), key=len, reverse=True):
        if not any(candidate in existing for existing in selected):
            selected.append(candidate)
    return selected


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _facet_reasons(
    facets: dict[str, list[str]],
    year_matches: list[str],
    metric_matches: list[str],
    text_metric_matches: list[str],
    entity_matches: list[str],
    text_entity_matches: list[str],
    field_matches: list[str],
) -> list[str]:
    reasons = []
    if year_matches:
        reasons.append("year_match")
    elif facets["years"]:
        reasons.append("year_missing")
    if metric_matches:
        reasons.append("metric_match")
    if text_metric_matches:
        reasons.append("metric_in_text")
    if entity_matches:
        reasons.append("entity_in_identity")
    if text_entity_matches:
        reasons.append("entity_in_text")
    if field_matches:
        reasons.append("field_match")
    return reasons


@lru_cache(maxsize=50_000)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    return tuple(tokenize(text))


def design_depth_excerpt(text: str, stage: str, source_name: str = '') -> str:
    names = re.findall(r'方案设计|初步设计|施工图设计', source_name)
    if names and (len(set(names)) != 1 or stage not in names) or not names and stage not in text:
        return ''
    match = re.search(r'2\.3\.1\s*设计深度要求\s*([\s\S]+?)(?=2\.3\.2|第三章|$)', text)
    if not match:
        return ''
    excerpt = match[1].strip()
    return excerpt if re.search(r'根据|满足|符合|要求|应|须|执行', excerpt) and not re.fullmatch(r'[（(]?待(?:补充|填写|明确)[）)]?[。.]?', excerpt) else ''


def actual_execution_request(question: str) -> bool:
    if re.search(r'原件|原表|原文|表中|表里|文件记载|资料记载|示范文本|应该|应当|必须|方可|才能|前提|(?:要求|规定)(?:是否|须|应|先)|(?:如何|怎么|怎样)(?:检查|核查|核实|判断)', question):
        return False
    return bool(re.search(r'是否(?:已经|已|实际)|是否.*已经|有没有.*(?:完成|开展)|实际完成情况', question)
                and re.search(r'检查|整改|执行|落实|完成|验收|上传|入图|报审|开展|考核', question))


def historical_case_scope_gap(question: str, plan: dict[str, Any]) -> str:
    """A dated case records what its author wrote, not live progress or general rules."""
    literal = bool(re.search(r'原报告|原文|原件|原表|报告(?:记载|记录|所述|当时|中的|中)|当时|截至\s*20\d{2}', question))
    if not literal and (actual_execution_request(question) or re.search(r'现在|目前|当前|最新|至今|已经.*(?:整改|验收|闭环|完成)|是否.*(?:整改完|通过验收)', question)):
        return '历史评估报告不能证明当前工程状态或整改完成；需要对应日期的实施、整改回复及复核证据。'
    if re.search(r'所有项目|其他项目|一律|都必须|通用要求|现行规范|现行要求', question):
        return '项目案例不能代替其他项目的输入资料或现行通用要求。'
    if not plan.get('project') and not (plan.get('scope_constraints') or {}).get('source_reference'):
        return '未明确该案例范围，不能用单个项目的评估记录回答通用问题。'
    return ''


def assessment_value_parts(question: str, text: str) -> list[str] | None:
    """Read the requested assessment value from its own column and professional row."""
    attributes = [a for a in ('完整度', '深度') if a in question]
    if not attributes or not re.search(r'是多少|为多少|几分|分数|评分|百分之几', question):
        return None
    professionals = [p for p in ('建筑','结构','暖通','给排水','道路','电气','总平') if p in question]
    systems = [p for p in ('集电线路','风电场','升压站') if p in question]
    table = re.search(r'表头：([^\n]+)\n行：([\s\S]+)',text)
    if table:
        headers=[s.strip() for s in table[1].split('|')]; values=[s.strip() for s in table[2].split('|')]
        if len(headers)!=len(values):return []
        if not any(h=='专业' for h in headers):return []
        identities=[v for h,v in zip(headers,values) if h in {'专业','序号'}]
        if professionals and not all(any(p in v for v in identities) for p in professionals):return []
        if systems and not all(any(p in v for v in identities) for p in systems):return []
        if not professionals and not systems and not any(v=='合计' for v in values):return []
        labels=list(dict.fromkeys(v for h,v in zip(headers,values) if h=='专业' and v and v!='合计'))
        label='／'.join(labels) or '总体'
        result=[]
        for attribute in attributes:
            matches=[v for h,v in zip(headers,values) if re.fullmatch(re.escape(attribute)+r'[（(]%[）)]',h) and re.fullmatch(r'\d+(?:\.\d+)?%?',v)]
            if len(matches)!=1:return []
            result.append(label+attribute+'：'+matches[0].rstrip('%')+'%。')
        return result
    result=[]
    for attribute in attributes:
        prefix='[／/、的 ]*'.join(re.escape(p) for p in [*professionals,*systems])
        match=re.search(prefix+r'(?:专业)?'+re.escape(attribute)+r'(?:为|是|[：:])\s*(\d+(?:\.\d+)?%)',text)
        if not match:return []
        result.append(('／'.join([*professionals,*systems]) or '总体')+attribute+'：'+match[1]+'。')
    return result
