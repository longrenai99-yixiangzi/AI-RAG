"""Verify visible source fields and append a bounded table layer to the existing candidate."""
import json,hashlib,re,copy
from pathlib import Path
import numpy as np
import pymupdf
from app.bm25 import tokenize
from app.ingestion.pdf_native_geometry import character_layer,cell_text
from app.ingestion.pdf_paragraph_context import native_lines
from app.retrieval.named_source_scope import path_key
from app.retrieval.table_schema import PDF_READ_LOCK


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def flat(text):return ''.join(text.splitlines()).strip()
def signature(text,box):return text,tuple(round(v,4) for v in box)


def source_contexts(folder):
    contexts={}
    for g in read(Path(folder)/'reviewed_grids.json'):
        cells=g['native']['cells']
        if not any(c['row']==1 and c['column']==1 and flat(c['text'])=='项目名称' for c in cells):continue
        project=next(c for c in cells if c['row']==1 and c['column']==3)
        date=next(c for c in cells if c['row']==1 and c['column']==6)
        contexts[g['source_version']]={'project_name':flat(project['text']),'evaluation_date':re.sub(r'\s+','',date['text']),
            'source_cells':[project,date]}
    return contexts


def verify_source_rows(folder):
    folder=Path(folder);m=read(folder/'manifest.json');review=read(folder/'revision_receipt.json')
    if sha(folder/'manifest.json')!=review['proof_sha256'][str(folder/'manifest.json')]:raise ValueError('Reviewed table manifest changed')
    if any(sha(folder/n)!=h for n,h in m['artifact_sha256'].items()):raise ValueError('Reviewed table artifact changed')
    rows=read(folder/'records.json');grids=read(folder/'reviewed_grids.json');docs={};cache={}
    profiles={(path_key(g['source_path']),g['source_version'],g['page']):g for g in grids}
    def chars(path,version,page):
        identity=(path_key(path),version);key=(*identity,page)
        if key in cache:return cache[key]
        if identity not in docs:
            raw=Path(path).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Reviewed PDF source changed')
            docs[identity]=pymupdf.open(stream=raw,filetype='pdf')
        pg=docs[identity][page-1];values,_=character_layer(pg.get_text('rawdict'),version);profile=profiles.get(key,{})
        hidden=profile.get('confirmed_occluded_native_lines',[]);remove=set()
        for wanted in hidden:
            found=[l for l in native_lines(pg) if l['text']==wanted['text'] and tuple(round(v,4) for v in l['bbox'])==tuple(round(v,4) for v in wanted['bbox'])]
            if len(found)!=1:raise ValueError('Occluded native-line proof changed')
            remove.update(signature(c['c'],c['bbox']) for c in found[0]['chars'])
        values=[c for c in values if signature(c['text'],c['bbox']) not in remove]
        mask=profile.get('masked_value_bbox')
        if mask:
            inside=lambda c:mask[0]<=(c['bbox'][0]+c['bbox'][2])/2<=mask[2] and mask[1]<=(c['bbox'][1]+c['bbox'][3])/2<=mask[3]
            if sum(inside(c) for c in values)!=profile['masked_native_chars_excluded']:raise ValueError('Masked region proof changed')
            values=[c for c in values if not inside(c)]
        for override in profile.get('native_span_owner_overrides',[]):
            found=[c for c in values if signature(c['text'],c['bbox'])==signature(override['text'],override['original_bbox'])]
            if len(found)!=1:raise ValueError('Native span ownership proof changed')
            found[0]['bbox']=override['assignment_bbox']
        cache[key]=values;return values
    with PDF_READ_LOCK:
        try:
            for r in rows:
                source=r['source_path'];version=r['source_version'];page=r['location']['page']
                for f in r['fields']:
                    original=cell_text(chars(source,version,page),f['cell']['bbox'])
                    if original!=f['cell']['text']:raise ValueError('Visible source cell differs')
                    fragments=f['continuation_fragments']
                    for fragment in fragments:
                        if cell_text(chars(source,version,fragment['page']),fragment['bbox'])!=fragment['text']:raise ValueError('Continuation source differs')
                    expected='\n'.join(v['text'] for v in fragments) if fragments else original
                    if f['raw_text']!=expected:raise ValueError('Field differs from complete visible source')
                    if not expected.strip() and f['read_status'] not in {'BLANK_IN_SOURCE','IMAGE_REGION_NO_READABLE_NUMBER'}:raise ValueError('Blank field misclassified')
                for h in r['header_sources']:
                    if flat(cell_text(chars(source,version,h['page']),h['bbox']))!=h['text']:raise ValueError('Header source differs')
                for parent in r['parent_context']:
                    if cell_text(chars(source,version,parent['page']),parent['bbox'])!=parent['text']:raise ValueError('Parent source differs')
                if r.get('selected_root_option') and not any('☑不要求' in re.sub(r'\s+','',f['raw_text']) for f in r['fields']):raise ValueError('Root selection not verified')
            for version,ctx in source_contexts(folder).items():
                source=next(r['source_path'] for r in rows if r['source_version']==version)
                for c in ctx['source_cells']:
                    if cell_text(chars(source,version,c['page']),c['bbox'])!=c['text']:raise ValueError('Source context changed')
            return rows,m
        finally:
            for doc in docs.values():doc.close()


def append_rows(folder,candidate_hash,model_digest,paragraph_hash,documents,records,corpus,vectors):
    folder=Path(folder);m=read(folder/'manifest.json')
    if (m['base_candidate_hash'],m['embedding_model_digest'],m['additional_paragraph_manifest_sha256'])!=(candidate_hash,model_digest,paragraph_hash):raise ValueError('Table-field dependency differs')
    if any(sha(folder/n)!=h for n,h in m['artifact_sha256'].items()):raise ValueError('Table-field compiled artifact changed')
    original_folder=Path(m['reviewed_source_folder'])
    if sha(original_folder/'manifest.json')!=m['reviewed_source_manifest_sha256']:raise ValueError('Table-field review version changed')
    original,review=verify_source_rows(original_folder);compiled=read(folder/'records.json')
    if len(compiled)!=len(original) or any(r['text']!=o['text'] or r['reviewed_table_row']!=o or r['evidence_id']!=o['evidence_id'] for r,o in zip(compiled,original,strict=True)):raise ValueError('Compiled rows differ from reviewed fields')
    contexts=source_contexts(original_folder)
    if any(r.get('reviewed_table_context',{})!=contexts.get(r['source_version'],{}) for r in compiled):raise ValueError('Compiled context differs')
    matrix=np.load(original_folder/'vectors.npy',allow_pickle=False)
    if matrix.shape!=(len(compiled),1024) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=.003):raise ValueError('Table-field vector alignment differs')
    if review['embedding_model_digest']!=model_digest:raise ValueError('Reviewed row encoder differs')
    existing={r['evidence_id']:r for r in records};origins={}
    for r in records:origins.setdefault((path_key(r['source_path']),r['source_version']),r)
    for r in compiled:
        origin=origins.get((path_key(r['source_path']),r['source_version']))
        if r['evidence_id'] in existing or not origin or origin['document_id'] not in documents:raise ValueError('Table-field source not admitted or ID duplicated')
    holds={}
    for h in read(folder/'flat_exclusions.json'):
        old=existing.get(h['evidence_id'])
        if not old or any(old[k]!=h[k] for k in ('source_path','source_version')) or old.get('location',{}).get('section')!=f'Page {h["page"]}':raise ValueError('Old flat-table binding differs')
        holds[h['evidence_id']]='REPLACED_BY_VISIBLE_REVIEWED_TABLE_FIELDS'
    for r in compiled:
        origin=origins[(path_key(r['source_path']),r['source_version'])]
        binding={k:origin[k] for k in ('document_id','source_id','document_role','authority_level','knowledge_root_id') if k in origin}
        records.append({**binding,**r});corpus.append(tokenize(r['text']))
    return np.concatenate([vectors,matrix]),holds,{'manifest_sha256':sha(folder/'manifest.json'),'records':len(compiled),
        'flat_rows_replaced':len(holds),'answer_scope':'EXPLICIT_SOURCE_AND_BOUNDED_ORIGINAL_FIELDS','model_calls_required':False}
