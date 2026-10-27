"""Link existing same-section rows and track explicit parallel lookup topics."""
import hashlib
import re
import unicodedata

from app.retrieval.named_source_scope import path_key
from app.retrieval.query_planner_v1 import _parallel_fact_subquestions
from app.retrieval.section_scope import mark_scope


def focus(question):
    value=re.split(r'(?:有)?(?:哪些|什么|如何|怎么|怎样|是否|哪几)',question,maxsplit=1)[0]
    value=value.rsplit('的',1)[-1].strip(' ？?；;，,。')
    value=re.sub(r'(?:应当|应该|应|需要|需|是|有)$','',value)
    # Predicate-only ellipses are not independent noun topics; keep the original question intact.
    if re.fullmatch(r'(?:应当|应该|需要|需|应|可以|可|能够|能|必须)?(?:重点|主要)?(?:关注|把控|控制|承担|负责|包括|包含|明确|保留|考虑|由)',value):return ''
    if value.startswith('设计') and len(value[2:])>=4:value=value[2:]
    if value.endswith('管理') and len(value[:-2])>=4:value=value[:-2]
    return value if len(value)>=2 and value not in {'管理流程','流程','内容','要求','管理','工作'} else ''


def parallel_facets(question):
    # Keep existing numeric, comparison and reasoning protections; do not infer those with row matches.
    if re.search(r'多少|几人|几位|人数|金额|费用|合计|统计|计算|占比|差额|比较|对比|区别|变化|为什么|为何|原因|是否|能否|如何|怎么|怎样',question):return []
    units=[p.strip() for p in re.split(r'[？?；;]+',question) if p.strip()]
    if len(units)<2:units=_parallel_fact_subquestions(question)
    if len(units)<2:return []
    result=[{'question':p,'topic':focus(p)} for p in units]
    return result if all(p['topic'] for p in result) else []


def intro_only(text):
    lines=[re.sub(r'^\[/body/p\[@paraId=[A-Za-z0-9]+\]\]\s*','',p).strip() for p in text.splitlines() if p.strip()]
    return bool(lines) and all(re.search(r'(?:如下|见下表|详见下表)[：:。]?$' ,p) for p in lines)


def table_row(text):
    headers=[p.split('：',1)[1].split('|') for p in text.splitlines() if p.startswith('表头：')]
    values=[p.split('：',1)[1].split('|') for p in text.splitlines() if p.startswith('行：')]
    if len(headers)!=1 or len(values)!=1 or len(headers[0])!=len(values[0]) or len(headers[0])<2:return None
    headers=[p.strip() for p in headers[0]];values=[p.strip() for p in values[0]]
    if not all(headers) or headers==values:return None
    return {'headers':headers,'values':values}


def topic_present(topic,candidate):
    if not topic or intro_only(candidate['text']):return False
    norm=lambda value:re.sub(r'[ \t\u3000]+','',unicodedata.normalize('NFKC',value))
    topic=norm(topic);row=table_row(candidate['text'])
    if row:
        unknown=lambda value:bool(re.match(r'^(?:未明确|未提供|暂无|不详|未知|待补充|待完善|待核实)',value))
        payload=any(len(norm(v))>=4 and topic not in norm(v) and not unknown(v) and not re.fullmatch(r'[\d\W]+',v) for v in row['values'])
        return payload and any(topic in norm(v) and not unknown(v) for v in row['values']) or any(topic in norm(h) and len(v)>=4 and not unknown(v) for h,v in zip(row['headers'],row['values']))
    if candidate.get('table_id') or any(p.startswith(('表头：','行：')) for p in candidate['text'].splitlines()):return False
    # Title-only matches cannot establish a requested aspect of the answer.
    return topic in norm(candidate['text'])


def associate_section(question,seed,ranked,records):
    facets=parallel_facets(question)
    if len(facets)>8:return [],{'status':'TOO_MANY_FACETS'},None
    topics=[p['topic'] for p in facets] or [focus(question)]
    identity=(path_key(seed['source_path']),seed['source_version'])
    heading=seed.get('heading_path')
    same=[r for r in records if heading and r.get('heading_path')==heading and (path_key(r['source_path']),r['source_version'])==identity]
    linked=[];seen=set();repeated_headers=0
    for r in mark_scope(question,same):
        if not r.get('table_id') or 'MISMATCH' in r.get('scope',{}).values():continue
        row=table_row(r['text'])
        if not row:
            repeated_headers+=1;continue
        if not any(topic_present(p,r) for p in topics):continue
        key=(r['table_id'],tuple(row['headers']),tuple(row['values']))
        if key in seen:continue
        seen.add(key)
        names=[p.split('：',1)[1] for p in r['text'].splitlines() if p.startswith('表名：')]
        label='；'.join(f'{h}={v}' for h,v in list(zip(row['headers'],row['values']))[:2])
        linked.append({**r,'role':'DIRECT','table_evidence':row,'retrieval_origin':'SAME_SECTION_TABLE_ROW',
            'display_location':' > '.join(filter(None,[heading,names[0] if names else '原表',label])),
            'table_association':{'seed_evidence_id':seed['evidence_id'],'same_source_version_section':True,
                                 'case_source':bool(re.search(r'EPC设计管理经验总结\(',unicodedata.normalize('NFKC',r.get('file_name',''))))}})
    audit={'status':'NOT_APPLICABLE','linked_rows':len(linked),'rejected_header_or_invalid_rows':repeated_headers,'section_path':heading}
    invalid_seed_row=bool(seed.get('table_id') and not table_row(seed['text']))
    if not facets and not linked and not intro_only(seed['text']) and not invalid_seed_row:return None,audit,None
    if linked and (len(linked)>8 or any(len(r['text'])>800 for r in linked) or sum(len(r['text']) for r in linked)>1600):
        return [],{**audit,'status':'TABLE_CONTEXT_LIMIT_EXCEEDED'},None
    audit['status']='SAME_SECTION_ROWS_LINKED' if linked else 'NO_MATCHING_SECTION_ROW'
    pool=linked+[r for r in ranked if (path_key(r['source_path']),r['source_version'])==identity and not intro_only(r['text'])]
    selected=[];coverage=None
    if facets:
        for facet in facets:
            matches=[r for r in pool if topic_present(facet['topic'],r)]
            # shortcut: one complete candidate per explicit lookup topic, not semantic completeness proof.
            chosen=matches[:1]
            facet.update(status='TOPIC_LOCATED' if chosen else 'NOT_LOCATED',evidence_ids=[r['evidence_id'] for r in chosen])
            selected.extend(chosen)
        coverage={'question_sha256':hashlib.sha256(question.encode()).hexdigest(),'facets':facets,
                  'status':'PARTIAL' if any(p['status']=='NOT_LOCATED' for p in facets) else 'TOPICS_LOCATED_NOT_SEMANTICALLY_VERIFIED'}
    else:selected=linked
    selected=[dict(r) for r in {r['evidence_id']:r for r in selected}.values()]
    if len(selected)>8 or sum(len(r['text']) for r in selected)>6000:return [],{**audit,'status':'EVIDENCE_CONTEXT_LIMIT_EXCEEDED'},coverage
    for r in selected:
        r['answer_usage']='PRIMARY'
        if r.get('table_id'):
            r['table_evidence']=table_row(r['text'])
            if not r.get('table_association'):
                r['table_association']={'seed_evidence_id':seed['evidence_id'],'same_source_version_section':r.get('heading_path')==heading,
                    'case_source':bool(re.search(r'EPC设计管理经验总结\(',unicodedata.normalize('NFKC',r.get('file_name',''))))}
        if coverage:r['facet_coverage']=coverage
    return selected,audit,coverage


def facet_gaps(audit,used_evidence_ids=None):
    return [f'子问“{p["topic"]}”尚未核定，不能用其他方面的内容代答。' for p in (audit or {}).get('facets',[])
            if p['status']=='NOT_LOCATED' or used_evidence_ids is not None and not set(p['evidence_ids']).intersection(used_evidence_ids)]


def table_fields_text(row):
    return '；'.join(f'{h}：{v or "[空白]"}' for h,v in zip(row['headers'],row['values'])).rstrip('。；')+'。'


def citation_facets(citations,question):
    audits=[c['facet_coverage'] for c in citations if c.get('answer_usage')=='PRIMARY' and c.get('facet_coverage')]
    if not audits:return None
    if any(a!=audits[0] for a in audits) or audits[0]['question_sha256']!=hashlib.sha256(question.encode()).hexdigest():
        raise ValueError('并列子问核对记录与本题不一致。')
    return audits[0]


def case_notice(citations):
    return '以下为所引项目复盘中的案例做法：\n' if any(c.get('table_association',{}).get('case_source') for c in citations if c.get('answer_usage')=='PRIMARY') else ''
