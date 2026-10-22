"""One read-only candidate for source browsing, hybrid retrieval and answer evidence."""
from collections import Counter
import hashlib,json,re,sys,time
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi
from app.bm25 import tokenize
from app.retrieval.named_source_scope import path_key,resolve_named_scope,ranking_question,named_titles,named_document_ids
from app.retrieval.reference_bindings import linked_path,binding_current
from app.retrieval.project_source_scope import route_project_question
from app.retrieval.focused_candidate import FocusedCandidate
from app.retrieval.section_scope import SectionTitleIndex
from app.ingestion.normalization.markdown_normalizer import is_source_reference_note


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def declared_version(doc):
    versions={str(doc[k]).lower() for k in ('source_version','source_hash','content_hash','sha256') if re.fullmatch('[a-fA-F0-9]{64}',str(doc.get(k,'')))}
    return next(iter(versions)) if len(versions)==1 else None


def embedding_identity(folder):
    folder=Path(folder);h=hashlib.sha256()
    for p in sorted([*folder.glob('*.bin'),*folder.glob('*.safetensors'),folder/'config.json',folder/'tokenizer.json']):
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def effective_indices(records,documents,contract):
    """Ported from the validated Word overlay; keep older experiment snapshots immutable."""
    admitted={};reasons={}
    for did,d in documents.items():
        _,reason=contract.decision(Path(d['source_path']));version=declared_version(d)
        reasons[did]='NAVIGATION_OR_EXCLUDED' if reason in {'navigation_only','excluded_root','generated_or_navigation_note','invalid_frontmatter','missing_or_symlink'} else 'UNKNOWN_CATALOG_VERSION' if not version else None
        if not reasons[did]:admitted[did]=(path_key(d['source_path']),version)
    selected=[];seen=set();excluded=Counter()
    for i,r in enumerate(records):
        expected=admitted.get(r['document_id'])
        if not expected:excluded[reasons.get(r['document_id']) or 'MISSING_CATALOG_DOCUMENT']+=1;continue
        identity=(path_key(r['source_path']),r.get('source_version'))
        if identity!=expected:excluded['NOT_CATALOG_VERSION_OR_PATH']+=1;continue
        key=(*identity,r['evidence_id'])
        if key in seen:excluded['DUPLICATE_SAME_VERSION']+=1;continue
        seen.add(key);selected.append(i)
    return selected,dict(excluded)


class UnifiedCandidate:
    def __init__(self,folder,encoder,reranker,*,personnel_folder=None,quality_folder=None,scalar_links=None):
        started=time.perf_counter();folder=Path(folder)
        self.manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in self.manifest['artifact_sha256'].items():
            if file_sha(folder/name)!=digest:raise ValueError('Unified candidate artifact changed: '+name)
        if file_sha(self.manifest['contract_path'])!=self.manifest['contract_sha256']:raise ValueError('Source admission contract changed; revalidate this candidate')
        if getattr(encoder,'model_path',None) and embedding_identity(encoder.model_path)!=self.manifest.get('embedding_model_digest'):raise ValueError('Query encoder differs from the candidate embedding model')
        self.records=[json.loads(line) for line in (folder/'evidence.jsonl').open(encoding='utf-8') if line.strip()]
        docs=[json.loads(line) for line in (folder/'documents.jsonl').open(encoding='utf-8') if line.strip()]
        self.documents={d['document_id']:d for d in docs};self.vectors=np.load(folder/'dense_embeddings.npy',mmap_mode='r')
        sparse=json.loads((folder/'bm25.json').read_text(encoding='utf-8'))
        ids=[r['evidence_id'] for r in self.records]
        if ids!=sparse['chunk_ids'] or len(set(ids))!=len(ids):raise ValueError('Evidence/BM25 row identity mismatch')
        if self.vectors.shape!=(len(ids),1024) or not np.isfinite(self.vectors).all() or not np.allclose(np.linalg.norm(self.vectors,axis=1),1,atol=.003):raise ValueError('Invalid vector alignment or normalization')
        paths={p:path_key(p) for p in {r['source_path'] for r in self.records}|{d['source_path'] for d in docs}}
        versions={did:(paths[d['source_path']],declared_version(d)) for did,d in self.documents.items()}
        for r in self.records:
            if (paths[r['source_path']],r['source_version'])!=versions[r['document_id']]:raise ValueError('Evidence and catalog versions disagree')
        self.bm25=BM25Okapi([[sys.intern(t) for t in tokens] for tokens in sparse['corpus']]);del sparse
        sections=json.loads((folder/'sections.json').read_text(encoding='utf-8'))
        self.scope_documents=dict(self.documents)
        self.encoder=encoder;self.focused=FocusedCandidate(sections,SectionTitleIndex(sections),reranker,documents=self.scope_documents)
        self.candidate_hash=self.manifest['candidate_hash'];self.by_path={};self.by_source={}
        source_ids={}
        for i,r in enumerate(self.records):
            key=(paths[r['source_path']],r['source_version'])
            sid=source_ids.setdefault(key,'SRC_'+hashlib.sha256('|'.join(key).encode()).hexdigest()[:24])
            r['lineage_source_id']=r.get('source_id');r['source_id']=sid
            self.by_path.setdefault(key[0],[]).append(i)
            self.by_source.setdefault(sid,[]).append(i)
        self.personnel=None
        if personnel_folder is not None:
            from app.retrieval.personnel_scope import PersonnelIndex
            self.personnel=PersonnelIndex(personnel_folder,self.candidate_hash,source_ids)
        self.reference_only=set()
        for path,version in source_ids:
            if Path(path).suffix.lower() not in {'.md','.markdown'}:continue
            try:
                raw=Path(path).read_bytes()
                if hashlib.sha256(raw).hexdigest()==version and is_source_reference_note(raw.decode('utf-8-sig')):self.reference_only.add(path)
            except (OSError,UnicodeError):continue
        self.quality_exclusions={};self.reference_bindings={}
        if quality_folder is not None:
            quality=json.loads((Path(quality_folder)/'manifest.json').read_text(encoding='utf-8'))
            if quality['base_candidate_hash']!=self.candidate_hash:raise ValueError('Evidence quality belongs to another candidate')
            if any(file_sha(p)!=h for p,h in quality['proof_sha256'].items()):raise ValueError('Evidence quality proof changed')
            indexed={r['evidence_id']:r for r in self.records}
            for entry in quality['exclusions']:
                record=indexed.get(entry['evidence_id'])
                if not record or any(record[k]!=entry[k] for k in ('source_path','source_version')):raise ValueError('Evidence quality source binding differs')
                if entry['evidence_id'] in self.quality_exclusions:raise ValueError('Duplicate evidence quality exclusion')
                self.quality_exclusions[entry['evidence_id']]=entry['reason']
            for entry in quality.get('reference_bindings',[]):
                note_key=(path_key(entry['note_path']),entry['note_version']);body_key=(path_key(entry['body_path']),entry['body_version'])
                body=self.documents.get(entry['body_document_id'])
                if note_key not in source_ids or body_key not in source_ids or not body or (path_key(body['source_path']),declared_version(body))!=body_key:raise ValueError('Reference body is outside the admitted candidate')
                if note_key[0] not in self.reference_only or body_key[0] in self.reference_only or entry['linked_version']!=entry['body_version']:raise ValueError('Reference note/body type or version differs')
                target=linked_path(Path(entry['note_path']).read_text(encoding='utf-8-sig'))
                if target is None or path_key(target)!=path_key(entry['linked_path']) or not binding_current(entry):raise ValueError('Reference link or current files differ')
                sid=source_ids[note_key]
                if sid in self.reference_bindings:raise ValueError('Duplicate reference binding')
                self.reference_bindings[sid]={**entry,'body_source_id':source_ids[body_key]}
                for did,doc in self.documents.items():
                    if (path_key(doc['source_path']),declared_version(doc))==note_key:self.scope_documents[did]={**body,'file_name':doc['file_name'],'reference_note_path':doc['source_path']}
        self.scalar_links=scalar_links or {}
        for md,link in self.scalar_links.items():
            # A derived duplicate can be excluded while its original remains admitted.
            pairs=((md,link['markdown_sha256']),(link['original_path'],link['original_sha256']))
            if not any((path_key(p),version) in source_ids for p,version in pairs):raise ValueError('Scalar scope is outside the admitted candidate')
        self.load_ms=round((time.perf_counter()-started)*1000,2)

    def sources(self,query='',file_type='',offset=0,limit=50):
        rows=[]
        for sid,indices in self.by_source.items():
            r=self.records[indices[0]]
            if query.casefold() not in (r['file_name']+' '+r['source_path']).casefold():continue
            if file_type and r.get('file_type')!=file_type:continue
            personnel_count=sum(p['source_id']==sid for p in self.personnel.records) if self.personnel else 0
            binding=self.reference_bindings.get(sid);current=bool(binding and binding_current(binding))
            rows.append({'source_id':sid,'file_name':r['file_name'],'source_path':r['source_path'],'file_type':r.get('file_type') or Path(r['source_path']).suffix,
                         'source_type':'离线候选来源','body_status':'仅原件链接' if path_key(r['source_path']) in self.reference_only else 'PARSED','index_status':'离线候选','current_hash':r['source_version'],'chunk_count':len(indices)+personnel_count,
                         'approval_status':'ISOLATED_READ_ONLY','version_note':'该Markdown只有来源链接与关联导航，本候选尚未取得该文件正文，不能作为业务回答依据。' if path_key(r['source_path']) in self.reference_only else '候选索引版本，建包时已核对原件；后续变更须重核，事实与效力未验收'})
            if binding:
                linked_count=len(self.by_source[binding['body_source_id']])+(sum(p['source_id']==binding['body_source_id'] for p in self.personnel.records) if self.personnel else 0)
                rows[-1].update(body_status='已关联原件 · 正文待核' if current else '关联版本待核对',linked_source_id=binding['body_source_id'],chunk_count=linked_count,
                                version_note=f'本条是登记卡，已关联原件《{Path(binding["body_path"]).name}》，正文版本{binding["body_version"][:12]}。预览和问答引用来自原件；不代表正文质量与业务内容已经验收。' if current else '登记卡、链接目标或候选原件版本已变；暂不沿用旧关联正文。')
        rows.sort(key=lambda r:(r['file_name'],r['source_id']))
        return {'items':rows[offset:offset+limit],'total':len(rows),'candidate_hash':self.candidate_hash,**({'personnel_index_sha256':self.personnel.manifest['records_sha256']} if self.personnel else {})}

    def source_evidence(self,source_id,limit=12):
        binding=self.reference_bindings.get(source_id)
        if binding:
            if not binding_current(binding):return {'items':[],'candidate_hash':self.candidate_hash,'reference_resolution':binding,'failure_message':'关联版本已变，不能沿用旧原件正文。'}
            return {**self.source_evidence(binding['body_source_id'],limit),'reference_resolution':binding}
        rows=[r for r in self.personnel.records if r['source_id']==source_id] if self.personnel else []
        rows += [self.records[i] for i in self.by_source.get(source_id,[])]
        return {'items':[{'evidence_id':r['evidence_id'],'source_version':r['source_version'],'heading_path':r.get('heading_path'),'location':r.get('location') or {},'raw_text':r['text'],'excerpt':r['text'],**({'answer_exclusion_reason':self.quality_exclusions[r['evidence_id']]} if r['evidence_id'] in self.quality_exclusions else {})} for r in rows[:limit]], 'candidate_hash':self.candidate_hash,**({'personnel_index_sha256':self.personnel.manifest['records_sha256']} if self.personnel else {})}

    def retrieve(self,question,query_vector=None):
        start=time.perf_counter()
        named_paths={path_key(self.documents[did]['source_path']) for title in named_titles(question) or [] for did in named_document_ids(self.documents,title)}
        bindings=[b for b in self.reference_bindings.values() if path_key(b['note_path']) in named_paths]
        reference_meta={'reference_resolution':bindings} if bindings else {}
        if any(not binding_current(b) for b in bindings):return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING','candidate_hash':self.candidate_hash,**reference_meta,'selection_notes':['登记卡、链接目标或原件版本已变，停止使用旧关联；不能据此认为原库没有资料。']}
        route=route_project_question(question,self.scope_documents);routed=route['question']
        if route['status'] in {'AMBIGUOUS_PROJECT_SELECTOR','SOURCE_SCOPE_MISSING','CONFLICTING_EVIDENCE'}:
            return {'candidate_evidence':[],'bundle_status':'CONFLICTING_EVIDENCE' if route['status']=='CONFLICTING_EVIDENCE' else 'SOURCE_SCOPE_MISSING','scope_resolution':route,'candidate_hash':self.candidate_hash}
        scope=resolve_named_scope(routed,self.scope_documents);allowed=scope['allowed_paths']
        if allowed is not None and not allowed:return {'candidate_evidence':[],'bundle_status':scope['status'],'source_scope':scope,'candidate_hash':self.candidate_hash}
        mask=list(range(len(self.records))) if allowed is None else sorted({i for p in allowed for i in self.by_path.get(p,[])})
        if not mask:return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING','candidate_hash':self.candidate_hash}
        reference_rows={i for i in mask if path_key(self.records[i]['source_path']) in self.reference_only or self.records[i]['evidence_id'] in self.quality_exclusions}
        if len(reference_rows)==len(mask):
            return {'candidate_evidence':[{**self.records[i],'role':'DIRECT','answer_usage':'BACKGROUND'} for i in sorted(reference_rows)[:8]],'bundle_status':'SOURCE_SCOPE_MISSING','candidate_hash':self.candidate_hash,
                    'selection_notes':['所指定资料只有来源链接，或片段解析质量尚未通过核对；本候选没有可用的正文证据。仍可查阅来源线索，不能据此认定原件不存在。']}
        mask=[i for i in mask if i not in reference_rows]
        from app.retrieval.scalar_bridge import matching_links,scope_paths,scalar_bundle
        scalar_links=matching_links(question,self.scalar_links)
        if scalar_links:
            scalar_paths=scope_paths(scalar_links)
            mask=[i for i in mask if path_key(self.records[i]['source_path']) in scalar_paths]
            if not mask:return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING','candidate_hash':self.candidate_hash}
        task=ranking_question(routed,self.scope_documents)
        scoped=self.personnel.lookup(task,allowed) if self.personnel else None
        uncovered=bool(scoped is not None and allowed and len(set(allowed))==1 and allowed[0] not in self.personnel.by_path)
        if scoped is not None and not uncovered:
            scoped.update(candidate_hash=self.candidate_hash,scope_resolution=route,answer_grounding_policy='STRICT_SOURCE_UNITS',retrieval_audit={'method':'NATIVE_PERSONNEL_SCOPE_FIELDS','new_embeddings':0,'total_ms':round((time.perf_counter()-start)*1000,2)},**reference_meta)
            return scoped
        vector=np.asarray(query_vector if query_vector is not None else self.encoder.embed_query(task),dtype=np.float32)
        if vector.shape!=(1024,) or not np.isfinite(vector).all() or np.linalg.norm(vector)==0:raise ValueError('Invalid query vector')
        vector=vector/np.linalg.norm(vector);sparse=self.bm25.get_scores(tokenize(task));dense=self.vectors@vector;fusion={}
        for values in (sparse,dense):
            for rank,i in enumerate(sorted(mask,key=lambda i:(-values[i],i)),1):fusion[i]=fusion.get(i,0)+1/(60+rank)
        order=sorted(fusion,key=lambda i:(-fusion[i],i))[:60 if scalar_links else 20]
        recalled=[{**self.records[i],'role':'DIRECT','score':fusion[i]} for i in order]
        if scalar_links:
            bundle=scalar_bundle(question,recalled,scalar_links)
            bundle.update(candidate_hash=self.candidate_hash,scope_resolution=route,**reference_meta,
                          retrieval_audit={'method':'EXISTING_VERSIONED_TEXT_SCALAR','eligible_rows':len(mask),'recalled_ids':[r['evidence_id'] for r in recalled],'new_document_embeddings':0,'total_ms':round((time.perf_counter()-start)*1000,2)})
            return bundle
        bundle=self.focused.rank(routed,recalled)
        if uncovered:
            bundle.update(bundle_status='SOURCE_SCOPE_MISSING',personnel_scope_audit=scoped['personnel_scope_audit'],selection_notes=scoped['selection_notes'])
            for r in bundle['candidate_evidence']:r['answer_usage']='BACKGROUND'
        bundle.update(candidate_hash=self.candidate_hash,scope_resolution=route,answer_grounding_policy='STRICT_SOURCE_UNITS',**reference_meta,
                      retrieval_audit={'eligible_rows':len(mask),'recalled_ids':[r['evidence_id'] for r in recalled],'query_text_sha256':hashlib.sha256(task.encode()).hexdigest(),'total_ms':round((time.perf_counter()-start)*1000,2)})
        return bundle
