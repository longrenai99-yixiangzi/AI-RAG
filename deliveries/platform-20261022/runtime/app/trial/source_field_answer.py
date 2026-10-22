"""Project-bound fields from retrieved primary evidence, never stored answers."""
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


def project_blocks(card, name):
    if card.get('answer_usage')!='PRIMARY':return
    path=Path(card.get('source_path',''))
    try:raw=path.read_bytes()
    except OSError:return
    if hashlib.sha256(raw).hexdigest()!=card.get('source_version'):return
    lines=card['excerpt'].splitlines();texts=[clean(line) for line in lines]
    intros={i:m[1] for i,t in enumerate(texts) if (m:=INTRO.match(t)) and m[1] not in {'本项目','该项目','此项目'}}
    starts=[i for i,n in intros.items() if key(n)==key(name)]
    if not starts and not intros and key(name) in key(card.get('file_name','')):starts=[0]
    for start in starts:
        end=next((i for i in range(start+1,len(lines)) if i in intros or CASE.match(texts[i])),len(lines))
        case=next((texts[i] for i in range(start-1,-1,-1) if CASE.match(texts[i])),'')
        yield {'path':path,'raw':raw,'lines':lines,'texts':texts,'start':start,'end':end,
               'intro':intros.get(start,''),'case':case}


def field_citation(card, block, index, name, label):
    excerpt='\n'.join(block['lines'][block['start']:index+1])
    location=dict(card.get('location') or {})
    if block['path'].suffix.lower()=='.md':
        try:content=block['raw'].decode('utf-8-sig').replace('\r\n','\n')
        except UnicodeError:return None
        offset=content.find(excerpt)
        if offset<0:return None
        location.update(line_start=content[:offset].count('\n')+1,line_end=content[:offset].count('\n')+1+excerpt.count('\n'))
    anchor=re.match(r'\[/body/p\[@paraId=([A-Za-z0-9]+)\]\]',block['lines'][index])
    if anchor:location['paragraph_anchor']=anchor[1]
    return {**card,'excerpt':excerpt,'location':location,'parent_location':card.get('location'),
            'display_location':' > '.join(filter(None,[card.get('display_location'),block['case'],name,label]))}


def money_answer(result, question):
    from .existing_text_answers import TEXT_ALIASES, TEXT_LABEL, TEXT_MONEY
    name=subject(question)
    question_task=question.replace(name,'') if name else question
    requested=list(dict.fromkeys(TEXT_ALIASES[m[0]] for m in re.finditer(TEXT_LABEL,question_task)))
    if not requested or not re.search(r'多少|金额|费用|总投资|总价',question):return None
    if any(m in {'提前天数','创效金额'} for m in requested):return None
    if re.search(r'为什么|原因|如何|怎么|哪些|作用|区别|流程|职责|目的|内容|构成|依据|定义|谁|何时|占比|比例|美元|美金|欧元|港元|英镑|日元',question_task):return None
    cards=result.get('citations',[])

    def reject(reason):
        return {'answer_status':'EVIDENCE_INSUFFICIENT','status_label':'金额指标或适用范围尚未核定',
                'answer':'相关原文可查，但未在所问项目和范围内核定该金额指标；暂不借用其他项目、地块或金额。',
                'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards],'claims':[],
                'generation_mode':'NO_GENERATION','field_audit':{'method':'PROJECT_BOUND_MONEY','reason':reason}}

    if len(requested)!=1:return reject('MULTIPLE_MONEY_FIELDS')
    if not name:return reject('PROJECT_NAME_NOT_UNIQUE_OR_MISSING')
    phases=set(re.findall(r'[一二三四五六七八九十]+期',question))
    units=re.findall(r'亿元|万元|元',question)
    if len(units)>1:return reject('MULTIPLE_REQUESTED_UNITS')
    task=re.sub(TEXT_LABEL,'',question_task)
    task=re.sub(r'[一二三四五六七八九十]+期|亿元|万元|人民币|元|请问|请告诉我|请说明|请给出|查询一下|查询|多少|折合|换算|大约|大概|大致|总共|一共|是|为|的|有|成|钱|呢|啊|呀','',task)
    if re.sub(r'[\W_]+','',task):return reject('UNVERIFIED_CONDITION_OR_SUBSCOPE')
    factors={'元':Decimal(1),'万元':Decimal(10000),'亿元':Decimal(100000000)}
    facts=[]
    for card in cards:
        # This route reuses admitted Markdown, not reparsing native Office/PDF attachments.
        if Path(card.get('source_path','')).suffix.lower()!='.md':continue
        for block in project_blocks(card,name):
            for i in range(block['start'],block['end']):
                line=block['texts'][i]
                for match in TEXT_MONEY.finditer(line):
                    if TEXT_ALIASES[match['label']]!=requested[0] or match['unit'] not in factors:continue
                    prefix=line[:match.start()];suffix=line[match.end():]
                    clause=re.split(r'[，,。；;]',prefix)[-1]
                    if re.search(r'桩基|基坑|支护|土建|安装|钢结构|幕墙|装饰|分项|分部|地块|单体|不含|不包括|仅|扣除',clause):continue
                    if re.match(r'\s*(?:/|／|每|美元|美金|港元|欧元|日元|英镑)',suffix):continue
                    names=re.findall(r'([^，,。；;：:！？?\s《》()（）]{1,100}?项目)',line)
                    if any(key(n)!=key(name) for n in names if n not in {'本项目','该项目','此项目','建设项目','施工项目','设计项目','EPC项目'}):continue
                    phase=re.search(r'([一二三四五六七八九十]+期)(?:项目)?[^，,。；;]{0,12}$',prefix)
                    local_phases=({phase[1]} if phase else set())|set(re.findall(r'[一二三四五六七八九十]+期',block['intro']))
                    if local_phases!=phases:continue
                    note=re.match(r'\s*(?:（[^（）]{1,100}）|\([^()]{1,100}\))',suffix)
                    condition=note[0].strip() if note else ''
                    rest=suffix[len(note[0]):] if note else suffix
                    if re.match(r'^(?:不含|不包括|仅|但|除外|含税|不含税)',rest.lstrip(' ，,。；;()（）')):continue
                    notes=[t for t in block['texts'][i+1:block['end']] if re.match(r'^(?:注[：:]|备注|以上|上述|该金额|该费用|该工程费|仅|不含)',t)]
                    if any(re.search(r'不含|不包括|仅|但|除外|含税|不含税',t) for t in notes):continue
                    value=Decimal(match['value'].replace(',',''));base=value*factors[match['unit']]
                    unit=units[0] if units else match['unit'];value=base/factors[unit]
                    qualifier=match['qualifier'] or '';label=''.join(sorted(local_phases))+requested[0]
                    citation=field_citation(card,block,i,name,label)
                    if citation is None:continue
                    facts.append({'text':f'{name}，{label}{qualifier}{format(value.normalize(),"f")}{unit}{condition}。',
                                  'citation':citation,'identity':(str(base.normalize()),tuple(sorted(local_phases)),qualifier,condition),
                                  'raw_value':match['value'],'raw_unit':match['unit'],'qualifier':qualifier})
    if not facts:return reject('NO_PROJECT_BOUND_AMOUNT_WITH_EXPLICIT_RMB_UNIT')
    if len({f['identity'] for f in facts})!=1:return reject('CONFLICTING_PROJECT_MONEY_VALUES')
    fact=facts[0]
    return {'answer_status':'SOURCE_EXTRACT','status_label':'项目金额字段答复 · 待业务核对',
            'answer':fact['text']+' ['+fact['citation']['citation_id']+']','citations':[fact['citation']],
            'generation_mode':'LOCAL_PROJECT_MONEY_FIELD_NO_MODEL','answer_completeness':'SOURCE_FIELD_SCOPE_ONLY',
            'field_audit':{'method':'PROJECT_BOUND_MONEY','project':name,'metric':requested[0],
                           **{k:fact[k] for k in ['raw_value','raw_unit','qualifier']}},
            'notice':'按本次同版主证据中的项目、明确金额指标和人民币单位提取；完整项目段落见引用。未调用生成模型，业务口径仍可核对。'}


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
        for block in project_blocks(c,name):
            texts=block['texts'];start=block['start'];end=block['end']
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
                    local_phases.update(re.findall(r'[一二三四五六七八九十]+期',block['intro']))
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
                    citation=field_citation(c,block,i,name,label)
                    if citation is None:continue
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
