"""Version-bound personnel lookup over native rows; never sum phases or infer team totals."""
import hashlib,json,re
from pathlib import Path
from app.answer_engine.question_scope import question_scope,personnel_count_query
from app.ingestion.scalar_evidence import _docx_parents
from app.retrieval.named_source_scope import path_key


def request_scope(question):
    question=re.sub(r'《[^》]+》','',question)
    if not personnel_count_query(question):return None
    hint=question_scope(question) or {}
    if hint.get('kind')=='ROLE_AND_TEAM_COUNTS':return 'MULTIPLE_COUNT_TARGETS'
    if re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)|不含|不包括|剔除|扣除|除外|截至',question):return 'UNVERIFIED_CONDITION'
    if re.search(r'设计(?:管理)?团队|仅设计岗位|设计岗位',question):return 'DESIGN_TEAM_TOTAL'
    employment=re.sub(r'专兼职|专职(?:还是|或|/|、)兼职','',question)
    if re.search(r'专职|兼职',employment) or (re.search(r'领导班子|技术部|工程部',question) and re.search(r'仅|合计|总人数',question)):return 'UNVERIFIED_SUBGROUP'
    if hint.get('kind')=='PROJECT_ORGANIZATION_COUNT':return 'PROJECT_ORGANIZATION_TOTAL'
    if re.search(r'阶段|施工图|初设|初步设计|专项设计|竣工|驻场|岗位配置|人员配置表',question):return 'DESIGN_STAGE_POSITION'
    if hint.get('kind')=='LEAD_ROLE_COUNT' or re.search(r'(?:技术|设计|商务|建造|安全|质量)总监|项目经理|设计经理',question):return 'LEAD_ROLE'
    return 'UNSPECIFIED_COUNT_TARGET'


def count_remainder(text):
    # shortcut: controlled count wording; extend only after checking new business questions.
    return re.sub(r'专兼职|专职(?:还是|或|/|、)兼职|阶段|岗位|人员|配置|需要|一共|总共|多少|几|人数|数量|如何|是否|情况|原表|表中|的|为|是|有|共|人|名|位|个|[\s，,。？?：:；;（）()]','',text)


def stage_positions(question,rows):
    """Require a complete native position or a unique explicit abbreviation."""
    phases={r['personnel']['phase'] for r in rows};aliases={p:{p,p.removesuffix('阶段').removesuffix('设计')} for p in phases if p}
    wanted={p for p,names in aliases.items() if any(name in question for name in names)}
    if len(wanted)!=1:return []
    task=question
    for name in sorted({n for p in wanted for n in aliases[p]},key=len,reverse=True):task=task.replace(name,'')
    chosen=[]
    for row in rows:
        if row['personnel']['phase'] not in wanted:continue
        position=row['personnel']['position'];names={position,position.removeprefix('设计支持中心').removesuffix('人员')}
        matches=[name for name in names if name and name in task]
        if matches:chosen.append((row,max(matches,key=len)))
    if len(chosen)!=1:return []
    row,name=chosen[0]
    return [row] if not count_remainder(task.replace(name,'')) else []


def build_records(parsed):
    """Reuse the existing native paragraph/row reader and corrected structural positions."""
    doc=parsed['documents'][0];path=Path(doc['source_path']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    sections={s['section_id']:s for s in parsed['sections']};parents=_docx_parents(path,digest)
    native_rows={(p['location']['table'],p['location']['row']):p for p in parents if 'table' in p['location']}
    paragraphs={p['location']['paragraph']:p for p in parents if 'paragraph' in p['location']};out=[]
    for p in parsed['paragraphs']:
        heading=sections[p['section_id']]['heading_path']
        match=re.search(r'(?:配置|配备)([^，。；\d]{1,20})\s*\d+\s*人',p['text'])
        if not match or not re.search(r'统筹|牵头',p['text']) or '组织架构' not in heading:continue
        native=paragraphs[p['order']]
        out.append({**native,'document_id':doc['document_id'],'heading_path':heading,'location':p['location'],
                    'personnel':{'kind':'LEAD_ROLE','position':match[1],'scope_basis':'原文配置人数与统筹职责同段'}})
    for table in parsed['tables']:
        rows=[r for r in parsed['table_rows'] if r['table_id']==table['table_id']];joined='\n'.join(' | '.join(r['values']) for r in rows)
        stage_table=all(h in table['header'] for h in ['阶段','岗位','人员配置数量'])
        organization=all(marker in joined for marker in ['项目组织结构模式','项目领导班子成员','部门'])
        if not stage_table and not organization:continue
        heading=sections[table['section_id']]['heading_path'];number=table['source_location']['table']
        for row in rows:
            if row['is_header'] or row.get('is_table_preamble'):continue
            total=any(re.fullmatch(r'合计|总计|总人数',v.strip()) for v in row['values'])
            if not stage_table and not total:continue
            native=native_rows[(number,row['row_number'])]
            compact=lambda s:re.sub(r'\s+','',s)
            if compact(''.join(native['table_cells']))!=compact(''.join(row['values'])):raise ValueError('Native personnel cells differ from parsed row')
            fields={c['header']:c['value'] for c in row['cells']}
            kind='DESIGN_STAGE_TABLE_TOTAL' if stage_table and total else 'DESIGN_STAGE_POSITION' if stage_table else 'PROJECT_ORGANIZATION_TOTAL'
            out.append({**native,'document_id':doc['document_id'],'heading_path':heading,
                        'location':row['source_location'],'display_location':f'{heading} > 原件第{number}表第{row["row_number"]}行',
                        'personnel':{'kind':kind,'phase':fields.get('阶段',''),'position':fields.get('岗位',''),
                                     'scope_basis':'阶段、岗位、人员配置数量原列' if stage_table else '原表含项目组织模式、领导班子及部门；只引用明确合计行'}})
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Native source changed while reading personnel rows')
    return out


def extract_answer(bundle,cards,question):
    """Quote one scoped native unit, without deriving counts or calling a model."""
    audit=bundle.get('personnel_scope_audit') or {};target=audit.get('target')
    titles={'LEAD_ROLE':'岗位与配置人数原文','PROJECT_ORGANIZATION_TOTAL':'项目组织表明确合计行原文','DESIGN_STAGE_POSITION':'同一阶段、岗位的配置行原文'}
    if target not in titles or request_scope(question)!=target or audit.get('eligible_rows')!=1 or len(cards)!=1:return None
    rows=bundle.get('candidate_evidence',[])
    if len(rows)!=1:return None
    row=rows[0];card=cards[0]
    if row.get('answer_usage')!='PRIMARY' or row.get('personnel',{}).get('kind')!=target:return None
    if any(row.get(k)!=card.get(k) for k in ('evidence_id','source_path','source_version','location')) or row.get('text')!=card.get('excerpt'):return None
    path=Path(row['source_path']);version=row['source_version']
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=version:return None
        native=next((p for p in _docx_parents(path,version) if p['evidence_id']==row['evidence_id']),None)
        if not native or any(native.get(k)!=row.get(k) for k in ('text','table_cells','table_headers')):return None
        location=row['location'];original=native['location']
        if 'table' in original:
            if location.get('header_row')!=1 or any(location.get(k)!=original.get(k) for k in ('table','row')):return None
        elif location.get('paragraph_start')!=original.get('paragraph') or location.get('paragraph_end')!=original.get('paragraph'):return None
        if hashlib.sha256(path.read_bytes()).hexdigest()!=version:return None
    except (OSError,ValueError,KeyError):return None
    text=row['text'];sid=card['citation_id']
    return {'answer_status':'SOURCE_EXTRACT_DRAFT','status_label':'原文摘录 · 待核对','answer':titles[target]+'：\n'+text+' ['+sid+']',
            'answer_contract_version':'NATIVE_SOURCE_EXTRACT_V1','support_check':'EXACT_NATIVE_UNIT','answer_completeness':'SCOPED_SOURCE_EXTRACT',
            'claims':[{'claim_id':'C1','claim_text':text,'rendered_claim_text':text,'evidence_ids':[sid],'claim_type':'SOURCE_EXTRACT'}]}


class PersonnelIndex:
    def __init__(self,folder,candidate_hash,source_ids):
        folder=Path(folder);self.manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if self.manifest['base_candidate_hash']!=candidate_hash:raise ValueError('Personnel index belongs to another candidate')
        raw=(folder/'records.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.manifest['records_sha256']:raise ValueError('Personnel evidence changed')
        self.records=json.loads(raw);self.by_path={}
        if len({r['evidence_id'] for r in self.records})!=len(self.records):raise ValueError('Duplicate personnel evidence IDs')
        for r in self.records:
            key=(path_key(r['source_path']),r['source_version'])
            if key not in source_ids:raise ValueError('Personnel source version is outside the candidate')
            r['lineage_source_id']=r['source_id'];r['source_id']=source_ids[key];self.by_path.setdefault(key[0],[]).append(r)

    def lookup(self,question,allowed_paths):
        target=request_scope(question)
        if target is None:return None
        rows=[];chosen=[];reason='人数对象或资料范围尚不明确，请区分牵头岗位、项目组织合计与仅设计岗位团队。'
        if allowed_paths and len(set(allowed_paths))==1:
            path=next(iter(allowed_paths));rows=self.by_path.get(path,[])
            if rows and hashlib.sha256(Path(rows[0]['source_path']).read_bytes()).hexdigest()!=rows[0]['source_version']:rows=[];reason='原件版本已变，本次数值检索停止。'
            elif rows:
                chosen=[r for r in rows if r['personnel']['kind']==target]
                if target=='LEAD_ROLE':
                    requested=re.findall(r'(?:技术|设计|商务|建造|安全|质量)总监|项目经理|设计经理',question)
                    if requested:chosen=[r for r in chosen if r['personnel']['position'] in requested]
                    if len(chosen)==1:
                        task=question.replace(chosen[0]['personnel']['position'],'')
                        task=re.sub(r'岗位(?:及|和|与)人数','岗位人数',task)
                        task=re.sub(r'组织架构表|组织结构表|本项目|项目|哪个|负责人|负责|统筹|牵头|技术|设计|管理|工作|由|谁|和|与|中','',task)
                        if count_remainder(task):chosen=[]
                elif target=='DESIGN_STAGE_POSITION':
                    chosen=stage_positions(question,chosen)
                    reason='未取得同一明确阶段和岗位的唯一人员配置行；不跨阶段相加，也不替换为其他阶段人数。'
                elif target=='UNVERIFIED_CONDITION':reason='本次人数记录未核对所问年度、截止时间或排除条件，不能将不带该条件的配置人数直接代入。'
                elif target=='UNVERIFIED_SUBGROUP':reason='本次未取得所问子范围的独立人数；整行配置、专兼职属性或项目合计不能直接替代该子范围人数。'
                elif target=='DESIGN_TEAM_TOTAL':reason='本次核对的人数记录未取得所问范围的明确设计团队合计；不从岗位、分阶段配置或项目组织合计推算，也不据此断定整份原件或整库没有资料。'
                elif target=='PROJECT_ORGANIZATION_TOTAL':reason='本次核对的人数记录未取得项目组织人员的明确合计行，不能用负责人或设计岗位配置代替。'
            else:reason='本次人数范围索引未核对该原件；这不表示整库没有资料。'
        valid=len(chosen)==1
        selected=chosen if valid else rows[:8]
        return {'candidate_evidence':[{**r,'role':'DIRECT','answer_usage':'PRIMARY' if valid else 'BACKGROUND','score':1.0} for r in selected],
                'bundle_status':'PRIMARY_SECTION_CANDIDATE' if valid else 'SOURCE_SCOPE_MISSING',
                'personnel_scope_audit':{'target':target,'inferred':True,'native_rows_in_scope':len(rows),'eligible_rows':len(chosen),'index_records_sha256':self.manifest['records_sha256'],'no_cross_phase_sum':True},
                'selection_notes':['按原件同一范围的明确人数记录返回原文，尚未生成或验收业务回答。'] if valid else [reason]}
