"""Project-bound area facts from retrieved primary evidence, never stored answers."""
import hashlib
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from app.retrieval.named_source_scope import named_titles
from .concise_extract import clean


METRICS=('地上建筑面积','地下建筑面积','计容建筑面积','单体建筑面积','总建筑面积','建筑面积','用地面积','占地面积')
METRIC='|'.join(METRICS)
UNITS=r'(?P<scale>亿|万)?\s*(?P<unit>平方米|平米|㎡|m²|m2|公顷)'
AREA=re.compile(r'(?P<phase>[一二三四五六七八九十]+期)?(?P<metric>'+METRIC+r')[：:\s|]*(?P<qualifier>(?:(?:暂估|暂定|预计|大约|约|为|是)\s*)*)(?P<value>[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*'+UNITS)
INTRO=re.compile(r'^([^，,。；;：:\n]{1,100}?项目)(?=[，,。；;：:]|$)')
CASE=re.compile(r'^案例\s*[0-9一二三四五六七八九十]+\s*[：:]?\s*$')


def key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())


def subject(question):
    q=question
    for title in named_titles(q) or []:q=q.replace('《'+title+'》','')
    names=re.findall(r'([^，,。；;：:！？?\s《》()（）]{1,100}?项目)',q)
    names=[re.sub(r'^(?:请问|请告诉我|请说明|查询一下|查询|查一下|关于|请)+','',n) for n in names]
    return names[0] if len(names)==1 and names[0] not in {'本项目','该项目','这个项目'} else None


def blocked(cards,reason):
    return {'answer_status':'EVIDENCE_INSUFFICIENT','status_label':'面积字段范围尚未核对',
            'answer':'未在同一项目和所问范围内核定该面积字段，暂不套用其他案例或其他指标的数值。',
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards], 'claims':[],
            'field_audit':{'method':'PROJECT_BOUND_AREA','reason':reason},'generation_mode':'NO_GENERATION'}


def factor(scale,unit):
    return Decimal({'':1,'万':10000,'亿':100000000}[scale or ''])*Decimal(10000 if unit=='公顷' else 1)


def area_answer(result,question):
    wanted=re.search(METRIC,question)
    if not wanted:return None
    tail=question[wanted.end():].strip(' ，,。？?：:')
    if not re.search(r'多少|多大|几|换算',question) and tail:return None
    cards=result.get('citations',[])
    if len({m[0] for m in re.finditer(METRIC,question)})!=1:return blocked(cards,'MULTIPLE_REQUESTED_AREA_FIELDS')
    if wanted[0]=='建筑面积' and re.search(r'地上|地下|计容|单体',question):return blocked(cards,'UNBOUND_AREA_SUBSCOPE')
    if re.search(r'比较|对比|合计|总和|相差|差额|平均|占比|不含|扣除|增加|减少|变化|增量|上限|下限|调整前|调整后|(?:19|20)\d{2}年',question):
        return blocked(cards,'UNSUPPORTED_COMPARISON_OR_EXTRA_CONDITION')
    name=subject(question)
    if not name:return blocked(cards,'PROJECT_NAME_NOT_UNIQUE_OR_MISSING')
    phases=set(re.findall(r'[一二三四五六七八九十]+期',question))
    requested=list(re.finditer(UNITS,question))
    if len(requested)>1:return blocked(cards,'MULTIPLE_REQUESTED_UNITS')
    facts=[]
    for c in cards:
        if c.get('answer_usage')!='PRIMARY':continue
        path=Path(c.get('source_path',''))
        try:raw=path.read_bytes()
        except OSError:continue
        if hashlib.sha256(raw).hexdigest()!=c.get('source_version'):continue
        lines=c['excerpt'].splitlines();texts=[clean(line) for line in lines]
        intros={i:m[1] for i,t in enumerate(texts) if (m:=INTRO.match(t)) and m[1] not in {'本项目','该项目','此项目'}}
        starts=[i for i,n in intros.items() if key(n)==key(name)]
        if not starts and not intros and key(name) in key(c.get('file_name','')):
            starts=[0]
        for start in starts:
            end=next((i for i in range(start+1,len(lines)) if i in intros or CASE.match(texts[i])),len(lines))
            case=next((texts[i] for i in range(start-1,-1,-1) if CASE.match(texts[i])),'')
            for i in range(start,end):
                for match in AREA.finditer(texts[i]):
                    allowed={wanted[0]} if wanted[0]!='建筑面积' else {'建筑面积','总建筑面积'}
                    if match['metric'] not in allowed:continue
                    names=re.findall(r'([^，,。；;：:！？?\s《》()（）]{1,100}?项目)',texts[i])
                    named=[n for n in names if n not in {'本项目','该项目','此项目','建设项目','施工项目','设计项目','EPC项目'}
                           and not re.fullmatch(r'(?:其中|该|本|其)?[一二三四五六七八九十]+期项目',n)]
                    if any(key(n)!=key(name) for n in named):continue
                    nearest_phase=re.search(r'([一二三四五六七八九十]+期)(?:项目)?[^，,。；;]{0,12}$',texts[i][:match.start('metric')])
                    local_phases={match['phase']} if match['phase'] else ({nearest_phase[1]} if nearest_phase else set())
                    local_phases.update(re.findall(r'[一二三四五六七八九十]+期',intros.get(start,'')))
                    if phases and phases!=local_phases:continue
                    suffix=texts[i][match.end():].lstrip()
                    note=re.match(r'(?:（[^（）]{1,100}）|\([^()]{1,100}\))',suffix)
                    condition=note[0] if note else ''
                    remainder=texts[i]
                    extra_notes=[t for t in texts[i+1:end] if re.search(r'面积|^注[：:]|^备注',t)]
                    # Unbound extra qualifications must not be silently discarded.
                    if re.search(r'但|仅|不含|不包括|暂估|暂定',remainder.replace(match[0],'').replace(condition,'')) or any(re.search(r'但|仅|不含|不包括|暂估|暂定',t) for t in extra_notes):
                        continue
                    raw_qualifier=re.sub(r'\s+|为|是','',match['qualifier'])
                    value=Decimal(match['value'].replace(',',''))
                    base=value*factor(match['scale'],match['unit'])
                    scale=match['scale'] or '';unit=match['unit']
                    if requested:
                        scale=requested[0]['scale'] or '';unit=requested[0]['unit']
                        value=base/factor(scale,unit)
                    unit='公顷' if unit=='公顷' else '平方米'
                    number=format(value.normalize(),'f')
                    label=(match['phase'] or (next(iter(local_phases)) if len(local_phases)==1 else ''))+match['metric']
                    excerpt='\n'.join(lines[start:i+1])
                    location=dict(c.get('location') or {})
                    if path.suffix.lower()=='.md':
                        content=raw.decode('utf-8-sig').replace('\r\n','\n')
                        offset=content.find(excerpt)
                        if offset<0:continue
                        location.update(line_start=content[:offset].count('\n')+1,line_end=content[:offset].count('\n')+1+excerpt.count('\n'))
                    anchor=re.match(r'\[/body/p\[@paraId=([A-Za-z0-9]+)\]\]',lines[i])
                    if anchor:location['paragraph_anchor']=anchor[1]
                    citation={**c,'excerpt':excerpt,'location':location,'parent_location':c.get('location'),
                              'display_location':' > '.join(filter(None,[c.get('display_location'),case,name,label]))}
                    facts.append({'text':f'{name}，{label}{raw_qualifier}{number}{scale}{unit}{condition}。',
                                  'citation':citation,'identity':(match['metric'],tuple(sorted(local_phases)),str(base.normalize()),raw_qualifier,condition),
                                  'raw_value':match['value'],'raw_unit':(match['scale'] or '')+match['unit'],'qualifier':raw_qualifier,
                                  'parent_evidence_id':c.get('evidence_id')})
    if not facts:return blocked(cards,'NO_PROJECT_BOUND_FIELD_WITH_EXPLICIT_UNIT')
    if len({f['identity'] for f in facts})!=1:return blocked(cards,'CONFLICTING_PROJECT_FIELD_VALUES')
    fact=facts[0];citation=fact['citation']
    return {'answer_status':'SOURCE_EXTRACT','status_label':'项目面积字段答复 · 待业务核对',
            'answer':fact['text']+' ['+citation['citation_id']+']','citations':[citation],
            'generation_mode':'LOCAL_PROJECT_AREA_FIELD_NO_MODEL','answer_completeness':'SOURCE_FIELD_SCOPE_ONLY',
            'field_audit':{'method':'PROJECT_BOUND_AREA','project':name,'metric':wanted[0],
                           **{k:fact[k] for k in ['raw_value','raw_unit','qualifier','parent_evidence_id']}},
            'notice':'按同版主证据中的项目和面积字段提取，保留原文近似值及范围；展开引用核对对应段落。未调用生成模型。'}
