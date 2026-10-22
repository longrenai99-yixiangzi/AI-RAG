"""Answer only simple lists/options grounded in a retrieved native layout region."""
from __future__ import annotations

import re

from app.ingestion.atomic_search import query_terms
from app.ingestion.layout_evidence import compact

NUMBERS = dict(zip('一二三四五六七八九十',range(1,11)))


def normalize(text):
    return re.sub(r'[\s\d、，。,:：.>\-]', '', text).replace('初设','初步设计').replace('施工图阶段','施工图设计阶段')


def layout_proposal(question, plan, records):
    if plan.get('project') or re.search(r'以及|同时|分别.*多少|并且|另外|及其|并(?:说明|给出|比较)|和.*[？?]',question):
        return None
    count = re.search(r'([一二三四五六七八九十\d]+)\s*(?:大|个|项|条)?\s*(?:方面|模块|维度|要点)',question)
    required = (int(count[1]) if count[1].isdigit() else NUMBERS.get(count[1],0)) if count else 0
    candidates = []
    for record in records:
        layout = record.get('layout') or {}
        kind = layout.get('kind')
        items = [item['text'] for item in layout.get('items',[])]
        if kind not in {'list_group','comparison_options'} or len(items)<2 or len(set(items)) != len(items):
            continue
        native = compact(layout.get('source_context') or record['text'])
        if any(compact(item) not in native for item in items):
            continue
        context = layout.get('context','')
        if any(specialty not in context and specialty not in native for specialty in plan.get('specialty') or []):
            continue
        q, heading = normalize(question), normalize(record['heading_path'])
        if kind == 'comparison_options':
            if not any(word in question for word in ['比选','方案','选型']):
                continue
            subject = re.sub(r'选型|设计|方案|比选|分析|对比','',normalize(layout['label']))
            if len(subject)<2 or subject not in q:
                continue
            target=re.search(r'(.+?)(?:选型|方案比选|比选)',q)
            if target:
                requested=re.sub(r'^(?:这份|本例|该|这个|请问|请列出|请|关于)+','',target[1])
                requested=re.sub(r'设备$','',requested)
                if requested != subject:
                    continue
        else:
            if not required and not (any(word in question for word in ['模块','哪些方面','哪些维度']) or ('要点' in question and any(word in question for word in ['哪些','什么','列出']))):
                continue
            if required and len(items)!=required:
                continue
            if '模块' in question and '模块' not in layout['label']:
                continue
            if layout.get('region_count',1)>1 and '要点' in question and '要点' not in layout['label']:
                continue
            requested_stages = set(re.findall(r'方案设计|初步设计|施工图设计|深化设计',q))
            source_stages = set(re.findall(r'方案设计|初步设计|施工图设计|深化设计',heading))
            if requested_stages and source_stages and requested_stages.isdisjoint(source_stages):
                continue
            terms = [t for t in query_terms(question) if not t.isdigit() and t not in {'方面','模块','要点','哪些','三个','四大','五个','列出'}]
            hits = sum(normalize(term) in normalize(layout.get('source_context','')+' '+context+' '+layout['label']) for term in terms)
            if terms and hits/max(1,len(terms)) < .5:
                continue
        score = 10*(normalize(layout['label']) in q)+sum(term in heading for term in query_terms(question))
        candidates.append((score,record,items))
    if not candidates:
        return None
    candidates.sort(key=lambda item:(-item[0],item[1]['evidence_id']))
    if len(candidates)>1 and candidates[0][0]==candidates[1][0] and candidates[0][2]!=candidates[1][2]:
        return None
    _, record, items = candidates[0]
    return {'record':record,'items':items,'text':record['heading_path']+'：\n'+'\n'.join(f'{i}. {text}' for i,text in enumerate(items,1))}


def layout_count_mismatch(question, plan, records):
    count=re.search(r'(?:哪|哪些)\s*([一二三四五六七八九十\d]+)\s*(?:个|项|条)?\s*(方面|模块|维度|要点)',question)
    if not count:
        return None
    requested=int(count[1]) if count[1].isdigit() else NUMBERS.get(count[1],0)
    proposal=layout_proposal(question[:count.start()]+'有哪些'+count[2]+question[count.end():],plan,records)
    if proposal and requested!=len(proposal['items']):
        proposal['count_mismatch']=f'原文此栏列出{len(proposal["items"])}项，题目要求{requested}项；不能补造缺少的项。'
        return proposal
    return None


def render_layout(bundle):
    from app.verified_answer_engine_v2 import _answer, _claim

    if bundle.get('bundle_status') in {'SOURCE_SCOPE_MISSING','CONFLICTING_EVIDENCE','LINEAGE_BLOCKED'}:
        return None
    by_id = bundle.get('layout_source_records') or {}
    retrieved = {str(item['evidence_id']):item for item in bundle.get('candidate_evidence',[])}
    records=[r for key,r in by_id.items() if key in retrieved]
    proposal = layout_proposal(bundle['question'],bundle.get('query_plan') or {},records) or layout_count_mismatch(bundle['question'],bundle.get('query_plan') or {},records)
    if not proposal:
        return None
    source = proposal['record']
    evidence = {**retrieved[source['evidence_id']],**{key:source[key] for key in ('source_path','source_version','file_name','location','text','raw_text','heading_path')},'role':'DIRECT'}
    # This branch handles one list/option request, never a compound factual question.
    grounded = {**bundle,'bundle_status':'VERIFIED','candidate_evidence':[evidence],'verified_evidence':[evidence],
                'subquestions':[bundle['question']],'coverage_map':[{'subquestion_id':'SQ1','subquestion':bundle['question'],'coverage_status':'COVERED'}],
                'conflicting_evidence':[],'supporting_evidence':[]}
    claim = _claim('C1','DIRECT','SQ1',proposal['text'],[source['evidence_id']],raw_evidence_text=source['text'])
    claims=[claim]
    if proposal.get('count_mismatch'):
        grounded['coverage_map'][0]['coverage_status']='EVIDENCE_INSUFFICIENT'
        claims.append(_claim('C2','LIMITATION','SQ1',proposal['count_mismatch'],[source['evidence_id']]))
    answer = _answer(grounded,'PARTIAL_ANSWER' if proposal.get('count_mismatch') else 'ANSWERED',claims,[])
    answer['generation_mode'] = 'NATIVE_LAYOUT_ISOLATED_TRIAL'
    answer['answer_trace'].update({'gold_runtime_injection':0,'requires_owner_review':True,'native_items':proposal['items']})
    return answer
