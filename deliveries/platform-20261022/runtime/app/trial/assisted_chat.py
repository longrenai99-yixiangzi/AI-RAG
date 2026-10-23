"""Colleague-style stages on the existing V2 backend, with existing schema/citations."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Literal

from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,ConfigDict,Field
from starlette.background import BackgroundTask

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle,EvidenceItem
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
from app.answer_engine.llm.boundary_note_recovery import recover_body,project_partial_body
from app.answer_engine.llm.claim_validator import check_source_units
from app.answer_engine.question_scope import question_scope
from app.retrieval.section_scope import mark_scope
from app.retrieval.personnel_scope import extract_answer

router=APIRouter(prefix='/api/v2/assisted',tags=['Integrated evidence and generation candidate'])
gate=threading.Lock()


class AssistedQuery(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    question:str=Field(min_length=1,max_length=2000)
    mode:Literal['answer','sources']='answer'
    trial_user:str='reviewer-001'
    conversation_id:str=Field(default='',max_length=100)
    node_id:str=Field(default='',max_length=100)
    request_id:str=Field(default_factory=lambda:uuid.uuid4().hex,pattern=r'^[a-f0-9]{32}$')


def runtime(request):
    from app.trial import v2
    retrieve=getattr(request.app.state,'assisted_retrieve',None)
    if retrieve is None:
        def retrieve(question):
            engine=v2._engine_instance()
            bundle=engine.answer(question,detect_growth=False,retrieve_only=True)
            # Use the complete frozen text, not the legacy display excerpt.
            for item in bundle.get('candidate_evidence',[]):
                raw=engine.atomic.get(item['evidence_id'],{})
                if raw.get('source_version')==item.get('source_version'):
                    item['text']=raw.get('raw_text') or raw.get('text') or item['text']
            return bundle
    store=getattr(request.app.state,'assisted_store',v2.KNOWLEDGE_STORE)
    generator=getattr(request.app.state,'assisted_generator',None)
    if generator is None:generator=ShadowAnswerGenerator(UnavailableLLMProvider('本候选尚未启用真实模型调用。'))
    return retrieve,store,generator


def assemble(bundle,question=None,include_background=False):
    items=[];cards=[];seen=set();versions={}
    candidates=bundle.get('candidate_evidence',[])
    if question:candidates=mark_scope(question,candidates)
    for candidate in candidates:
        if not include_background and candidate.get('answer_usage') in {'BACKGROUND','UNRESOLVED'}:continue
        if candidate.get('role') not in {'DIRECT','SUPPORTING'}:continue
        if candidate.get('registration_page_flag') or candidate.get('query_page_flag') or candidate.get('system_evidence'):continue
        if any(candidate.get('scope',{}).get(k)=='MISMATCH' for k in ('project','organization','year','period','specialty','design_stage')):continue
        path=Path(candidate.get('source_path') or '');version=candidate.get('source_version') or ''
        if not re.fullmatch(r'[a-fA-F0-9]{64}',version):continue
        key=(str(path),version)
        if key not in versions:
            try:versions[key]=hashlib.sha256(path.read_bytes()).hexdigest()==version
            except OSError:versions[key]=False
        if not versions[key]:continue
        text=candidate.get('text') or '';identity=(str(path),version,text)
        if not text.strip() or identity in seen:continue
        seen.add(identity);sid='S'+str(len(items)+1)
        item=EvidenceItem(source_id=sid,chunk_id=candidate['evidence_id'],document_id=candidate['document_id'],file_name=path.name,source_path=str(path),
                          document_role=candidate.get('document_role') or '原始资料',authority_level=candidate.get('authority_level') or 'UNKNOWN',usage_scene='按来源原文回答，效力及业务真实性另核',
                          location=candidate.get('location') or {},excerpt=text,retrieval_score=float(candidate.get('score') or 0),selection_score=0,evidence_status='SOURCE_VERSION_MATCHED_CLAIM_NOT_REVIEWED')
        items.append(item)
        cards.append({'citation_id':sid,'evidence_id':candidate['evidence_id'],'source_id':candidate.get('source_id') or candidate['document_id'],
                      'source_version':version,'file_name':path.name,'source_path':str(path),'location':item.location,'display_location':candidate.get('display_location') or candidate.get('heading_path') or '位置见原文','excerpt':text,'answer_usage':candidate.get('answer_usage','UNCLASSIFIED')})
        if candidate.get('chapter_coverage'):cards[-1]['chapter_coverage']=candidate['chapter_coverage']
        if len(items)==8:break
    return EvidenceBundle(items=items,status='EVIDENCE_READY' if items else 'NO_EVIDENCE'),cards


def run_flow(data,retrieve,generator,save,resolved_question=None):
    started=time.perf_counter();qid='Q_'+data.request_id;run_id='QR_'+data.request_id
    resolved_question=resolved_question or data.question
    base={'query_id':qid,'query_run_id':run_id,'question':data.question,'resolved_question':resolved_question,'response_mode':data.mode,
          'pipeline_version':'COLLEAGUE_FLOW_EXISTING_V2_CANDIDATE','growth_candidate_ids':[],'claims':[],'citations':[],'debug':{},'latency':{'total_ms':0}}
    scope_hint=question_scope(data.question)
    if scope_hint:base['question_scope']=scope_hint
    state={**base,'conversation_id':data.conversation_id,'node_id':data.node_id,'trial_user':data.trial_user,'status':'RUNNING','created_at':datetime.now(timezone.utc).isoformat()}
    save(run_id,state)
    finished=False
    try:
        yield {'type':'status','stage':'retrieval','msg':'正在检索已有知识库。','query_run_id':run_id}
        bundle=retrieve(resolved_question);evidence,cards=assemble(bundle,resolved_question,include_background=data.mode=='sources')
        yield {'type':'sources','sources':cards,'query_run_id':run_id}
        result={**base,'citations':cards,'debug':{k:bundle[k] for k in ('candidate_hash','bundle_status','scope_resolution','source_scope','reference_resolution','coverage_audit','chapter_coverage','intent_audit','personnel_scope_audit','selection_notes','ranking_audit','retrieval_audit') if k in bundle}}
        if bundle.get('reference_resolution'):result['source_resolution_note']='本题由登记卡关联到同版原件；引用来自原件，登记卡未被补写为正文，内容与适用范围仍待核对。'
        blocked=bundle.get('bundle_status') in {'SOURCE_SCOPE_MISSING','LINEAGE_BLOCKED','CONFLICTING_EVIDENCE'}
        if not evidence.items or blocked:
            result.update(answer_status='EVIDENCE_INSUFFICIENT',status_label='证据范围不足',answer='本次没有取得足以组织回答的同版证据。已返回的片段仅供查阅，不能据此认定原库没有资料。')
            if bundle.get('selection_notes'):result['failure_message']='；'.join(bundle['selection_notes'])
        elif bundle.get('scalar_answer') is not None:
            scalar=bundle['scalar_answer']
            ids={c['evidence_id']:c['citation_id'] for c in cards}
            direct=[c for c in scalar['claims'] if c['claim_type']=='DIRECT']
            if direct and all(eid in ids for c in direct for eid in c['evidence_ids']):
                result.update(answer_status='SOURCE_EXTRACT_DRAFT',status_label='数值摘录与单位换算 · 待核对',
                              answer=scalar['answer_text'],generation_mode='VERIFIED_SCALAR_NO_MODEL',
                              claims=[{**c,'evidence_ids':[ids[eid] for eid in c['evidence_ids']]} for c in direct])
            else:
                for c in cards:c['answer_usage']='BACKGROUND'
                result.update(answer_status='EVIDENCE_INSUFFICIENT',status_label='数值证据范围不足',
                              answer='当前同版证据未核验所问金额指标、单位或条件，不能借用其他金额。',generation_mode='NO_GENERATION')
        elif data.mode=='sources':
            result.update(answer_status='SOURCES_ONLY',status_label='只查原文',answer='以下为本次检索到的同版原文，尚未生成业务结论。')
        elif bundle.get('personnel_scope_audit'):
            excerpt=extract_answer(bundle,cards,resolved_question)
            result.update(excerpt or {'answer_status':'EVIDENCE_INSUFFICIENT','status_label':'原文摘录核对未通过','answer':'本次数值片段未通过原件逐字及位置核对，暂不形成回答，请查阅原文。'})
        elif not generator.provider.available:
            result.update(answer_status='MODEL_UNAVAILABLE',status_label='原文已返回 · 模型未运行',answer='本候选尚未启用真实模型回答。可查看原文；这不表示知识库没有答案。')
        else:
            yield {'type':'status','stage':'generation','msg':'证据已返回，正在由模型组织回答。','query_run_id':run_id}
            intent='METHOD_QUERY' if any(w in data.question for w in ['如何','怎么','步骤','流程']) else 'CASE_QUERY' if any(w in data.question for w in ['案例','复盘','经验']) else 'GENERAL_QUERY'
            policy=policy_for_intent(intent)
            generated=generator.generate(resolved_question,policy,evidence)
            yield {'type':'status','stage':'validation','msg':'正在核对回答结构与引用绑定；这不等于业务结论已审核。','query_run_id':run_id}
            v2=getattr(generator,'protocol_version','V1')=='V2'
            v2_valid=v2 and generated.protocol_category=='VALID'
            v2_body=(generated.parsed_response or {}) if v2_valid else {}
            core_response=json.dumps({k:v for k,v in v2_body.items() if k!='scope_notes'},ensure_ascii=False) if v2_valid else generated.raw_llm_response
            recovery=recover_body(core_response,policy,evidence) if generated.status!='GENERATED' and not v2 else None
            partial=project_partial_body(core_response,policy,evidence) if generated.status!='GENERATED' and not recovery and (not v2 or v2_valid) else None
            processable=(generated.status=='GENERATED' and generated.validation and generated.validation.valid) or recovery or partial
            payload=(partial or recovery)['payload'] if partial or recovery else (generated.parsed_response or {})
            grounding=check_source_units(payload.get('claims',[]),evidence,allow_connector_omission=not partial) if processable and bundle.get('answer_grounding_policy')=='STRICT_SOURCE_UNITS' else None
            if grounding:result['grounding_audit']=grounding
            if v2_valid and not v2_body.get('claims') and v2_body.get('evidence_insufficient'):
                result.update(answer_status='MODEL_EVIDENCE_GAP',status_label='模型报告本题证据缺口 · 待核对',answer='模型未形成回答本题的证据主张，以下缺口仍需结合原件核对。',answer_completeness='UNANSWERED')
            elif processable and (grounding is None or grounding['valid']):
                claims=payload.get('claims',[])
                used={sid for c in claims for sid in c.get('evidence_ids',[])}
                display='\n\n'.join(f'{i}. '+c['claim_text']+' '+''.join('['+sid+']' for sid in c['evidence_ids']) for i,c in enumerate(claims,1))
                missing=payload.get('evidence_insufficient') or []
                if missing:display+='\n\n模型提出的证据缺口（是否属于本题仍待核对）：'+'；'.join(missing)
                elif not v2 and not recovery and any(not ids for ids in (payload.get('section_map') or {}).values()):display+='\n\n部分回答项尚未形成内容，请结合原文核对。'
                if recovery:display+='\n\n格式警告：正文已保留；模型的边界备注未通过格式检查，未作为已核实内容。'
                result.update(answer_status='MODEL_DRAFT_PROTOCOL_WARNING' if recovery else 'MODEL_DRAFT',status_label='模型正文草稿 · 格式待核对' if recovery else '模型回答 · 待核对',answer=display,
                              claims=[{**c,'claim_type':'MODEL_CLAIM','rendered_claim_text':c['claim_text']} for c in claims],citations=[c for c in cards if c['citation_id'] in used])
                if recovery:result.update(protocol_recovery='BODY_ONLY_ORIGINAL_SCHEMA_REJECTED',unverified_model_notes=recovery['unverified_notes'],original_schema_errors=recovery['original_schema_errors'])
                if partial:
                    result.update(answer_status='MODEL_PARTIAL_DRAFT',status_label='原文摘句 · 回答尚不完整',answer_contract_version='ASSISTED_PRESENTATION_V2',answer_completeness='PARTIAL',
                                  unresolved_aspects=partial['unresolved_aspects'],unverified_model_notes=partial['unverified_notes'],original_schema_errors=partial['original_schema_errors'],
                                  original_protocol_passed=partial['original_protocol_passed'],protocol_recovery='EXTRACTIVE_PARTIAL_PROJECTION',support_check=partial['support_check'])
            else:
                if grounding and not grounding['valid']:
                    result.update(answer_status='MODEL_GROUNDING_UNVERIFIED',status_label='回答表述尚待原文核对',answer='模型的部分表述尚未与所引原文对应；本次只展示原文线索，不据此判断这些表述必然错误。')
                else:
                    result.update(answer_status='MODEL_OUTPUT_REJECTED',status_label='模型回答未通过检查',answer='模型没有返回通过结构与引用检查的回答。原文仍可查看，未用旧答案替代本次结果。')
            if v2_valid:
                result.update(answer_contract_version='MINIMAL_ANSWER_V2_DRAFT',unverified_model_notes=list(v2_body['scope_notes']),unresolved_aspects=list(v2_body['evidence_insufficient']))
        result['latency']={'total_ms':round((time.perf_counter()-started)*1000,3)}
        save(run_id,{**state,'status':'COMPLETE','answer_status':result['answer_status'],'result':result})
        finished=True
        yield {'type':'result','result':result}
    except Exception:
        result={**base,'answer_status':'PIPELINE_ERROR','status_label':'本次处理未完成','answer':'本次检索或模型处理失败，问题已保存。不能据此判断库里没有资料。'}
        save(run_id,{**state,'status':'ERROR','result':result});finished=True;yield {'type':'result','result':result}
    finally:
        if not finished:save(run_id,{**state,'status':'INTERRUPTED','error':'连接已中断，未自动重试或续发生成请求。'})
    yield {'type':'done','query_run_id':run_id}


@router.get('/capabilities')
def capabilities(request:Request):
    generator=getattr(request.app.state,'assisted_generator',None)
    return {'protocol':'COLLEAGUE_FLOW_V1','generation_enabled':bool(generator and generator.provider.available),'model_output_streaming':False,'staged_response':True}


@router.get('/runs/{run_id}')
def saved_run(run_id:str,conversation_id:str,request:Request):
    if not re.fullmatch(r'QR_[a-f0-9]{32}',run_id):raise HTTPException(404,'未找到问题记录。')
    _,store,_=runtime(request);row=store.query_run(run_id)
    if not row or row.get('conversation_id')!=conversation_id:raise HTTPException(404,'未找到本会话的问题记录。')
    return {k:row[k] for k in ('query_run_id','question','status','result') if k in row}


@router.post('/query')
def query(data:AssistedQuery,request:Request):
    from app.trial import v2
    v2._ensure_user(data.trial_user)
    if v2.CONFIG.get('V2_VERIFIED_RAG_ENABLED') is not True:raise HTTPException(503,'V2_VERIFIED_RAG_DISABLED')
    origin=request.headers.get('origin');expected=str(request.base_url).rstrip('/')
    if request.url.hostname not in {'127.0.0.1','localhost'} or origin!=expected:raise HTTPException(403,'仅允许本机同源页面。')
    retrieve,store,generator=runtime(request);run_id='QR_'+data.request_id;prior=store.query_run(run_id)
    if prior:
        if prior.get('question')!=data.question or prior.get('conversation_id')!=data.conversation_id or prior.get('response_mode')!=data.mode:raise HTTPException(409,'请求编号已用于另一条问题。')
        if not prior.get('result'):raise HTTPException(409,'该问题仍在处理，未重复调用。')
        return StreamingResponse(iter(['data: '+json.dumps({'type':'result','result':prior['result']},ensure_ascii=False)+'\n\n']),media_type='text/event-stream')
    resolved=v2._resolve_followup(data.question,store.last_query_for_conversation(data.conversation_id))
    if not gate.acquire(blocking=False):raise HTTPException(429,'已有问题正在处理，请稍后重试。')
    def events():
        for event in run_flow(data,retrieve,generator,store.record_query,resolved):yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'},background=BackgroundTask(gate.release))
