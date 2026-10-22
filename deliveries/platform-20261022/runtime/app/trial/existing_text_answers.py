"""Isolated reuse of retrieved Markdown and already indexed layout children."""
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import re

from app.ingestion.layout_evidence import compact, identity
from app.ingestion.scalar_evidence import ALIASES, VALUE, _fact
from app.scalar_answers import render_scalars
from app.layout_answers import render_layout, NUMBERS

TEXT_ALIASES={**ALIASES,'合同造价':'合同金额','总价':'合同金额','总造价':'工程造价','中标金额':'中标金额','中标价':'中标金额','招标控制价':'招标控制价'}
TEXT_LABEL='|'.join(re.escape(v) for v in sorted(TEXT_ALIASES,key=len,reverse=True))
TEXT_MONEY=re.compile(rf'(?P<label>{TEXT_LABEL})(?:共计|合计|为|是|[：:\s|])*(?P<qualifier>暂估|暂定|预计|估算|约)?(?:为|是|[：:\s|])*(?P<value>{VALUE})\s*(?P<unit>亿元|万元|元|亿|万|W)(?![A-Za-z方㎡%])')


def _current_markdown(candidate, cache):
    path=Path(candidate.get('source_path') or '')
    if path.suffix.lower()!='.md' or not candidate.get('source_version'):
        return None
    key=(str(path),candidate['source_version'])
    if key not in cache:
        try:
            raw=path.read_bytes()
            cache[key]=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n') if hashlib.sha256(raw).hexdigest()==key[1] else None
        except (OSError,UnicodeError):cache[key]=None
    text=cache[key]
    return text if text and candidate.get('text') and candidate['text'] in text else None


def _clean_line(line):
    return re.sub(r'^\[/body/p\[[^\n]*?\]\]\s*','',line).strip()


def _render_layout(grounded):
    answer=render_layout(grounded)
    if answer is None:return None
    direct={eid for claim in answer['claims'] if claim['claim_type']=='DIRECT' for eid in claim['evidence_ids']}
    cited={c['evidence_id'] for c in answer['citations']}
    grounded['candidate_evidence']=[{**r,'role':'DIRECT' if r['evidence_id'] in direct else 'CONTEXT_ONLY'} for r in grounded['candidate_evidence'] if r['evidence_id'] in cited]
    grounded['verified_evidence']=[r for r in grounded['candidate_evidence'] if r['role']=='DIRECT']
    complete=answer['answer_status']=='ANSWERED'
    grounded['bundle_status']='VERIFIED' if complete else 'VERIFIED_PARTIAL'
    grounded['coverage_map']=[{'subquestion_id':'SQ1','subquestion':grounded['question'],'coverage_status':'COVERED' if complete else 'EVIDENCE_INSUFFICIENT'}]
    return answer


def _lists(candidate, full_text):
    result=[]
    for line in candidate['text'].splitlines():
        clean=_clean_line(line)
        markers=list(re.finditer(r'([一二三四五六七八九十])是',clean))
        if len(markers)>=2 and [NUMBERS[m[1]] for m in markers]==list(range(1,len(markers)+1)):
            label=clean[:markers[0].start()].strip('其：: ')
            items=[clean[m.end():markers[i+1].start() if i+1<len(markers) else len(clean)].strip('。；; ') for i,m in enumerate(markers)]
        else:
            match=re.search(r'(?:包括|包含)([一二三四五六七八九十])大(板块|模块)[：:](.+)',clean)
            if not match:continue
            label='模块';items=[p.strip('。；; ') for p in re.split(r'、|以及',match[3])]
            if len(items)!=NUMBERS[match[1]]:continue
        if not label or len(items)<2 or any(not item for item in items):continue
        offset=full_text.find(line)
        if offset<0:continue
        result.append({**candidate,'evidence_id':identity(candidate['evidence_id'],label,line),'derived_from_evidence_id':candidate['evidence_id'],
                       'location':{**candidate.get('location',{}),'markdown_line':full_text[:offset].count('\n')+1},
                       'layout':{'kind':'list_group','label':label,'context':candidate['text'],'source_context':candidate['text'],
                                 'region_count':2,'items':[{'text':item} for item in items]}})
    return result


def render_existing(bundle, source_links, *, recalled_parents=(), indexed_layouts=()):
    """Only use retrieved admitted text; a link carries scope/provenance, never answers."""
    if re.search(r'相差|差额|合计|汇总|平均|占比|最终结算|是否已',bundle['question']):return None
    cache={};scalars={};layouts={};verified_sources={};candidates=bundle.get('candidate_evidence') or []
    originals={link['original_path']:link for link in source_links.values()}
    recalled_parents=tuple(recalled_parents)[:60]
    plan=bundle.get('query_plan') or {}
    if plan.get('project') and not any(plan.get(k) for k in ('organization','year','period')):
        by_id={c['evidence_id']:c for c in candidates}
        for parent in recalled_parents:
            if parent['evidence_id'] not in by_id:by_id[parent['evidence_id']]={**parent,'role':'CONTEXT_ONLY'}
        candidates=list(by_id.values())
    for candidate in candidates:
        if candidate.get('role') in {'EXCLUDED','CONFLICTING'}:continue
        if any(candidate.get('scope',{}).get(field)=='MISMATCH' for field in ('organization','project','year','period','specialty')):continue
        path=candidate['source_path'];markdown=Path(path).suffix.lower()=='.md'
        full=_current_markdown(candidate,cache) if markdown else candidate.get('text')
        if not full:continue
        link=source_links.get(path) if markdown else originals.get(path)
        version_key='markdown_sha256' if markdown else 'original_sha256'
        if link and link[version_key]==candidate['source_version']:
            original=Path(link['original_path'])
            source_key=(str(original),link['original_sha256'])
            if source_key not in verified_sources:
                try:verified_sources[source_key]=hashlib.sha256(original.read_bytes()).hexdigest()==source_key[1]
                except OSError:verified_sources[source_key]=False
            if not verified_sources[source_key]:continue
            config={'scope':link['scope']}
            for line in candidate['text'].splitlines():
                clean=compact(_clean_line(line))
                for match in TEXT_MONEY.finditer(clean):
                    # Object-specific savings need a row/object relation, not a naked amount.
                    metric=TEXT_ALIASES[match['label']]
                    if metric=='创效金额':continue
                    if match['label']=='总价':
                        if not re.search(r'合同(?:价格|价款)?形式.{0,24}总价合同',compact(candidate['text'])):continue
                        if match.start() and re.match(r'[\u3400-\u9fffA-Za-z]',clean[match.start()-1]):continue
                    if metric=='合同金额' and re.search(r'(?:自营|自施|分包|分项)$',clean[:match.start()]):continue
                    if re.match(r'/(?:㎡|m[²2]|平方米)|每(?:㎡|m[²2]|平方米)',clean[match.end():],re.I):continue
                    subject=re.search(r'(桩基|基坑支护|基坑|支护|土建|安装|钢结构|幕墙|装饰|分项|分部)$',clean[:match.start()])
                    offset=full.find(line)
                    if offset<0:continue
                    location={**candidate.get('location',{})}
                    if markdown:location['markdown_line']=full[:offset].count('\n')+1
                    else:
                        page=re.fullmatch(r'(Slide|Page)\s+(\d+)',candidate.get('heading_path',''))
                        if page:location['slide' if page[1]=='Slide' else 'page']=int(page[2])
                    parent={**candidate,'location':location}
                    unit={'亿':'亿元','万':'万元'}.get(match['unit'],match['unit'])
                    fact=_fact(parent,config,metric,match['value'],unit,raw_metric=match['label'],subject=subject[1] if subject else '')
                    fact['scalar']['raw_unit']=match['unit']
                    if unit in {'元','万元','亿元'}:
                        fact['scalar']['value']=format((Decimal(fact['scalar']['value'])*{'元':1,'万元':10000,'亿元':100000000}[unit]).normalize(),'f')
                        fact['scalar']['unit']='元'
                    qualifier=re.match(r'[（(]([^（）()]*)[）)]',clean[match.end():])
                    fact['scalar']['qualifier']='；'.join(v for v in [match['qualifier'],qualifier[1] if qualifier else ''] if v)
                    fact['derived_from_evidence_id']=candidate['evidence_id']
                    scalars[fact['evidence_id']]=fact
        if markdown:
            for record in _lists(candidate,full):layouts[record['evidence_id']]=record
    if scalars:
        grounded={**deepcopy(bundle),'scalar_source_records':scalars,
                  'candidate_evidence':[{**r,'role':'CONTEXT_ONLY'} for r in scalars.values()]}
        answer=render_scalars(grounded)
        if answer is not None:
            answer['generation_mode']='EXISTING_TEXT_SCALAR_ISOLATED'
            return answer,grounded
    if layouts:
        grounded={**deepcopy(bundle),'layout_source_records':layouts,
                  'candidate_evidence':[{**r,'role':'CONTEXT_ONLY'} for r in layouts.values()]}
        answer=_render_layout(grounded)
        if answer is not None:
            answer['generation_mode']='EXISTING_MARKDOWN_LIST_ISOLATED'
            return answer,grounded
    # shortcut: expand within the measured top-60 recall window only; tune on new questions before rollout.
    verified_versions={}
    for parent in recalled_parents:
        location=parent.get('location') or {}
        page=location.get('slide') or location.get('page')
        if not page:
            kind='Slide' if Path(parent['source_path']).suffix.lower()=='.pptx' else 'Page'
            match=re.fullmatch(kind+r'\s+(\d+)',parent.get('heading_path',''))
            page=int(match[1]) if match else None
        if not page:continue
        for child in indexed_layouts:
            loc=child.get('location') or {}
            if (child['source_path'],child['source_version'],loc.get('slide') or loc.get('page'))!=(parent['source_path'],parent['source_version'],page):continue
            if child.get('layout',{}).get('kind') not in {'list_group','comparison_options'}:continue
            version=(child['source_path'],child['source_version'])
            if version not in verified_versions:
                try:verified_versions[version]=hashlib.sha256(Path(version[0]).read_bytes()).hexdigest()==version[1]
                except OSError:verified_versions[version]=False
            if not verified_versions[version]:continue
            layouts[child['evidence_id']]=child
    if layouts:
        grounded={**deepcopy(bundle),'layout_source_records':layouts,
                  'candidate_evidence':[{**r,'role':'CONTEXT_ONLY'} for r in layouts.values()]}
        answer=_render_layout(grounded)
        if answer is not None:
            answer['generation_mode']='EXISTING_INDEXED_LAYOUT_PARENT_EXPANSION'
            return answer,grounded
    return None
