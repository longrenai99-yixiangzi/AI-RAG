"""Resolve scalar requests from retrieved source-bound facts; no question/answer registry."""
from __future__ import annotations

from decimal import Decimal
import re

from app.ingestion.layout_evidence import compact
from app.ingestion.scalar_evidence import phases, project_key, requested_metrics
from app.retrieval.query_planner_v1 import plan_query


def packages(text):
    values=[]
    for token in re.findall(r'标包[（(]?([0-9一二三四五六七八九十]+)',text):
        if token.isdigit():values.append(int(token));continue
        digits={c:i for i,c in enumerate('零一二三四五六七八九')}
        if '十' in token:
            left,right=token.split('十',1);values.append((digits.get(left,1))*10+digits.get(right,0))
        else:values.append(digits.get(token))
    return set(values)


def scalar_proposal(question, records):
    metrics = requested_metrics(question)
    if not metrics or not re.search(r'多少|几天|金额|费用|总投资',question):
        return None
    if re.search(r'原因|为什么|如何|比例|多少项|以及.*(?:谁|何时)',question):
        return None
    key = project_key(question)
    scoped = [r for r in records if any(project_key(a) and project_key(a) in key for a in r['source_scope']['aliases'])]
    plan=plan_query(question)
    named=plan.project or plan.entities
    if named:
        exact=[r for r in scoped if all(any(project_key(p)==project_key(a) for a in r['source_scope']['aliases']) for p in named)]
        if scoped and not exact:
            return {'facts':[],'reference':scoped[0],'missing':['所问具体项目名称未与来源匹配，不能只凭同名片段借用数值。'],'scope_missing':True}
        scoped=exact
    if not scoped:
        return None
    wanted_phases = phases(question)
    matched_scope = [r for r in scoped if (not wanted_phases or wanted_phases == set(r['source_scope'].get('phases') or [])) and (not packages(question) or packages(question)==set(r['source_scope'].get('packages') or []))]
    if not matched_scope:
        return {'facts':[],'reference':scoped[0],'missing':['所问项目期别或标包未与原文一致，不能借用其他范围的数值。'],'scope_missing':True}
    results=[];missing=['负责人：本轮标量证据未核验该字段。'] if '负责人' in question else []
    reference=matched_scope[0]
    subject_query = re.sub(r'提前(?:多少|几)天|提前', '', compact(question))
    for metric in metrics:
        candidates = [r for r in matched_scope if r['scalar']['metric'] == metric and (not r['scalar']['subject'] or r['scalar']['subject'] in subject_query)]
        if not candidates:
            missing.append(metric+'：本轮接入范围尚未定位所问对象的这一指标。');continue
        reference=candidates[0]
        if any(r['scalar']['unit_status']=='UNRESOLVED' for r in candidates):
            missing.append(metric+'：原文单位未明确，不能套用其他行的单位确认。');continue
        identities = {(r['scalar']['value'],r['scalar']['unit'],r['scalar']['subject']) for r in candidates}
        if len(identities)>1:
            missing.append(metric+'：同一范围出现不同数值，暂不替用户裁定。');continue
        source = candidates[0];fact = source['scalar'];value=Decimal(fact['value']);unit=fact['unit']
        asked_unit = next((u for u in ['亿元','万元','元'] if u in question),None)
        if asked_unit and unit in {'亿元','万元','元'}:
            scale={'元':Decimal(1),'万元':Decimal(10000),'亿元':Decimal(100000000)}
            value=value*scale[unit]/scale[asked_unit];unit=asked_unit
        number=format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')
        text=(fact['subject']+'，' if fact['subject'] else '')+metric+'为'+number+unit+'。'
        if fact.get('qualifier'):
            text+='原文条件：'+fact['qualifier']+'。'
        if fact['unit_confirmation']:
            text+='原表写作'+fact['raw_value']+fact['raw_unit']+'，仅按该来源该单元格的既有确认换算。'
        results.append({'record':source,'text':text,'metric':metric,'value':str(value),'unit':unit})
    return {'facts':results,'reference':reference,'missing':missing,'scope_missing':False}


def render_scalars(bundle):
    from app.verified_answer_engine_v2 import _answer,_claim
    if bundle.get('bundle_status') in {'CONFLICTING_EVIDENCE','LINEAGE_BLOCKED'}:
        return None
    retrieved={str(r['evidence_id']):r for r in bundle.get('candidate_evidence',[])}
    records=[r for key,r in (bundle.get('scalar_source_records') or {}).items() if key in retrieved]
    proposal=scalar_proposal(bundle['question'],records)
    if proposal is None:
        return None
    selected=[f['record'] for f in proposal['facts']] or [proposal['reference']]
    with_reference={r['evidence_id']:r for r in [*selected,proposal['reference']]}
    fact_ids={f['record']['evidence_id'] for f in proposal['facts']}
    evidence=[{**retrieved[r['evidence_id']],**r,'role':'DIRECT' if r['evidence_id'] in fact_ids else 'CONTEXT_ONLY'} for r in with_reference.values()]
    status='SOURCE_SCOPE_MISSING' if proposal['scope_missing'] else ('PARTIAL_ANSWER' if proposal['missing'] else 'ANSWERED')
    questions=[f['metric'] for f in proposal['facts']]+proposal['missing']
    grounded={**bundle,'bundle_status':'SOURCE_SCOPE_MISSING' if proposal['scope_missing'] else ('VERIFIED_PARTIAL' if proposal['missing'] else 'VERIFIED'),
              'candidate_evidence':evidence,'verified_evidence':evidence if proposal['facts'] else [],'supporting_evidence':[],
              'conflicting_evidence':[],'subquestions':questions,
              'coverage_map':[{'subquestion_id':f'SQ{i}','subquestion':q,'coverage_status':'COVERED' if i<=len(proposal['facts']) else 'EVIDENCE_INSUFFICIENT'} for i,q in enumerate(questions,1)]}
    claims=[_claim(f'C{i}','DIRECT',f'SQ{i}',f['text'],[f['record']['evidence_id']],raw_evidence_text=f['record']['text']) for i,f in enumerate(proposal['facts'],1)]
    for message in proposal['missing']:
        i=len(claims)+1;claims.append(_claim(f'C{i}','LIMITATION',f'SQ{i}',message,[proposal['reference']['evidence_id']],raw_evidence_text=message))
    if proposal['reference'].get('source_scope',{}).get('source_anomaly'):
        claims.append(_claim(f'C{len(claims)+1}','LIMITATION','SOURCE_NOTE',proposal['reference']['source_scope']['source_anomaly'],[selected[0]['evidence_id']]))
    # The caller must validate against the same source-bound roles and coverage.
    bundle.update(grounded)
    answer=_answer(bundle,status,claims,[])
    answer['generation_mode']='NATIVE_SCALAR_ISOLATED_TRIAL'
    answer['answer_trace'].update({'requires_owner_review':True,'native_scalar_facts':[{'metric':f['metric'],'value':f['value'],'unit':f['unit'],'source_version':f['record']['source_version'],'location':f['record']['location']} for f in proposal['facts']]})
    return answer
