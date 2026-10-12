"""Source-bound comparison preparation; unknown inputs remain gaps, never winners."""
import copy
import hashlib
import re
from decimal import Decimal

COMMON_FIELDS={'scope':'比较对象和同一工作范围','requirements':'本次功能要求与硬约束','cost_scope':'两方案成本包括的相同费用范围','cost_basis':'同数量、价格时点及税费口径说明','duration_scope':'两方案施工用时的相同范围和前置条件'}
OPTION_FIELDS={'name':'本次方案名称','technical':'技术条件及可行性说明','construction':'施工条件与配合要求','operations':'运行维护影响','risk':'风险与待确认事项','cost':'成本金额（非负，仅填数字）','cost_unit':'成本单位','cost_evidence':'本方案成本依据及版本','duration_days':'本方案施工用时（天，非负）','duration_evidence':'本方案用时依据及版本','constraint_status':'硬约束情况'}


def comparison_topics(case):
    specs=case.get('comparison_topic_specs') or []
    if not specs:raise ValueError('本项目尚未配置经原文核对的比选议题。')
    version=case['source']['source_version']
    items={i['item_id']:i for i in case['items']};topics=[]
    for spec in specs:
        item_id,subject,a,b=(spec[k] for k in ('source_item_id','subject','baseline_reference','candidate_reference'))
        item=items.get(item_id)
        if not item or b not in item['quote'] or a and a not in item['quote']:
            raise ValueError('比选议题与同版原文未能对应。')
        topics.append({'topic_id':'SC-'+hashlib.sha256((version+'|'+item_id+'|'+subject).encode()).hexdigest()[:20],
                       'subject':subject,'source_item_id':item_id,'professional':item['professional'],'quote':item['quote'],
                       'anchors':copy.deepcopy(item['anchors']),'baseline_reference':a,'candidate_reference':b,
                       'condition':'如需降低造价' if item['quote'].startswith('如需降低造价') else '原报告建议，是否适用本次工作另行确定'})
    routed={t['source_item_id'] for t in topics}
    return {'project_id':case['project_id'],'project':case['project'],'source':copy.deepcopy(case['source']),'topics':topics,
            'separate_checks':[copy.deepcopy(i) for i in case['items'] if i.get('gap_type')=='TECHNICAL_REVIEW' and i['item_id'] not in routed],
            'common_fields':[{'id':k,'label':v} for k,v in COMMON_FIELDS.items()],
            'option_fields':[{'id':k,'label':v} for k,v in OPTION_FIELDS.items()],
            'scope_note':'议题来自本项目已核对的原文映射。不同对象分别讨论；其他技术核对事项不强行改成可选方案。原报告建议不等于本次已采用方案。'}


def _number(value,label):
    if value=='':return None
    if not re.fullmatch(r'\d{1,14}(?:\.\d{1,4})?',value):
        raise ValueError(label+'请填写非负普通数字，最多14位整数、4位小数；未知时留空。')
    return Decimal(value)


def _text_inputs(values,allowed):
    if set(values)-set(allowed) or any(not isinstance(v,str) or len(v)>2000 for v in values.values()):
        raise ValueError('填写字段不正确或内容过长。')
    return {k:v.strip() for k,v in values.items() if v.strip()}


def build_comparison(case,source_version,topic_id,common,options):
    if source_version!=case['source']['source_version']:raise ValueError('原件版本不一致，请刷新核对。')
    prepared=comparison_topics(case);topic=next((t for t in prepared['topics'] if t['topic_id']==topic_id),None)
    if not topic:raise ValueError('议题不属于本项目、本版资料。')
    if len(options)!=2:raise ValueError('本次请分别填写方案A和方案B。')
    common=_text_inputs(common,COMMON_FIELDS);options=[_text_inputs(o,OPTION_FIELDS) for o in options]
    gaps=[COMMON_FIELDS[k]+'缺项' for k in COMMON_FIELDS if not common.get(k)]
    costs=[];days=[];eligibility=[]
    for index,option in enumerate(options):
        label='方案'+('A','B')[index]
        unit=option.get('cost_unit','');state=option.get('constraint_status','待核对')
        if unit not in {'','元','万元'}:raise ValueError('成本单位请选择元或万元，不混用其他计量单位。')
        if state not in {'待核对','满足','不满足'}:raise ValueError('硬约束情况请选待核对、满足或不满足。')
        costs.append(_number(option.get('cost',''),label+'成本金额'))
        days.append(_number(option.get('duration_days',''),label+'施工用时'))
        gaps.extend(label+'：'+OPTION_FIELDS[k]+'缺项' for k in OPTION_FIELDS if not option.get(k) or k=='constraint_status' and state=='待核对')
        eligibility.append('填写记录为不满足硬约束，不进入推荐范围' if state=='不满足' else '功能与硬约束缺项，暂不能判断' if not common.get('requirements') or state=='待核对' else '用户填写满足，仍属准备记录，未实际核准')
    comparable_cost=all(k in common for k in ['scope','cost_scope','cost_basis']) and all(c is not None for c in costs) and all(o.get('cost_unit') and o.get('cost_evidence') for o in options)
    cost_result={'status':'MISSING_INPUT','summary':'成本或比较口径缺项，暂不计算节省额。'}
    if comparable_cost:
        amounts=[n*(Decimal('10000') if o['cost_unit']=='万元' else Decimal('1')) for n,o in zip(costs,options)]
        difference=amounts[1]-amounts[0]
        cost_result={'status':'INPUT_CALCULATION_ONLY','amounts_yuan':[format(n,'f') for n in amounts],'B_minus_A_yuan':format(difference,'f'),
                     'summary':'按填写的同一口径，方案B比方案A'+('少'+format(-difference,'f')+'元' if difference<0 else '多'+format(difference,'f')+'元' if difference>0 else '成本金额相同')+'；只比较已填成本，不代表总体优选。'}
    comparable_time=common.get('scope') and common.get('duration_scope') and all(d is not None for d in days) and all(o.get('duration_evidence') for o in options)
    time_result={'status':'MISSING_INPUT','summary':'施工用时或比较口径缺项，暂不判断缩短多少天。'}
    if comparable_time:
        difference=days[1]-days[0]
        time_result={'status':'INPUT_CALCULATION_ONLY','B_minus_A_days':format(difference,'f'),
                     'summary':'按填写的同一范围，方案B比方案A'+('少'+format(-difference,'f')+'天' if difference<0 else '多'+format(difference,'f')+'天' if difference>0 else '施工用时相同')+'；不自动等同于总工期变化。'}
    return {'project_id':prepared['project_id'],'project':prepared['project'],'source':prepared['source'],'topic':copy.deepcopy(topic),
            'common':common,'options':copy.deepcopy(options),'gaps':gaps,'eligibility':eligibility,'cost_comparison':cost_result,'time_comparison':time_result,
            'status':'COMPARISON_PREPARATION_WITH_GAPS' if gaps else 'INPUT_COMPARISON_PENDING_REVIEW',
            'recommended_option':None,'owner_approved':False,'ready_for_issue':False,'knowledge_published':False,'source_writeback':False}


def render_comparison(draft):
    title=draft['project']+' · '+draft['topic']['subject'];topic=draft['topic']
    warning='准备稿，未审批、未选定方案。缺资料先登记缺项，不要求先考证历史报告正确性；原报告建议不是当前已核准方案。'
    def cell(value):return (value or '[缺项，待补]').replace('|','｜').replace('\n',' / ')
    main=['# '+title+' · 比选准备','',warning,'','原报告记载：'+topic['quote'],'','原文条件：'+topic['condition'],'',
          '原报告提及的基准参考：'+(topic['baseline_reference'] or '[当前绑定条目未给出基准方案，不猜填]'),'','原报告候选参考：'+topic['candidate_reference'],'']
    main.extend(COMMON_FIELDS[k]+'：'+draft['common'].get(k,'[缺项，待补]') for k in COMMON_FIELDS)
    main.extend(['','## 已填数字的同口径比较','',draft['cost_comparison']['summary'],'',draft['time_comparison']['summary'],'',
                 '总体方案未选定。费用、用时差额不代替功能、硬约束、技术、施工、运维和风险的综合判断。',''])
    table=['# '+title+' · 两方案对照','',warning,'','| 比较事项 | 方案A | 方案B |','| --- | --- | --- |']
    table.extend('| '+label+' | '+cell(draft['options'][0].get(k,''))+' | '+cell(draft['options'][1].get(k,''))+' |' for k,label in OPTION_FIELDS.items())
    table.extend(['','硬约束记录：','',*['方案'+('A','B')[i]+'：'+text for i,text in enumerate(draft['eligibility'])],
                  '',draft['cost_comparison']['summary'],'',draft['time_comparison']['summary'],''])
    gaps=['# '+title+' · 比选准备缺项清单','',warning,'','以下为本次未填写或未明确的比选输入，不据此认定原报告或实际设计不存在相关内容。','']
    gaps.extend('- '+g for g in draft['gaps']);gaps.extend(['','缺项可以后补，暂不指定责任人、完成日期或强制安排立即论证。',''])
    evidence=['# '+title+' · 来源与条件','','原件：'+draft['source']['file_name'],'来源版本：'+draft['source']['source_version'],
              '原报告时点：'+draft['source']['observation_date'],'关联评估事项编号：'+topic['source_item_id'],'比选议题编号：'+topic['topic_id'],'',
              '原文：'+topic['quote'],'','原文条件：'+topic['condition'],'','原文中的数字不自动当作成本、报价、施工用时或实施完成情况。','']
    for a in topic['anchors']:evidence.extend(['原件第'+str(a['table'])+'表第'+str(a['row'])+'行（'+a['table_title']+'）','','完整源行问题栏：'+a['source_row_text'],''])
    return {'比选准备.md':'\n'.join(main),'两方案对照表.md':'\n'.join(table),'缺项清单.md':'\n'.join(gaps),'来源与条件.md':'\n'.join(evidence)}
