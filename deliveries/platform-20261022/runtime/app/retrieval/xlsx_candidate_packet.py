"""Local candidate evidence assembly; this does not authorize business answers."""
import re
import unicodedata
from openpyxl.utils import range_boundaries


def normalize_xlsx_query(text):
    text=unicodedata.normalize('NFKC',text)
    return re.sub(r'(?<=\d)[—–~至](?=\d)','-',text).replace('设计限额','限额设计').replace('快速预算对比概算','快速预算与概算对比')


def row_labels(record):
    return [str(cell['value']).removeprefix('其中').strip() for cell in record.get('source_cells',[])
            if isinstance(cell.get('value'),str) and (cell.get('header','').endswith('名称') or cell.get('header') in {'楼栋','分项工程','优化事项','优化内容','优化项目','档位','工程费金额范围'})]


def explicit_project_scope(question,records):
    # shortcut: literal project names in native titles only; unresolved short names require clarification.
    projects=[re.sub(r'^(?:请问|请告诉我|关于|请)+','',m) for m in re.findall(r'(?:^|[，,；;\s])([^，,；;。？?\s]{2,60}?项目)',normalize_xlsx_query(question))]
    source_ids=set()
    for project in projects:
        matched={record['source_id'] for record in records if project in normalize_xlsx_query(record.get('file_name','')+'\n'+record.get('raw_text','').split('\n')[0])}
        if not matched:return set(),{'status':'PROJECT_SCOPE_UNRESOLVED','project':project}
        source_ids|=matched
    return {record['id'] for record in records if not projects or record['source_id'] in source_ids},None


def native_points(record):
    result=set()
    def visit(cell):
        if cell.get('native_cells'):
            for member in cell['native_cells']:visit(member)
        else:
            ref=cell.get('origin_coordinate')
            if not ref:
                match=re.search(r'!([A-Z]+\d+)$',cell.get('cell_reference',''))
                ref=match[1] if match else None
            if ref:result.add((cell.get('sheet_name') or record.get('source_location',{}).get('sheet_name'),ref))
    for cell in record.get('source_cells',[]):visit(cell)
    return result


def explicit_table_scope(question,records,sheets):
    question=normalize_xlsx_query(question)
    wanted=[]
    for name in sheets:
        full=normalize_xlsx_query(name.strip())
        stem=re.sub(r'(?:汇总表|对比表|表)$','',full)
        if len(full)>=4 and re.search(re.escape(full)+r'(?:表|工作表|中|里|内|[A-Z]+\d|$)',question):wanted.append(name)
        elif len(stem)>=4 and stem!=full and stem in question:wanted.append(name)
    wanted=[name for name in wanted if not any(name.strip()!=other.strip() and name.strip() in other.strip() for other in wanted)]
    ranges=re.findall(r'(?<![A-Z0-9])([A-Z]{1,3}\d+:[A-Z]{1,3}\d+)',question)
    cell_matches=re.findall(r'(?<![A-Z0-9])([A-Z]{1,3}\d+)(?![A-Z0-9])',question) if not ranges else []
    allowed=[]
    for record in records:
        sheet=record.get('source_location',{}).get('sheet_name')
        if wanted and sheet not in wanted:continue
        points=native_points(record)
        if ranges:
            boxes=[range_boundaries(value) for value in ranges]
            if not any(any(left<=range_boundaries(ref)[0]<=right and top<=range_boundaries(ref)[1]<=bottom for _,ref in points) for left,top,right,bottom in boxes):continue
        if cell_matches and not any(ref in cell_matches for _,ref in points):continue
        allowed.append(record['id'])
    return set(allowed),{'named_sheets':wanted,'explicit_ranges':ranges,'explicit_cells':cell_matches}


def ambiguous_native_field(question,records,tables):
    for record in records:
        table=tables.get(record.get('table_id'),{})
        if not table.get('requires_column_scope'):continue
        original=table.get('original_header') or []
        for label in set(original):
            leaf=label.split(' > ')[-1]
            if original.count(label)>1 and leaf in question and not re.search(r'[A-Z]{1,3}\s*列',question):
                return {'status':'AMBIGUOUS_NATIVE_FIELD','field':label,'source_id':record['source_id']}
    return None


def literal_row_matches(question,records):
    """Keep explicitly named native rows ahead of model similarity."""
    question=normalize_xlsx_query(question)
    matched=set()
    for record in records:
        if record.get('kind')!='CHILD':continue
        for value in row_labels(record):
            name=normalize_xlsx_query(value)
            if len(name)>=3 and name in question:matched.add(record['id'])
    return matched


def missing_parallel_rows(question,records):
    labels={unicodedata.normalize('NFKC',label) for record in records for label in row_labels(record) if len(label)>=3}
    for clause in re.findall(r'([^，,。？?]+?)的',normalize_xlsx_query(question)):
        clause=clause.rsplit('时',1)[-1].removesuffix('各自')
        parts=re.split(r'与|和|、',clause)
        if len(parts)<2:continue
        present=[any(label in part for label in labels) for part in parts]
        if any(present) and not all(present):
            return {'status':'PARALLEL_ROW_NOT_SUPPORTED','missing_subjects':[part for part,found in zip(parts,present) if not found]}
    return None


def missing_amount_basis(question,records):
    # shortcut: checks literal amount bases only; broader semantic intent needs separate validation.
    bases=set(re.findall(r'(结算|预算|概算|中标|合同)(?:总)?(?:价|金额|费用)',question))
    headers=[cell.get('header','') for record in records if record.get('kind')=='CHILD' for cell in record.get('source_cells',[])]
    missing=sorted(basis for basis in bases if not any(basis in header for header in headers))
    if missing:return {'status':'AMOUNT_BASIS_NOT_SUPPORTED','missing_bases':missing}
    qualifiers=[term for term in ('可研批复','竣工结算','审定结算') if term in question and not any(term in header for header in headers)]
    return {'status':'REQUESTED_QUALIFIER_NOT_SUPPORTED','missing_qualifiers':qualifiers} if qualifiers else None


def hydrate_candidate_packet(seeds,records,parents):
    linked={};contexts={};missing=[]
    for seed in seeds:
        if seed.get('index_status','STAGING_CANDIDATE')!='STAGING_CANDIDATE':
            raise ValueError('Ineligible seed evidence')
        if seed.get('kind')!='CHILD':continue
        key=seed.get('source_table_row_id')
        siblings=[record for record in records if key and record.get('kind')=='CHILD' and record.get('index_status','STAGING_CANDIDATE')=='STAGING_CANDIDATE' and record.get('source_table_row_id')==key and record['source_id']==seed['source_id'] and record['source_version']==seed['source_version']]
        for record in [seed,*siblings]:
            linked[record['id']]=record
            pid=record.get('parent_chunk_id')
            if pid:
                parent=parents.get(pid)
                if not parent or (parent['source_id'],parent['source_version'])!=(record['source_id'],record['source_version']):
                    raise ValueError('Missing or cross-version parent evidence')
                contexts[pid]=parent
        if key and len({record.get('field_group_index') for record in siblings})<seed.get('field_group_count',1):missing.append(key)
    return {'primary_ids':[record['id'] for record in seeds],'linked_row_ids':list(linked),'context_ids':list(contexts),'missing_row_groups':list(dict.fromkeys(missing)),'business_answer_authorized':False}


def compact_candidate_packet(question,packet,records,parents):
    """Select literal metric fields, retaining native labels and separate context."""
    # shortcut: a small Excel metric vocabulary; unsupported wording stays review-only.
    aliases={word:word for word in ('施工图预算','预算价','预算成本','建筑面积','中标价','限额划分','限额设计','风险预留金','预留金比例','收入','成本','利润率','费率','备注')}
    aliases.update({'预算成本价':'预算成本','中标金额':'中标价','风险预留金额':'风险预留金'})
    question=normalize_xlsx_query(question)
    wanted=list(dict.fromkeys(aliases[m[0]] for m in re.finditer('|'.join(sorted(aliases,key=len,reverse=True)),question)))
    fields={};contexts={};hits={key:[] for key in wanted}
    for identity in dict.fromkeys(packet['primary_ids']+packet['linked_row_ids']):
        record=records[identity]
        for cell in record.get('source_cells',[]):
            header=normalize_xlsx_query(cell.get('header',''))
            label=re.sub(r'\([^)]*\)','',header).split('=')[0]
            if re.search(r'说明|来源|备注|条件|限制',header) and isinstance(cell.get('value'),str) and cell['value'].strip():
                ref=cell.get('origin_coordinate') or cell.get('cell_reference')
                contexts[(record['source_id'],record['source_version'],record['source_location']['sheet_name'],ref)]={'source_id':record['source_id'],'source_version':record['source_version'],'file_name':record['file_name'],'source_path':record['source_path'],'sheet':record['source_location']['sheet_name'],'coordinate':ref,'header':cell.get('header'),'text':cell['value']}
            for key in wanted:
                if key not in label:continue
                if any(term in header and term not in question for term in ('单方','指标','工程量','比例')):continue
                if key in {'限额设计','限额划分'} and any(term in header for term in ('风险','预留','合计')):continue
                if '下浮前后' not in question:
                    if '下浮后' in question and '下浮前' in header:continue
                    if '下浮前' in question and '下浮后' in header:continue
                if key!='备注' and (isinstance(cell.get('value'),bool) or not re.fullmatch(r'-?\d+(?:\.\d+)?%?',str(cell.get('value','')))):continue
                ref=cell.get('origin_coordinate') or cell.get('cell_reference')
                if not ref:continue
                item={'source_id':record['source_id'],'source_version':record['source_version'],'file_name':record['file_name'],'source_path':record['source_path'],'sheet':record['source_location']['sheet_name'],'coordinate':ref,'header':cell.get('header'),'raw_value':cell['value'],'display_value':cell.get('display_text',cell['value']),'row_labels':row_labels(record)}
                fields[(record['source_id'],record['source_version'],item['sheet'],ref)]=item
                hits[key].append(item)
        row_context=record.get('row_context')
        if isinstance(row_context,list):
            for cell in row_context:
                if cell.get('value_status')!='NATIVE_VALUE':continue
                ref=cell.get('origin_coordinate') or cell.get('cell_reference')
                sheet=cell.get('sheet_name',record['source_location']['sheet_name'])
                contexts[(record['source_id'],record['source_version'],sheet,ref)]={'source_id':record['source_id'],'source_version':record['source_version'],'file_name':record['file_name'],'source_path':record['source_path'],'sheet':sheet,'coordinate':ref,'text':cell.get('display_text',cell['value'])}
        elif row_context:
            contexts[(record['source_id'],identity)]={'source_id':record['source_id'],'source_version':record['source_version'],'file_name':record['file_name'],'source_path':record['source_path'],'text':row_context}
    for pid in packet['context_ids']:
        parent=parents[pid]
        for cell in parent.get('cells',parent.get('source_cells',[])):
            if cell.get('value_status')!='NATIVE_VALUE':continue
            ref=cell.get('origin_coordinate') or cell.get('cell_reference')
            contexts[(parent['source_id'],parent['source_version'],parent.get('sheet_name'),ref)]={'source_id':parent['source_id'],'source_version':parent['source_version'],'file_name':parent['file_name'],'source_path':parent['source_path'],'sheet':parent.get('sheet_name'),'coordinate':ref,'text':cell.get('display_text',cell['value'])}
    boundary=None
    for key,items in hits.items():
        if not items:boundary={'status':'FIELD_SELECTION_INCOMPLETE','field':key};break
        grouped={}
        values={}
        for item in items:
            group=(item['source_id'],tuple(item['row_labels']))
            grouped.setdefault(group,set()).add(item['header'])
            values.setdefault((group,item['header']),set()).add(str(item['raw_value']))
        if any(len(value)>1 for value in values.values()):
            boundary={'status':'CONFLICTING_NATIVE_VALUES','field':key};break
        paired=(key in {'施工图预算','预算价'} and '下浮前后' in question) or (key=='收入' and (bool(re.search(r'前.*后.*方案',question)) or all(term in question for term in ('原方案','新方案'))))
        if not paired and any(len(headers)>1 for headers in grouped.values()):
            boundary={'status':'AMBIGUOUS_REQUESTED_FIELD','field':key};break
    return {'requested_fields':wanted,'fields':list(fields.values()),'contexts':list(contexts.values()),'boundary':boundary,'status':'REVIEW_ONLY' if not wanted else 'CANDIDATE_FIELDS_SELECTED','business_answer_authorized':False}
