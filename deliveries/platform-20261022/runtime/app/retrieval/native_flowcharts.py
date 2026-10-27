"""Source-bound frame lookup; no workflow or approval inference from diagram ordering."""
import json,re
from pathlib import Path
import numpy as np
from app.bm25 import tokenize
from app.ingestion.flowchart_records import extract_flow_records
from .clean_text_overlay import sha
from .named_source_scope import path_key,named_titles


def append_flowcharts(folder,candidate_hash,model_digest,table_hash,documents,records,corpus,vectors):
    folder=Path(folder);read=lambda n:json.loads((folder/n).read_text(encoding='utf-8'))
    m=read('manifest.json')
    if (m['base_candidate_hash'],m['embedding_model_digest'],m['native_tables_manifest_sha256'])!=(candidate_hash,model_digest,table_hash):
        raise ValueError('Flowchart candidate/model/table dependency differs')
    if set(m['artifact_sha256'])!={'specs.json','charts.json','records.json','flow_clue_audit_12.json','vectors.npy'} or any(sha(folder/n)!=h for n,h in m['artifact_sha256'].items()):
        raise ValueError('Flowchart artifact changed')
    rows=read('records.json')
    if extract_flow_records(read('specs.json'))!=rows:raise ValueError('Flowchart frames differ from original')
    matrix=np.load(folder/'vectors.npy',allow_pickle=False)
    if matrix.shape!=(len(rows),1024) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=.003):
        raise ValueError('Invalid flowchart vectors')
    ids={r['evidence_id'] for r in records}
    if len({r['evidence_id'] for r in rows})!=len(rows) or any(r['evidence_id'] in ids for r in rows):raise ValueError('Duplicate flowchart IDs')
    origins={}
    for r in records:origins.setdefault((path_key(r['source_path']),r['source_version']),r)
    for r in rows:
        original=origins.get((path_key(r['source_path']),r['source_version']))
        if not original or original['document_id'] not in documents:raise ValueError('Flowchart source outside admitted candidate')
    for r in rows:
        original=origins[(path_key(r['source_path']),r['source_version'])]
        records.append({**{k:original[k] for k in ('document_id','source_id','document_role','authority_level','knowledge_root_id') if k in original},**r})
        corpus.append(tokenize(r['text']))
    charts=read('charts.json')
    return np.concatenate([vectors,matrix]),{'manifest_sha256':sha(folder/'manifest.json'),'records':len(rows),
        'frames':sum(len(c['nodes']) for c in charts),'drawn_arrows':sum(len(c['edges']) for c in charts),
        'arrows_held':sum(len(c['held_arrows']) for c in charts),'workflow_relations_used_for_answers':False}


def is_flow_record(record):return bool(record.get('native_flow_node') or record.get('native_flow_header'))


def frame_bundle(question,records):
    task=re.sub(r'\s+','',question)
    for title in named_titles(question) or []:task=task.replace('《'+re.sub(r'\s+','',title)+'》','')
    if not re.search(r'流程图|泳道|附件(?:17|18|19)(?!\d)',task):return None
    headers=[r for r in records if r.get('native_flow_header')]
    if not headers:return None
    audit={'method':'EXACT_NATIVE_FRAME_SCOPE','relations_used':False}
    def hold(message):
        audit['clarification_message']=message
        return {'candidate_evidence':[{**r,'answer_usage':'BACKGROUND'} for r in headers[:3]],
            'bundle_status':'SOURCE_SCOPE_MISSING','scope_mismatch_message':message,'native_flow_audit':audit}
    if re.search(r'今年|去年|最新|现行|现在|(?:19|20)\d{2}',task):
        return hold('当前只核对本版流程图原文，尚未核定指定年份或现行效力，不能直接作为该时点的执行要求。')
    if re.search(r'是否|能否|必须|不属于|不包括|无需|不用|不是|不需要|不应|不能|没有|未开展|除.+之外|顺序|先后|之前|之后|箭头|指向|连线|批准|审批权限|全部流程|完整流程|对比|区别|差异|多少|多久|几人|几天|何时|为什么|原因|目的|作用',task):
        return hold('本次按已核图框及其证据范围作答。不能仅凭图框或连线判断必须先后、审批权限、否定结论或跨图比较；请限定图框内容或直接绘制方向，业务要求仍需核对正文依据。')
    for short,full in [('初设阶段','初步设计阶段'),('方案阶段','方案设计阶段'),('初步阶段','初步设计阶段'),('施工图阶段','施工图设计阶段')]:task=task.replace(short,full)
    starts=re.findall(r'(方案设计阶段|初步设计阶段|施工图设计阶段)(?:开始|起始)',task)
    numbers={int(n) for n in re.findall(r'附件(\d+)',task)}
    if len(numbers)>1 or len(set(starts))>1:return hold('请一次限定一张流程图：附件17从方案阶段开始、附件18从初步阶段开始、附件19从施工图阶段开始。')
    chosen=[r for r in headers if (not numbers or r['native_flow_header']['appendix'] in numbers) and
            (not starts or r['native_flow_header']['chart_start']==starts[0])]
    if len(chosen)!=1:return hold('流程图起点尚未唯一对应。请明确附件17（方案开始）、18（初步开始）或19（施工图开始），并核对附件号与起点是否一致。')
    header=chosen[0]['native_flow_header'];audit.update(appendix=header['appendix'],chart_start=header['chart_start'])
    task=re.sub(r'(?:从)?(?:方案设计阶段|初步设计阶段|施工图设计阶段)(?:开始|起始)','',task)
    phases={p for p in ['方案设计阶段','初步设计阶段','施工图设计阶段'] if p in task}
    if len(phases)>1:return hold('请一次限定图内一个节点阶段；图的起点与节点所在阶段分别记录，未将两个阶段混合代答。')
    phases=phases or set(header['node_phases'])
    if len(phases)!=1 or not phases.issubset(set(header['node_phases'])):return hold('请补充节点所在的方案、初步或施工图阶段；本次未将流程起点当成全部节点的阶段。')
    phase=next(iter(phases));audit['node_phase']=phase
    lanes={lane for lane in header['lane_names'] if lane in task}
    canonical=lambda s:s.replace('管理','')
    businesses={canonical(b) for b in header['business_labels'] if canonical(b) in canonical(task)}
    if not lanes or not businesses:return hold('请补充图内业务事项和角色泳道（或“输出成果”列），以便摘录对应图框，避免混入其他职责。')
    selected=[r for r in records if (meta:=r.get('native_flow_node')) and meta['chart_id']==header['chart_id'] and
              meta['phase']==phase and meta['lane'] in lanes and canonical(meta['business']) in businesses]
    present={(canonical(r['native_flow_node']['business']),r['native_flow_node']['lane']) for r in selected}
    if present!={(business,lane) for business in businesses for lane in lanes}:
        return hold('所问阶段、业务和角色未取得完整对应图框；本次未改用其他图或其他角色代答，也不据此认定原件没有相关要求。')
    if len(selected)>8 or sum(len(r['text']) for r in selected)>5000:return hold('所问图框超出本次完整引用范围，请进一步限定业务事项或角色，未截取部分冒充完整答复。')
    audit['frame_ids']=[r['evidence_id'] for r in selected]
    return {'candidate_evidence':[{**r,'answer_usage':'PRIMARY'} for r in selected],
            'bundle_status':'PRIMARY_SECTION_CANDIDATE','native_flow_audit':audit}


def frame_answer(result):
    primary=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
    if not primary or not all(c.get('native_flow_node') for c in primary):return None
    scopes={(c['native_flow_node']['chart_id'],c['native_flow_node']['phase']) for c in primary}
    if len(scopes)!=1:return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','answer':'当前图框未唯一限定同一张图及同一节点阶段，请补充范围。','generation_mode':'NO_GENERATION'}
    meta=primary[0]['native_flow_node']
    answer=f'附件{meta["appendix"]}（从{meta["chart_start"]}开始），节点所在阶段：{meta["phase"]}。\n'
    answer+='\n'.join(f'{c["native_flow_node"]["business"]}／{c["native_flow_node"]["lane"]}：\n'+
        c['native_flow_node']['text']+f' [{c["citation_id"]}]' for c in primary)
    return {**result,'answer_status':'SOURCE_EXTRACT','answer':answer,'status_label':'流程图框原文 · 待业务核对',
        'generation_mode':'NATIVE_FLOW_FRAME_NO_MODEL','notice':'仅摘录指定图框，未根据图框次序推断流程先后或审批关系。'}
