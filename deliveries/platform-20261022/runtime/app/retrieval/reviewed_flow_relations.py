"""Bounded native connector lookups; a drawn arrow is not an approval or timing rule."""
import hashlib,json,re
from pathlib import Path
import pymupdf
from app.ingestion.pdf_flow_paths import direct_paths
from app.retrieval.named_source_scope import named_titles,path_key
from app.retrieval.clean_text_overlay import sha
from app.retrieval.table_schema import PDF_READ_LOCK

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def load_index(folder,flow_hash,records):
    folder=Path(folder);m=read(folder/'manifest.json');flow=Path(m['flowchart_folder'])
    if m['flowchart_manifest_sha256']!=flow_hash or sha(flow/'manifest.json')!=flow_hash:raise ValueError('Reviewed arrows belong to another flowchart layer')
    if set(m['artifact_sha256'])!={'graphs.json','relations.json','head_register_61.json'} or any(sha(folder/n)!=h for n,h in m['artifact_sha256'].items()):raise ValueError('Reviewed arrow artifact changed')
    base=read(flow/'manifest.json')
    if sha(flow/'charts.json')!=base['artifact_sha256']['charts.json']:raise ValueError('Reviewed chart provenance changed')
    charts=read(flow/'charts.json');expected=[];documents={}
    with PDF_READ_LOCK:
        try:
            for c in charts:
                spec=c['spec'];key=(spec['source_path'],spec['source_version'])
                if key not in documents:
                    raw=Path(key[0]).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=key[1]:raise ValueError('Reviewed arrow original changed')
                    documents[key]=pymupdf.open(stream=raw,filetype='pdf')
                expected.append({'page':spec['page'],'heads':direct_paths(c,documents[key][spec['page']-1].get_drawings())})
        finally:
            for d in documents.values():d.close()
    if expected!=read(folder/'graphs.json'):raise ValueError('Reviewed arrows differ from native original paths')
    nodes={r['evidence_id']:r for r in records if r.get('native_flow_node')};pairs={};expected_pairs={}
    for chart in expected:
        for head in chart['heads']:
            if head['status'] not in {'EXPLICIT_NATIVE_PATHS','DUPLICATE_NATIVE_HEAD'}:raise ValueError('Unreviewed arrow remains')
            for p in head.get('paths',[]):expected_pairs.setdefault((chart['page'],p['source_node_id'],p['target_node_id']),[]).append({'head_seqno':head['head_seqno'],'tip':head['tip'],'base':head['base'],'color':head['color'],**p})
    edges=read(folder/'relations.json')
    for edge in edges:
        key=(edge['page'],edge['source_node_id'],edge['target_node_id'])
        if key in pairs or key not in expected_pairs or edge['native_paths']!=expected_pairs[key]:raise ValueError('Duplicate or unbound reviewed arrow')
        for sid in (edge['source_node_id'],edge['target_node_id']):
            r=nodes.get(sid)
            if not r or r['native_flow_node']['chart_id']!=edge['chart_id'] or r['source_version']!=edge['source_version'] or path_key(r['source_path'])!=path_key(edge['source_path']):raise ValueError('Arrow endpoint outside admitted source')
        pairs[key]=edge
    if set(pairs)!=set(expected_pairs) or len(pairs)!=m['direct_relations']:raise ValueError('Reviewed native arrows incomplete')
    register=read(folder/'head_register_61.json')
    wanted={(c['spec']['page'],r['head_seqno']) for c in charts for r in c['held_arrows']}
    if {(r['page'],r['head_seqno']) for r in register}!=wanted or len(register)!=61 or not all(r['reviewed_visual'] for r in register):raise ValueError('Pending arrow register not reviewed')
    return {'manifest_sha256':sha(folder/'manifest.json'),'relations':edges,'direct_relations':len(edges),'pending_head_records_reviewed':61,'unique_pending_heads':44,'duplicate_pending_heads':17,'pending_head_records_held':0,'new_vectors':0,'business_semantics_inferred':False}

def direction_intent(task):
    # Classify drawing direction, never chronological or approval semantics.
    task=re.sub(r'[“「].*?[”」]', '', task)
    directions=set()
    for part in re.split(r'[，,；;。？！?]|并且|同时|以及|又',task):
        pointer=r'哪些(?:图框|角色|岗位)(?:的)?(?:箭头|连线)?(?:直接)?指向(?:它|本图框|该图框|这个图框)?|指向[^，,；;。？！?]{0,30}的图框有哪些'
        incoming=bool(re.search(pointer,part) or re.search(r'连入|连进|连过来|入向|(?:箭头|连线).{0,8}(?:来自|来源|起点|从.{0,8}来)|(?:接收|收到|进入).{0,20}(?:箭头|连线)',part))
        remainder=re.sub(pointer,'',part)
        outgoing=bool(re.search(r'指向|连向|连到|连出|出向|接到|通向|(?:箭头|连线).{0,8}(?:终点|去向)|去哪里|往哪',remainder))
        if incoming:directions.add('INCOMING')
        if outgoing:directions.add('OUTGOING')
    if not directions and re.search(r'有哪些(?:直接)?(?:箭头|连线)|(?:箭头|连线)(?:都)?有哪些|列出[^，,；;。？！?]{0,15}(?:箭头|连线)',task):return 'BOTH'
    return 'BOTH' if len(directions)==2 else next(iter(directions)) if directions else 'UNKNOWN'


def relation_bundle(question,records,index):
    if not index:return None
    def hold(message,frames=()):
        return {'candidate_evidence':[{**r,'answer_usage':'BACKGROUND'} for r in frames],'bundle_status':'SOURCE_SCOPE_MISSING','scope_mismatch_message':message,
                'native_flow_audit':{'method':'REVIEWED_EXPLICIT_NATIVE_ARROWS','relations_used':False,'clarification_message':message}}
    task=question
    for title in named_titles(question) or []:task=task.replace('《'+title+'》','')
    if not re.search(r'箭头|连线|连入|连出|连到|连向|连进|连过来',task):return None
    if re.search(r'顺序|先后|之前|之后|最先|下一步|随后|接着|必须|审批权限|批准|生效|现行|完整流程|全部流程|整个流程|所有流程|多久|几天|为什么|原因|所有路径|传递|间接|不指向|没有|未连|不连|未指|不包括|无需|不需要|不应|能否|是否|指向.*吗|连线.*吗',task):return None
    direction=direction_intent(task)
    neutral=re.sub(r'哪些图框的箭头(?:直接)?指向|哪些图框(?:的连线)?(?:直接)?指向|箭头(?:直接)?指向哪些图框|连线(?:直接)?指向哪些图框|(?:箭头|连线|直接连到|直接连入|直接|指向|图框|哪些|谁)','',question)
    from app.retrieval.native_flowcharts import frame_bundle
    selected=frame_bundle(neutral,records)
    if selected is None:return None
    if selected['bundle_status']!='PRIMARY_SECTION_CANDIDATE':return selected
    frames=selected['candidate_evidence']
    if len(frames)>1:
        quotes=re.findall(r'[“「](.{4,100}?)[”」]',task)
        exact=[r for r in frames if any(re.sub(r'\s+','',q) in re.sub(r'\s+','',r['native_flow_node']['text']) for q in quotes)]
        if len(exact)==1:frames=exact
    if len(frames)!=1:return hold('该阶段、业务和角色对应多个图框，请补充所指图框的原文。未把同泳道不同图框的连线混合。',frames)
    frame=frames[0]
    try:current=sha(frame['source_path'])
    except OSError:current=None
    if current!=frame['source_version']:return hold('流程图原件版本已变化或不可读取，本次停止使用旧连线；请更新并复核原件版本。')
    sid=frame['evidence_id'];byid={r['evidence_id']:r for r in records if r.get('native_flow_node')}
    if direction=='UNKNOWN':return hold('请明确要查连入这个图框的来源、它指向的目标，还是两个方向；未默认按出向答复。',[frame])
    requested=['INCOMING','OUTGOING'] if direction=='BOTH' else [direction]
    edges=[];missing=[]
    for which in requested:
        key='target_node_id' if which=='INCOMING' else 'source_node_id'
        group=[{**e,'query_direction':which} for e in index['relations'] if e[key]==sid]
        if not group:missing.append(which)
        edges.extend(group)
    if not edges or len(edges)>8:return hold('当前已核直接连线不足以在本次范围内完整答复，请限定具体图框或结合原图核对；未据此认定原图没有连接。',[frame])
    cards=[]
    for e in edges:
        source,target=byid[e['source_node_id']],byid[e['target_node_id']];s,t=source['native_flow_node'],target['native_flow_node']
        points=[p for path in e['native_paths'] for seg in path['path_items'] for p in seg]+[e['native_paths'][0]['tip']]
        box=[min([s['bbox'][0],t['bbox'][0]]+[p[0] for p in points]),min([s['bbox'][1],t['bbox'][1]]+[p[1] for p in points]),max([s['bbox'][2],t['bbox'][2]]+[p[0] for p in points]),max([s['bbox'][3],t['bbox'][3]]+[p[1] for p in points])]
        text=f'原图绘制的直接箭头（不代表审批权限）：\n起点图框：{s["phase"]}／{s["business"]}／{s["lane"]}：'+s['text']+f'\n终点图框：{t["phase"]}／{t["business"]}／{t["lane"]}：'+t['text']
        cards.append({**source,'evidence_id':'reviewed-flow-edge-'+hashlib.sha256((e['source_version']+e['source_node_id']+e['target_node_id']).encode()).hexdigest(),
            'text':text,'answer_usage':'PRIMARY','location':{'page':e['page'],'bbox':box},'display_location':f'PDF第{e["page"]}页 · 附件{e["appendix"]} · 已核直接箭头',
            'native_flow_node':None,'native_flow_relation':{'source':s,'target':t,'direction':e['query_direction'],'requested_direction':direction,'unverified_directions':missing,'queried_node_id':sid,'head_seqnos':[p['head_seqno'] for p in e['native_paths']],'path_seqnos':[p['path_seqno'] for p in e['native_paths']],'manifest_sha256':index['manifest_sha256']}})
    return {'candidate_evidence':cards,'bundle_status':'PRIMARY_SECTION_CANDIDATE','native_flow_audit':{'method':'REVIEWED_EXPLICIT_NATIVE_ARROWS','relations_used':True,'transitive_relations_used':False,'arrow_count':len(cards)},'retrieval_audit':{'method':'VERIFIED_NATIVE_FLOW_PATH','new_embeddings':0,'reranker_pairs':0}}

def relation_answer(result):
    rows=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
    if not rows or not all(c.get('native_flow_relation') for c in rows):return None
    scopes={(c['source_path'],c['source_version'],c['native_flow_relation']['queried_node_id'],c['native_flow_relation'].get('requested_direction',c['native_flow_relation']['direction'])) for c in rows}
    if len(scopes)!=1:return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','answer':'连线尚未唯一限定同一原图和图框，未合并答复。','generation_mode':'NO_GENERATION'}
    m=rows[0]['native_flow_relation'];incoming=m['direction']=='INCOMING';n=m['target'] if incoming else m['source']
    answer=f'所查图框：{n["phase"]}／{n["business"]}／{n["lane"]}：“'+''.join(n['text'].split())+'”。'
    requested=m.get('requested_direction',m['direction']);directions=['INCOMING','OUTGOING'] if requested=='BOTH' else [requested]
    for which in directions:
        selected=[c for c in rows if c['native_flow_relation']['direction']==which]
        answer+='\n'+('图上直接连入它的图框：' if which=='INCOMING' else '图上箭头直接指向：')
        if not selected:
            answer+='本次已核原始路径中未取得足以完整列出的关系，暂不据此认定没有连接。'
        for i,c in enumerate(selected,1):
            n=c['native_flow_relation']['source' if which=='INCOMING' else 'target']
            answer+=f'\n{i}. {n["phase"]}／{n["business"]}／{n["lane"]}：“'+''.join(n['text'].split())+f'”。[{c["citation_id"]}]'
    return {**result,'answer_status':'SOURCE_EXTRACT','status_label':'原图直接连线 · 待业务核对','answer':answer,'generation_mode':'NATIVE_FLOW_RELATION_NO_MODEL',
        **({'answer_completeness':'PARTIAL','coverage_gaps':['尚未完整核定'+d+'方向' for d in m.get('unverified_directions',[])]} if m.get('unverified_directions') else {}),
        'notice':'仅依据完整原始折线和箭头说明直接绘制方向；未推断必须先后、审批权限、共享干线的传递关系或完整业务流程。'}
