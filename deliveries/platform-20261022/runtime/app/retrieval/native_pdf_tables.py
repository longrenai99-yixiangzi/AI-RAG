"""Append source-verified native table rows; unverified flattened rows stay held."""
import json
from pathlib import Path

import numpy as np
from app.ingestion.pdf_table_records import extract_table_records
from app.bm25 import tokenize
from .clean_text_overlay import sha
from .named_source_scope import path_key,named_titles
import re


def purpose_supported(question,record):
    task=question
    for title in named_titles(question) or []:task=task.replace('《'+title+'》','')
    meta=record.get('native_pdf_table')
    caption=(meta or record.get('native_pdf_table_note') or {}).get('caption','')
    appendix=re.search(r'附件\s*(\d+)',task)
    original_appendix=(meta or record.get('native_pdf_table_note') or {}).get('appendix_number')
    if appendix and original_appendix is not None and int(appendix[1])!=original_appendix:return False
    if meta and '标准分值' in meta['all_original_headers'] and re.search(r'职责|岗位|责任分工|作用|原因|为什么|为何',task):
        if not appendix and meta['caption'] not in task and not re.search(r'评价|评分|扣分|标准分|考核|得分',task):return False
    for dimension in [('建造业务','地产开发业务'),('体系建设','体系执行')]:
        asked={v for v in dimension if v in task};actual={v for v in dimension if v in caption}
        if len(asked)==1 and actual and asked.isdisjoint(actual):return False
    if meta and '标准分值' in meta['all_original_headers'] and not named_titles(question):
        if not re.search(r'建造业务|地产开发业务',task) or not re.search(r'评价|评分|扣分|扣几分|标准分|考核|满分|得分',task):return False
    if record.get('native_pdf_table_note'):
        subject=re.sub(r'^注[:：]','',record['text'].split('=')[0])
        if subject not in re.sub(r'\s+','',task):return False
    return True


def scoped_indices(question,records,indices):
    if not named_titles(question):return None
    task=question
    for title in named_titles(question):task=task.replace('《'+title+'》','')
    appendix=re.search(r'附件\s*(\d+)',task)
    if not re.search(r'评分|扣|得分|标准分|满分|表头|字段|列名|评价事项|评价主体|应对措施|应对策略|风险类别',task):return None
    number=re.search(r'表\s*(\d+(?:-\d+)?)',task);matching=[]
    for i in indices:
        meta=records[i].get('native_pdf_table') or records[i].get('native_pdf_table_note')
        if not meta:continue
        caption=re.sub(r'^表\s*[\d-]+\s*','',meta['caption']);original=re.match(r'^表\s*([\d-]+)',meta['caption'])
        if (appendix and meta.get('appendix_number')==int(appendix[1]) or caption in re.sub(r'\s+','',task)
                or number and original and number[1]==original[1]):matching.append(i)
    if not matching:return None
    return [i for i in matching if purpose_supported(question,records[i])]


def append_native_tables(folder,candidate_hash,model_digest,paragraph_hash,documents,records,corpus,vectors):
    folder=Path(folder);read=lambda n:json.loads((folder/n).read_text(encoding='utf-8'))
    manifest=read('manifest.json')
    if (manifest['base_candidate_hash'],manifest['embedding_model_digest'],manifest['paragraph_manifest_sha256'])!=(candidate_hash,model_digest,paragraph_hash):
        raise ValueError('Native table candidate/model/paragraph dependency differs')
    if set(manifest['artifact_sha256'])!={'specs.json','records.json','vectors.npy','flat_exclusions.json'} or any(sha(folder/n)!=h for n,h in manifest['artifact_sha256'].items()):
        raise ValueError('Native table artifact changed')
    expected=extract_table_records(read('specs.json'));stored=read('records.json')
    if expected!=stored:raise ValueError('Native table rows differ from original geometry')
    matrix=np.load(folder/'vectors.npy',allow_pickle=False)
    if matrix.shape!=(len(expected),1024) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=.003):
        raise ValueError('Invalid native table vectors')
    ids={r['evidence_id'] for r in records}
    if len({r['evidence_id'] for r in expected})!=len(expected) or any(r['evidence_id'] in ids for r in expected):raise ValueError('Duplicate native table IDs')
    origins={}
    for r in records:origins.setdefault((path_key(r['source_path']),r['source_version']),r)
    by_id={r['evidence_id']:r for r in records};holds={}
    for entry in read('flat_exclusions.json'):
        old=by_id.get(entry['evidence_id'])
        if not old or any(old[k]!=entry[k] for k in ('source_path','source_version')) or old.get('location',{}).get('section')!=f'Page {entry["page"]}':
            raise ValueError('Native table flattened-row exclusion differs')
        holds[entry['evidence_id']]='REPLACED_BY_NATIVE_TABLE_ROWS'
    for r in expected:
        original=origins.get((path_key(r['source_path']),r['source_version']))
        if not original or original['document_id'] not in documents:raise ValueError('Native table source outside admitted candidate')
        binding={k:original[k] for k in ('document_id','source_id','document_role','authority_level','knowledge_root_id') if k in original}
        records.append({**binding,**r});corpus.append(tokenize(r['text']))
    return np.concatenate([vectors,matrix]),holds,{'manifest_sha256':sha(folder/'manifest.json'),'records':len(expected),
        'table_rows':sum('native_pdf_table' in r and not r['native_pdf_table']['summary_row'] for r in expected),
        'summaries':sum(r.get('native_pdf_table',{}).get('summary_row',False) for r in expected),
        'notes':sum('native_pdf_table_note' in r for r in expected),'flat_rows_replaced':len(holds)}


def overview_bundle(question,records,allowed_paths):
    if not named_titles(question) or not re.search(r'哪些|哪几|完整|全部',question):return None
    if re.search(r'计算|合计|总分|比较|对比|人数|今年|去年|\d{4}',re.sub(r'《.*?》','',question)):return None
    task=question
    for title in named_titles(question):task=task.replace('《'+title+'》','')
    task=re.sub(r'根据|依据|按照|请问|请列出|包括|包含|哪些|哪几类|有哪些|的|[\W_]','',task)
    groups={}
    for r in records:
        meta=r.get('native_pdf_table')
        if not meta or (allowed_paths is not None and path_key(r['source_path']) not in allowed_paths):continue
        caption=re.sub(r'^表\s*[\d-]+\s*','',meta['caption'])
        if task!=caption:continue
        groups.setdefault(meta['table_id'],[]).append(r)
    if not groups:return None
    rows=next(iter(groups.values())) if len(groups)==1 else []
    valid=bool(rows) and all(r['native_pdf_table']['table_complete'] for r in rows) and len(rows)<=8 and sum(len(r['text']) for r in rows)<=5000
    return {'candidate_evidence':[{**r,'answer_usage':'PRIMARY' if valid else 'BACKGROUND'} for r in rows[:8]],
        'bundle_status':'PRIMARY_SECTION_CANDIDATE' if valid else 'SOURCE_SCOPE_MISSING',
        'native_table_overview_audit':{'complete_rows_included':valid,'rows_available':len(rows)},
        'selection_notes':['只依据已核实原表行列举；表不完整或超过引用范围时不把单行当完整清单。']}


def direct_bundle(question,records,allowed_paths):
    if not named_titles(question):return None
    task=question
    for title in named_titles(question):task=task.replace('《'+title+'》','')
    if re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)|今年|去年|现行|最新|现在执行',task):return None
    header=bool(re.search(r'表头|字段|栏目|列名',task));total=bool(re.search(r'满分|标准总分|标准分值合计|实际总分|实际总得分',task))
    eligible=[r for r in records if allowed_paths is None or path_key(r['source_path']) in allowed_paths]
    if header or total:
        appendix=re.search(r'附件\s*(\d+)',task);number=re.search(r'表\s*(\d+(?:-\d+)?)',task);groups={};conflicting_scope=False
        for r in eligible:
            meta=r.get('native_pdf_table')
            if not meta:continue
            caption=re.sub(r'^表\s*[\d-]+\s*','',meta['caption'])
            original_number=re.match(r'^表\s*([\d-]+)',meta['caption'])
            if not (caption in re.sub(r'\s+','',task) or appendix and int(appendix[1])==meta['appendix_number'] or number and original_number and number[1]==original_number[1]):continue
            if not purpose_supported(question,r):conflicting_scope=True;continue
            if total and not meta['summary_row']:continue
            groups.setdefault(meta['table_id'],[]).append(r)
        if len(groups)>1 or conflicting_scope:return {'candidate_evidence':[],'bundle_status':'CONFLICTING_EVIDENCE','selection_notes':['表名、附件号、表号或业务范围未唯一对应，未用其中一张表代答。']}
        if not groups:return None
        row=dict(next(iter(groups.values()))[0])
        if total:
            rest=task.replace(row['native_pdf_table']['caption'],'')
            rest=re.sub(r'附件\s*\d+|表\s*[\d-]+|建造业务|地产开发业务|根据|依据|按照|请问|本表|此表|这张表|整表|整个表|标准分值|标准总分|标准分|实际总得分|实际总分|满分|是多少|多少|总计|合计|的|是|为|[\W_]','',rest)
            if rest:return None
        row['native_pdf_table']={**row['native_pdf_table'],'explicit_table_selection':True}
        if header:
            meta=dict(row['native_pdf_table']);meta.update(header_only=True,summary_row=False,row=1,cells=meta['header_cells'],original_headers=meta['all_original_headers'],column_indices=list(range(1,len(meta['all_original_headers'])+1)))
            row.update(evidence_id='native-header-'+row['evidence_id'],text='表名：'+meta['caption']+'\n表头：'+' | '.join(meta['all_original_headers']),
                location={**row['location'],'row':1},display_location=f'PDF第{meta["page"]}页 · {meta["caption"]} · 原表表头',native_pdf_table=meta)
            row.pop('table_evidence',None)
        return {'candidate_evidence':[{**row,'answer_usage':'PRIMARY'}],'bundle_status':'PRIMARY_SECTION_CANDIDATE','selection_notes':['依据原表字段或显式汇总行，未进行跨行计算。']}
    if re.search(r'公式|计算|口径|合同额|设计预算成本',task):
        notes=[r for r in eligible if r.get('native_pdf_table_note') and purpose_supported(question,r) and re.sub(r'^注[:：]','',r['text'].split('=')[0]) in re.sub(r'\s+','',task)]
        if len(notes)==1:
            blocked=bool(re.search(r'本项目|实际|代入|计算结果|\d',re.sub(r'附件\d+|表[\d-]+','',task)))
            return {'candidate_evidence':[{**notes[0],'answer_usage':'BACKGROUND' if blocked else 'PRIMARY'}],
                'bundle_status':'SOURCE_SCOPE_MISSING' if blocked else 'PRIMARY_SECTION_CANDIDATE','selection_notes':['只引用原表附注的计算口径，不代入未经核实的项目数据。']}
    if re.search(r'扣|分值|实得分|实际得分|内容|定义|什么是|措施|策略',task):
        meaningful=[]
        for r in eligible:
            meta=r.get('native_pdf_table')
            if not meta or meta['summary_row'] or not purpose_supported(question,r):continue
            values=[v for h,v in zip(meta['original_headers'],r['table_evidence']['values']) if h in {'风险类别','风险描述','评价维度','评价事项','评分标准'}]
            meaningful.append((r,'\n'.join(values)))
        for size in range(min(40,len(task)),3,-1):
            matches={}
            for start in range(len(task)-size+1):
                term=task[start:start+size]
                if not re.fullmatch(r'[\u4e00-\u9fff]{4,}',term):continue
                for r,text in meaningful:
                    if term in re.sub(r'\s+','',text):matches[r['evidence_id']]=(r,term)
            if matches:
                if len(matches)!=1:return None
                row,term=next(iter(matches.values()));meta={**row['native_pdf_table'],'explicit_row_selection':True,'literal_object_or_condition':term}
                return {'candidate_evidence':[{**row,'native_pdf_table':meta,'answer_usage':'PRIMARY'}],
                        'bundle_status':'PRIMARY_SECTION_CANDIDATE','selection_notes':['原表字段中明确出现的唯一对象或条件优先，不以相似子行代答。']}
    return None
