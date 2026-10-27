"""Link explicitly reviewed contract modifications; never infer general contract precedence."""
import hashlib,json,re
from pathlib import Path
import pymupdf
from app.ingestion.pdf_paragraph_context import native_lines,paragraph_text,compact
from .named_source_scope import path_key
from .table_schema import PDF_READ_LOCK

RULES=Path(__file__).with_suffix('.json')


def requested_subitems(question):
    from app.retrieval.complete_lists import NUM,number
    return [number(v) for v in re.findall(r'第\s*[（(]?\s*('+NUM+r')\s*[）)]?\s*项',question)]


def reviewed_topic(question):
    task=re.sub(r'《.*?》','',question)
    return bool('5.2.1' in task or re.search(r'(?:承包人|设计)文件',task) and '审查' in task and re.search(r'期限|期满|时限|多少天|几天|起算|重新|异议|同意',task)
                or re.search(r'审查(?:期|时限).*?(?:文件|多少天|几天)|(?:期满|异议|审查).*?(?:视为|同意|默认|默示)',task))


def project_contract_selector(question,records):
    from .named_source_scope import named_titles
    if named_titles(question) or not reviewed_topic(question):return None
    for rule in json.loads(RULES.read_text(encoding='utf-8')):
        if rule['project_selector'] not in question:continue
        if not any(r['source_version']==rule['source_version'] and path_key(r['source_path'])==path_key(rule['source_path']) for r in records):continue
        return {'status':'REVIEWED_PROJECT_TOPIC_SOURCE_SELECTOR','question':'《'+Path(rule['source_path']).name+'》中，'+question,
            'original_question':question,'basis':'VERIFIED_PROJECT_TOPIC_AND_SOURCE_VERSION_NOT_CASE_FILENAME_ONLY'}
    return None


def project_conflict(question,rule):
    task=re.sub(r'《.*?》','',question)
    task=re.sub(r'(?:该|本|这个|上述|所述)项目','',task)
    projects=re.findall(r'([\u4e00-\u9fffA-Za-z0-9]{2,30})项目(?!经理|管理人员|部|团队)',task)
    return any(rule['project_selector'] not in name and name not in {'本次','该工程','本工程','这个','上述','所述','EPC','工程总承包','承包人','发包人'} for name in projects)


def context_bundle(question,records,*,source_scoped=False,cited_only=False):
    if requested_subitems(question):return None
    rules=json.loads(RULES.read_text(encoding='utf-8'))
    for rule in rules:
        admitted=[r for r in records if r['source_version']==rule['source_version'] and path_key(r['source_path'])==path_key(rule['source_path'])]
        if not admitted:continue
        task=re.sub(r'《.*?》','',question)
        topic=reviewed_topic(task)
        quoted=any(rule['deleted_quote'] in compact(r.get('text','')) for r in admitted if r.get('answer_usage')=='PRIMARY')
        explicit=source_scoped or rule['project_selector'] in task
        conflict=project_conflict(question,rule)
        if not (topic and explicit or cited_only and (quoted or topic)):continue
        path=Path(rule['source_path']);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=rule['source_version']:raise ValueError('Linked contract original changed')
        with PDF_READ_LOCK,pymupdf.open(stream=raw,filetype='pdf') as doc:
            assert compact(rule['project_name']) in compact(doc[rule['project_name_verified_page']-1].get_text())
            for unit in rule['units']:
                text,_=paragraph_text(native_lines(doc[unit['page']-1]),unit)
                if text!=unit['text']:raise ValueError('Linked contract unit changed')
        units={u['kind']:u for u in rule['units']}
        if (compact(units['GENERAL_DELETED']['text']).rstrip('。')!=rule['deleted_quote'] or
            '并删除' not in compact(units['SPECIAL']['text']) or rule['deleted_quote'] not in compact(units['SPECIAL']['text'])):
            raise ValueError('Reviewed contract deletion not verified')
        audit={'method':'VERSIONED_CONTRACT_MODIFICATION','issue_id':rule['issue_id'],'clause':rule['clause'],
               'project_name':rule['project_name'],'deleted_quote':rule['deleted_quote'],'legal_validity_determined':False}
        unsupported=bool(re.search(r'现行|最新|法律效力|生效|法定|所有项目|所有合同|(?:19|20)\d{2}年|赔偿|违约金|金额|能否调整|如何缩短|是否可以更改|合计|计算',task))
        message=('问句中的项目与本版招标文件所载项目未对应，本次未跨项目套用条款。' if conflict else
                 '请限定该项目这版招标文件的原文；本次未核定法定期限、现行效力、赔偿或其他项目的适用规则。' if unsupported else
                 '本次仅核对5.2.1的通用/专用条件修改关系，请限定审查期限、起算或默示同意表述，不把该条当成完整审查要求。' if not topic else
                 '当前引用来自示例实验中学片区提升项目的招标文件，请明确是否查询该项目本版文件，未将项目条款当作通用要求。' if not explicit else '')
        audit['clarification_message']=message
        binding={k:admitted[0][k] for k in ('document_id','source_id','document_role','authority_level','knowledge_root_id') if k in admitted[0]}
        cards=[]
        for unit in rule['units']:
            part='专用条件' if unit['kind']=='SPECIAL' else '通用条件（被删除原句，仅作对照）' if unit['kind']=='GENERAL_DELETED' else '通用条件（期限与起算）'
            cards.append({**binding,'source_path':str(path),'source_version':rule['source_version'],'file_name':path.name,
                'evidence_id':'contract-context-'+hashlib.sha256((rule['source_version']+unit['kind']+unit['text']).encode()).hexdigest(),
                'text':unit['text'],'role':'DIRECT','answer_usage':'BACKGROUND' if message else 'PRIMARY',
                'location':{'page':unit['page'],'bbox':unit['bbox']},
                'display_location':rule['project_name']+f' · PDF第{unit["page"]}页 · {part} · 5.2.1',
                'contract_clause_context':{'kind':unit['kind'],'clause':rule['clause'],'project_name':rule['project_name'],
                    'issue_id':rule['issue_id'],'deleted_quote':rule['deleted_quote'],'all_units_required':True}})
        return {'candidate_evidence':cards,'bundle_status':'SOURCE_SCOPE_MISSING' if message else 'PRIMARY_SECTION_CANDIDATE',
            'scope_mismatch_message':message,'contract_context_audit':audit}
    return None


def context_answer(result,question):
    primary=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
    linked=[c for c in primary if c.get('contract_clause_context')]
    if not linked:return None
    groups={(c['source_path'],c['source_version'],c['contract_clause_context']['issue_id']) for c in linked}
    by_kind={c['contract_clause_context']['kind']:c for c in linked}
    if len(groups)!=1 or len(primary)!=3 or set(by_kind)!={'DEADLINE','GENERAL_DELETED','SPECIAL'}:
        return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','answer':'本次未完整取得同版通用及专用修改依据，暂不单独引用通用条款答复。',
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in result.get('citations',[])],'generation_mode':'NO_GENERATION'}
    deadline_query=bool(re.search(r'期限|时限|起算|审查(?:需要|需|要|应在|不超过|为)?(?:多少天|几天|多久)',question))
    deletion_query=bool(re.search(r'默示|默认|视为|期满.*同意|专用.*(?:修改|调整|删除)|删除',question))
    other_subject=bool(re.search(r'不同意|未获同意|不予同意|通知谁|向谁|提前.*通知|全文|全部.*原文|原文.*全部',question))
    if other_subject or not (deadline_query or deletion_query):
        return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','answer':'本次仅核定审查期限、起算及默示同意的修改关系，尚不足以回答所问事项；未用已核小段代替整条全文或其他处置要求。',
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in result.get('citations',[])],'generation_mode':'NO_GENERATION'}
    special=by_kind['SPECIAL'];meta=special['contract_clause_context']
    answer=f'就《招标文件》所载{meta["project_name"]}而言，专用条件5.2.1明确删除了通用条件中的这句表述：“{meta["deleted_quote"]}”。[{special["citation_id"]}]'
    if deadline_query:
        deadline=by_kind['DEADLINE'];answer+='\n期限与起算的通用原文为：\n'+compact(deadline['excerpt'])+f' [{deadline["citation_id"]}]'
        answer+=f' 通用原句仅供修改前对照。[{by_kind["GENERAL_DELETED"]["citation_id"]}]'
    else:answer+=f' 通用原句仅供修改前对照。[{by_kind["GENERAL_DELETED"]["citation_id"]}]'
    return {**result,'answer_status':'SOURCE_EXTRACT','status_label':'同版条款修改对照 · 待业务核对','answer':answer,
        'generation_mode':'LINKED_CONTRACT_SOURCE_NO_MODEL','notice':'仅据所引招标文本核对原文修改关系，未判断合同生效或现行法律效力。'}


def paragraph_bundle(question,records,*,source_scoped):
    # shortcut: exact reviewed clause numbers only; implicit questions retain ordinary retrieval.
    codes=set(re.findall(r'(?<!\d)\d+\.\d+(?:\.\d+){0,2}(?![\d.])',question))
    if len(codes)!=1 or not source_scoped:return None
    code=next(iter(codes));rules=json.loads(RULES.read_text(encoding='utf-8'))
    from app.retrieval.complete_lists import NUM,number as ordinal
    requested_items=requested_subitems(question)
    if len(requested_items)>1:return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING','scope_mismatch_message':'本次已核单元按一个条款子项定位，请分项查询，未用其中一项代答多项。'}
    for rule in rules:
        matches=[r for r in records if r.get('paragraph_completion') and r['source_version']==rule['source_version'] and path_key(r['source_path'])==path_key(rule['source_path'])]
        if not matches:continue
        path=Path(rule['source_path']);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=rule['source_version']:raise ValueError('Reviewed clause source changed')
        selected={}
        with PDF_READ_LOCK,pymupdf.open(stream=raw,filetype='pdf') as doc:
            for section in rule['sections']:
                if section['title'] not in compact(doc[section['page']-1].get_text()):raise ValueError('Reviewed contract section changed')
            for r in matches:
                meta=r['paragraph_completion'];page=meta['page'];context=''
                if meta.get('segments'):
                    from app.ingestion.pdf_source_spans import span_paragraph
                    body,context=span_paragraph(doc,meta)
                else:body,_=paragraph_text(native_lines(doc[page-1]),meta)
                number=re.match(r'^(\d+\.\d+(?:\.\d+){0,2})(?![\d.])',body)
                exact_item=None
                if requested_items:
                    body_item=re.match(r'^[（(]\s*('+NUM+r')\s*[）)]',body)
                    if not meta.get('segments') or not body_item or ordinal(body_item[1])!=requested_items[0]:continue
                    parents=[m for m in re.finditer(r'(?m)^(\d+\.\d+(?:\.\d+){0,2})(?![\d.])',context) if m[1]==code]
                    if not parents:continue
                    number=parents[0];exact_item=requested_items[0]
                partial=meta.get('unit_scope')=='INTRO_WITH_EXPLICIT_MODIFICATION'
                linked=''
                if partial:
                    from app.ingestion.pdf_source_spans import read_span
                    headings=[read_span(doc,p) for p in meta.get('context_segments',[])]
                    number=re.match(r'^(\d+\.\d+(?:\.\d+){0,2})(?![\d.])',headings[0]) if headings else None
                    if not number or number[1]!=code:continue
                    linked=next((text for text in headings if compact('不执行通用合同条件'+code) in compact(text)), '')
                    if not linked:raise ValueError('Explicit same-clause modification missing')
                if not number or number[1]!=code:continue
                sections=[s for s in rule['sections'] if s['page']<=page]
                if not sections:
                    if meta.get('section_reference'):
                        from app.ingestion.pdf_source_spans import read_span
                        section={'title':compact(read_span(doc,meta['section_reference'])),'kind':'SOURCE_SECTION'}
                    elif exact_item is not None:
                        section={'title':'已核原文单元','kind':'SOURCE_SECTION'}
                    else:continue
                else:section=sections[-1]
                key=meta['paragraph_sha256']
                if hashlib.sha256(body.encode()).hexdigest()!=key:raise ValueError('Reviewed clause paragraph changed')
                selected[key]={**r,'text':(context+'\n' if context else '')+body,'evidence_id':'reviewed-clause-'+key,'role':'DIRECT','answer_usage':'PRIMARY',
                    'location':{'page':page,'bbox':meta['bbox'],**({'pages':sorted({p['page'] for p in meta['segments']+meta.get('context_segments',[])})} if meta.get('segments') else {})},
                    'display_location':r.get('display_location') if meta.get('segments') else rule['project_name']+f' · PDF第{page}页 · {section["title"]} · {code}',
                    'reviewed_contract_paragraph':{'clause':code,'section':section['title'],'kind':section['kind'],'project_name':rule['project_name'],**({'item':exact_item} if exact_item is not None else {}),**({'linked_modification':linked,'partial':True} if partial else {})}}
        if not selected:
            if requested_items:return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING','scope_mismatch_message':'本次已核原文单元尚未定位所问条款子项，请核对编号、类别或查阅原件；未用其他子项代答，也不据此认定原文没有该内容。'}
            return None
        asked=set()
        if '通用' in question:asked.add('GENERAL')
        if '专用' in question:asked.add('SPECIAL')
        rows=[r for r in selected.values() if not asked or r['reviewed_contract_paragraph']['kind'] in asked]
        valid=len(rows)==1 and len(asked)<=1 and not project_conflict(question,rule) and not re.search(r'现行|最新|法定|生效|效力|所有项目|合计|计算|对比|比较|(?:19|20)\d{2}年',question)
        if any(r['reviewed_contract_paragraph'].get('item') is not None and r['reviewed_contract_paragraph']['kind'] in {'GENERAL','SPECIAL'} for r in rows) and len(asked)!=1:valid=False
        if any(r['reviewed_contract_paragraph'].get('partial') for r in rows) and (not re.search(r'修改|不执行|直接|套用|本项目|作为.*(?:约定|要求)',question) or re.search(r'全文|完整|全部|[（(][一二三四五六七八九\d]+[)）]|第[（(]?[一二三四五六七八九\d]+[)）]?[项条]',question)):
            valid=False
        if not valid:
            return {'candidate_evidence':[{**r,'answer_usage':'BACKGROUND'} for r in selected.values()],
                'bundle_status':'SOURCE_SCOPE_MISSING','scope_mismatch_message':'尚未唯一取得所问项目及通用/专用类别的已核条款。本次未用同号的另一类条款代答，也未将单段用于跨条比较或效力认定。'}
        return {'candidate_evidence':rows,'bundle_status':'PRIMARY_SECTION_CANDIDATE',
            'reviewed_clause_audit':{'method':'EXACT_VERSIONED_NATIVE_PARAGRAPH','clause':code,'section':rows[0]['reviewed_contract_paragraph']['section']}}
    return None


def paragraph_answer(result):
    rows=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
    if len(rows)!=1 or not rows[0].get('reviewed_contract_paragraph'):return None
    c=rows[0];meta=c['reviewed_contract_paragraph']
    if meta.get('linked_modification'):
        return {**result,'answer_status':'SOURCE_EXTRACT','answer':'本版专用条件对同号通用条款有明确修改，需同时核对。专用条件原文：\n'+compact(meta['linked_modification'])+f' [{c["citation_id"]}]',
            'generation_mode':'REVIEWED_NATIVE_CLAUSE_NO_MODEL','status_label':'同版原文修改对照 · 待业务核对',
            'notice':'通用节选只作对照；未据此判断合同效力，也未将节选当作整条全文。'}
    return {**result,'answer_status':'SOURCE_EXTRACT','answer':f'该版文件{meta["section"]}第{meta["clause"]}条{('第（'+str(meta['item'])+'）项') if meta.get('item') is not None else ''}原文：\n'+compact(c['excerpt'])+f' [{c["citation_id"]}]',
        'generation_mode':'REVIEWED_NATIVE_CLAUSE_NO_MODEL','status_label':'指定条款原文 · 待业务核对',
        'notice':'保留本段条件、否定和例外；未将单段原文当成全部合同要求或现行效力认定。'}
