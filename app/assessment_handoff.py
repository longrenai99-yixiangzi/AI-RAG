"""Prepare project tasks from dated source rows without approving or dispatching them."""
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from app.taskbook_drafting import FIELDS

INPUT_FIELDS = {
    'current_basis':'本次核对依据及版本', 'stage':'本次拟委托或设计阶段', 'taskbook_text':'拟补入任务书的内容',
    'deliverable':'拟交付成果及核对办法', 'owner':'拟责任人',
    'start_date':'拟开始日期', 'due_date':'拟完成日期',
    'predecessor':'前置资料或任务', 'response_evidence':'回复资料及版本', 'review_note':'复核意见',
}


def make_case(parsed, source_version, project_id, project):
    doc=parsed['documents'][0]
    if doc['content_hash']!=source_version or not doc.get('observation_date'):
        raise ValueError('报告版本或资料时点未核对。')
    if project not in ((doc.get('document_profile') or {}).get('project') or {}).get('value',[]):
        raise ValueError('报告项目与本次准备项目不一致。')
    # shortcut: supports the reviewed three-table report layout; validate a new layout before adding another template.
    tables={t['table_id']:t for t in parsed['tables'] if t['source_location']['table'] in {3,4,5}}
    if len(tables)!=3:raise ValueError('已核读的汇总表不齐。')
    rows=[];items={}
    for row in parsed['table_rows']:
        table=tables.get(row['table_id'])
        if not table or not 2<=row['row_number']<=10:continue
        number=table['source_location']['table'];values=row['values'];professional='—'.join(dict.fromkeys(v for h,v in zip(table['header'],values) if h=='专业' and v))
        text=values[table['header'].index('主要问题')]
        dimension={3:'完整度',4:'设计深度',5:'技术可行性'}[number]
        location={'table':number,'row':row['row_number'],'body_order':table['source_location']['body_order'],'table_title':table['table_title']}
        rows.append({'dimension':dimension,'professional':professional,'text':text,'values':copy.deepcopy(values),'location':location})
        for part in re.finditer(r'[^；;]+(?:[；;]|$)',text):
            quote=part[0].strip(' \t\r\n；;')
            if not quote:continue
            key=professional+'|'+re.sub(r'\s+','',quote).rstrip('。')
            item_id='AT-'+hashlib.sha256((source_version+'|'+key).encode()).hexdigest()[:20]
            kind='未评范围待补评' if '未评估' in quote else '技术问题或建议待复核' if number==5 else '资料与设计问题待复核'
            item=items.setdefault(item_id,{'item_id':item_id,'professional':professional,'quote':quote,'kind':kind,'dimensions':[],'anchors':[]})
            if dimension not in item['dimensions']:item['dimensions'].append(dimension)
            start=text.find(quote,part.start(),part.end())
            item['anchors'].append({**location,'dimension':dimension,'source_row_id':row['table_row_id'],'source_row_text':text,
                                    'quote':quote,'char_start':start,'char_end':start+len(quote)})
    if len(rows)!=27:raise ValueError('27条源行未能完整对应。')
    by_field={r[0]:{'field':r[0],'chapter':r[1],'label':r[2]} for r in FIELDS}
    for item in items.values():
        quote=item['quote']
        if item['kind']=='未评范围待补评':
            keys=['scope','basis','schedule'];action='先核对本次资料与人员条件，明确补评范围和安排；补评结果另行复核。'
        elif '技术可行性' in item['dimensions']:
            keys=['technical','limits'];action='先核对合同、图纸和适用依据；涉及方案调整时，先做技术、成本及工期论证，复核后决定是否采用。'
        else:
            keys=['scope','coordination'] if re.search(r'界面|接口|分工',quote) else ['basis','technical'] if re.search(r'地勘|勘察|依据|资料',quote) else ['deliverables','technical']
            action='先核对当前资料是否仍存在该项问题；确认适用后再明确补充成果、任务要求和复核办法。'
        item.update(taskbook_routes=[by_field[k] for k in keys],suggested_action=action,review_status='HISTORICAL_RECORD_PENDING_CURRENT_REVIEW')
    return {'project_id':project_id,'project':project,'source':{'source_path':doc['source_path'],'file_name':doc['file_name'],'source_version':source_version,'observation_date':doc['observation_date']},
            'scope_note':'仅整理已核对版本3.1、3.2、3.3三张汇总表的27条源行；不代表全报告附表的问题已列全。相同专业、相同原文合并展示并保留全部出处，近似表述不自动合并。',
            'source_rows':rows,'items':list(items.values()),'input_fields':[{'id':k,'label':v} for k,v in INPUT_FIELDS.items()]}


def gap_type(quote):
    if not quote.strip():return 'REPORT_CONTENT_GAP','报告未说明，按报告缺项登记'
    if '未评估' in quote:return 'ASSESSMENT_GAP','评估缺项（未评）'
    if not quote.startswith('如需') and re.search(r'缺|不全|未表达|未说明|未提及|不明确|^无.*(?:报告|表)|补充',quote):
        return 'SOURCE_REPORTED_GAP','报告列示待补项'
    return 'TECHNICAL_REVIEW','技术问题或建议，另行处理'


def apply_gap_policy(case,receipt):
    if receipt['source_version']!=case['source']['source_version'] or receipt['project_id']!=case['project_id']:
        raise ValueError('缺项处理口径与项目或版本不一致。')
    result=copy.deepcopy(case);result['gap_policy']=copy.deepcopy(receipt)
    for item in result['items']:
        kind,label=gap_type(item['quote']);item.update(gap_type=kind,gap_label=label)
        if kind=='ASSESSMENT_GAP':
            item['suggested_action']='先登记评估缺项，后续按资料和人员条件安排补评；不影响其他缺项先行整理。'
        elif kind in {'SOURCE_REPORTED_GAP','REPORT_CONTENT_GAP'}:
            item['suggested_action']='按缺项直接列入补齐清单，写明需要补充的资料或成果；不以考证历史报告正确性为前置条件。'
        if kind!='TECHNICAL_REVIEW':item['review_status']='GAP_REGISTERED_UNDER_OWNER_WORKING_POLICY'
    result['scope_note']+=' 已按用户确认口径，缺内容先按缺项登记，不要求先逐项考证历史报告正确性；缺项记录不等于实际设计缺陷。'
    for field in result['input_fields']:
        if field['id']=='current_basis':field['label']='补充资料或线索（有则填）'
    return result


def load_case(root: Path, project_id: str, navigation: dict):
    path=root/'assessment_handoff.json'
    manifest=json.loads((root.parent/'PACKAGE_MANIFEST_PRIVATE.json').read_text(encoding='utf-8'))
    expected=next((r['sha256'] for r in manifest['files'] if r['path']=='runtime/assessment_handoff.json'),None)
    if not path.is_file() or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('任务准备资料版本校验未通过。')
    case=json.loads(path.read_text(encoding='utf-8'));source=case['source']
    project=next((p for p in navigation['projects'] if p['id']==project_id),None)
    if not project or case['project_id']!=project_id or not any(s['source_version']==source['source_version'] and s['source_path'].replace('/','\\').casefold()==source['source_path'].replace('/','\\').casefold() for s in project['sources']):
        raise ValueError('本项目尚未绑定同版评估任务准备资料，不能借用其他项目。')
    catalog=json.loads((root/'frozen_sources/catalog.json').read_text(encoding='utf-8'))['records']
    ref=next((r for r in catalog.values() if r.get('source_version')==source['source_version'] and r.get('source_path','').replace('/','\\').casefold()==source['source_path'].replace('/','\\').casefold()),None)
    if not ref:raise ValueError('本项目评估原件未登记。')
    original=(root/ref['frozen_path']).resolve()
    if not original.is_relative_to(root/'frozen_sources') or not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest()!=source['source_version']:
        raise ValueError('评估原件版本已变化，不能生成任务准备稿。')
    return case


def build_handoff(case, source_version, selected_ids, updates):
    if source_version!=case['source']['source_version']:raise ValueError('所选评估版本不一致，请刷新核对。')
    items={r['item_id']:r for r in case['items']}
    if not selected_ids or len(selected_ids)>200 or len(set(selected_ids))!=len(selected_ids) or set(selected_ids)-items.keys():
        raise ValueError('请选择本项目的有效事项，不得重复或混用其他版本。')
    if set(updates)-set(selected_ids):raise ValueError('补充内容必须对应本次勾选事项。')
    result=[]
    for item_id in selected_ids:
        notes=updates.get(item_id,{})
        if set(notes)-INPUT_FIELDS.keys() or any(not isinstance(v,str) or len(v)>2000 for v in notes.values()):
            raise ValueError('补充字段不正确或内容过长。')
        notes={k:v.strip() for k,v in notes.items() if v.strip()}
        for key in ['start_date','due_date']:
            if notes.get(key):
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',notes[key]):raise ValueError('日期请填写为年-月-日。')
                try:date.fromisoformat(notes[key])
                except ValueError as error:raise ValueError('日期不存在，请重新核对。') from error
        if notes.get('start_date') and notes.get('due_date') and notes['start_date']>notes['due_date']:
            raise ValueError('拟完成日期不能早于拟开始日期。')
        item=copy.deepcopy(items[item_id]);item['current_inputs']=notes;item['current_status']='DRAFT_PENDING_REVIEW'
        result.append(item)
    return {'project_id':case['project_id'],'project':case['project'],'source':copy.deepcopy(case['source']),'scope_note':case['scope_note'],'items':result,
            'gap_policy':copy.deepcopy(case.get('gap_policy')), 'status':'DRAFT_PENDING_REVIEW','owner_approved':False,'ready_for_issue':False,'task_dispatched':False,'knowledge_published':False,'source_writeback':False}


def render_handoff(draft):
    heading='# '+draft['project']+' · '
    warning='**准备稿，待复核、未审签、未下发。** 原报告截至'+draft['source']['observation_date']+'；历史问题未自动成为当前缺陷，填写与生成不代表审批、派发或整改完成。'
    if draft.get('gap_policy'):warning+=' 缺内容按缺项先行登记，不要求先考证历史报告正确性；资料缺项不直接等于实际设计缺陷。'
    task=[heading+'评估问题任务准备','',warning,'',draft['scope_note'],'']
    book=[heading+'任务书补充事项','',warning,'','以下是待讨论的补充事项，不是完整任务书，也未替换已批准的任务书。','']
    plan=[heading+'设计计划准备表','',warning,'','日期、责任和前置条件均按本次填写保留；未填写时不自动估工期或安排节点。','']
    evidence=[heading+'来源核对表','','原件：'+draft['source']['file_name'],'版本：'+draft['source']['source_version'],'资料时点：'+draft['source']['observation_date'],'',draft['scope_note'],'']
    for item in draft['items']:
        title=item['professional']+' · '+item.get('gap_label',item['kind']);notes=item['current_inputs']
        task.extend(['## '+title,'','编号：'+item['item_id'],'','原报告记载：'+item['quote'],'','建议的准备动作：'+item['suggested_action'],''])
        task.extend([INPUT_FIELDS[k]+'：'+notes.get(k,'[待填写]') for k in INPUT_FIELDS]);task.append('')
        book.extend(['## '+title,'','关联编号：'+item['item_id'],'','原报告记载：'+item['quote'],'','建议归入（待核对）：'+'；'.join(r['chapter']+'／'+r['label'] for r in item['taskbook_routes']),
                     '', '本次依据：'+notes.get('current_basis','[待核对]'),'','本次拟委托或设计阶段：'+notes.get('stage','[待明确]'),'','拟补入内容：'+notes.get('taskbook_text','[按缺项拟定补充资料、成果与要求]' if draft.get('gap_policy') else '[先核对是否仍适用，再明确本次要求]'),'','拟交付成果：'+notes.get('deliverable','[待明确]'),''])
        plan.extend(['## '+title,'','关联编号：'+item['item_id'],'','待核事项：'+item['quote'],'','准备动作：'+item['suggested_action'],''])
        plan.extend([INPUT_FIELDS[k]+'：'+notes.get(k,'[待填写]') for k in ['stage','owner','start_date','due_date','predecessor','deliverable','response_evidence','review_note']]);plan.append('')
        evidence.extend(['## '+title,'','关联编号：'+item['item_id'],''])
        for anchor in item['anchors']:
            evidence.extend([anchor['dimension']+'：原件第'+str(anchor['table'])+'表第'+str(anchor['row'])+'行（'+anchor['table_title']+'）',
                             '', '对应原文：'+anchor['quote'],'','完整源行问题栏：'+anchor['source_row_text'],''])
    return {'评估问题任务准备.md':'\n'.join(task),'任务书补充事项.md':'\n'.join(book),'设计计划准备表.md':'\n'.join(plan),'来源核对表.md':'\n'.join(evidence)}
