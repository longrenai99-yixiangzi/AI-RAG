"""Read explicit grouped lists from existing, version-bound evidence; no source parsing."""
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from app.retrieval.named_source_scope import named_titles

NUM=r'(?:\d{1,3}|[一二两三四五六七八九]?十[一二三四五六七八九]?|[零一二两三四五六七八九])'
DECL=re.compile(r'('+NUM+r')(?:个|项|条|种)([\u4e00-\u9fffA-Za-z]{2,30}?)[，,。；;：:]')
GROUP=re.compile(r'第('+NUM+r')(?:类|组)(?:为|是)([^，,。；;：:]{1,30})[，,：:](?:主要)?(?:包括|包含)([^；;。]+)([；;。])')


def number(text):
    if text.isdigit():return int(text)
    values=dict(zip('一二三四五六七八九',range(1,10)));values['两']=2
    if '十' in text:
        a,b=text.split('十');return (values.get(a,1)*10)+values.get(b,0)
    return values.get(text,0)


def compact(text):return re.sub(r'\s+','',unicodedata.normalize('NFKC',text)).replace('的','')


def list_request(question):
    query=unicodedata.normalize('NFKC',question)
    found=re.search(r'(?<![第\d.．零一二两三四五六七八九十])('+NUM+r')\s*(个|项|条|种|类)\s*([^，,。；;！？?]{2,35}?)(?:有哪些|分别是|包括哪些|是什么|如何|怎么)',query)
    if found:
        count,unit,topic=found.groups()
        result={'expected_count':number(count),'count_kind':'GROUPS' if unit=='类' else 'ITEMS','topic':compact(topic)}
    elif re.search(r'完整清单|全部.*(?:动作|事项|章节)|列出.*(?:清单|章节)|(?:有哪些|包含哪些|包括哪些)章节|(?:动作|事项|类别)有哪些|章节和内容',query):
        result={'expected_count':None,'count_kind':'ITEMS','topic':''}
    else:return None
    result['question_sha256']=hashlib.sha256(question.encode()).hexdigest()
    intent=query
    for title in named_titles(query) or []:intent=intent.replace('《'+title+'》','')
    result['details_unverified']=bool(re.search(r'如何|怎么|谁|牵头|负责|各自|每项|职责|流程|步骤|措施|对比|比较|区别|变化|原因|(?:19|20)\d{2}|今年|去年|截至',intent))
    return result


def parse_lists(raw):
    offsets=[i for i,c in enumerate(raw) if not c.isspace()]
    flat=''.join(raw[i] for i in offsets);result=[]
    for declaration in DECL.finditer(flat):
        count=number(declaration[1])
        if not 1<=count<=60:continue
        groups=[];last_end=None
        for group in GROUP.finditer(flat,declaration.end(),min(len(flat),declaration.end()+4000)):
            if number(group[1])!=len(groups)+1:break
            if last_end is not None and group.start()!=last_end:break
            items=[s.strip() for s in re.split(r'[、，,]',group[3])]
            if any(not 1<=len(s)<=60 for s in items):break
            groups.append({'name':group[2],'items':items});last_end=group.end()
            if group[4]=='。':break
        declared_groups=re.search(r'分(?:为|成)('+NUM+r')(?:个)?(?:类别|类|组)',flat[declaration.end():declaration.end()+100])
        items=[s for g in groups for s in g['items']]
        complete=bool(groups and last_end and flat[last_end-1]=='。' and len(items)==count and len(set(items))==count
                      and (not declared_groups or number(declared_groups[1])==len(groups)))
        if not complete:continue
        a,b=offsets[declaration.start()],offsets[last_end-1]+1
        result.append({'declared_count':count,'topic':declaration[2],'groups':groups,'quote':raw[a:b],'start':a,'end':b})
    return result


def build_catalog(records):
    same=defaultdict(list)
    for r in records:same[(r['source_path'],r['source_version'],r.get('heading_path',''))].append(r)
    result=[]
    for rows in same.values():
        if sum(len(r['text']) for r in rows)>12000:continue
        raw='\n'.join(r['text'] for r in rows)
        for entry in parse_lists(raw):
            pos=0;children=[]
            for r in rows:
                if pos<entry['end'] and pos+len(r['text'])>entry['start']:children.append(r['evidence_id'])
                pos+=len(r['text'])+1
            key=hashlib.sha256((rows[0]['source_path']+rows[0]['source_version']+entry['quote']).encode()).hexdigest()
            record={**rows[0],'evidence_id':'complete-list-'+key,'text':entry['quote'],'role':'DIRECT','answer_usage':'PRIMARY',
                    'display_location':(rows[0].get('heading_path') or '原文位置')+' > 原文分组清单',
                    'retrieved_child_ids':children,'retrieval_origin':'SAME_LOCATION_VERIFIED_GROUPED_LIST'}
            result.append({**entry,'record':record,'children':children})
    from .appendix_outline import build_outlines
    return result+build_outlines(records)


def list_bundle(question,catalog,eligible_ids):
    request=list_request(question)
    if request is None:return None
    from .appendix_outline import outline_bundle
    outline=outline_bundle(question,catalog,eligible_ids,request)
    if outline is not None:return outline
    query=compact(question)
    matching=[e for e in catalog if e.get('kind')!='APPENDIX_OUTLINE' and (compact(e['topic']) in (request['topic'] or query)
              or request['topic'] and request['topic'] in compact(e['topic']))]
    matching=[e for e in matching if set(e['children']).issubset(eligible_ids)]
    unique={(e['record']['source_version'],e['topic'],str(e['groups'])):e for e in matching}
    audit={**request,'status':'NO_VERIFIED_COMPLETE_LIST'}
    if len(unique)>1:audit['status']='AMBIGUOUS_LIST_SOURCES'
    elif unique:
        entry=next(iter(unique.values()));r=entry['record']
        count=len(entry['groups']) if request['count_kind']=='GROUPS' else entry['declared_count']
        audit.update(source_version=r['source_version'],evidence_id=r['evidence_id'],declared_count=entry['declared_count'],
                     groups=entry['groups'],source_topic=entry['topic'],child_evidence_ids=entry['children'])
        current=hashlib.sha256(Path(r['source_path']).read_bytes()).hexdigest() if Path(r['source_path']).is_file() else None
        if current!=r['source_version']:audit['status']='SOURCE_VERSION_MISMATCH'
        elif request['details_unverified']:audit['status']='ADDITIONAL_DETAILS_NOT_VERIFIED'
        elif request['expected_count'] is not None and request['expected_count']!=count:audit['status']='REQUEST_COUNT_DIFFERS_FROM_SOURCE'
        else:audit['status']='COMPLETE'
    selected=[next(iter(unique.values()))['record']] if len(unique)==1 and audit['status']=='COMPLETE' else []
    return {'candidate_evidence':selected,'bundle_status':'COMPLETE_LIST_VERIFIED' if selected else 'COMPLETE_LIST_UNVERIFIED',
            'complete_list_audit':audit,'selection_notes':['完整清单先核对声明数量、全部分组、名称与来源版本；未核对时不调用模型凑数。']}


def render_list(audit,cards,question):
    request=list_request(question)
    if request and audit.get('kind')=='APPENDIX_OUTLINE':
        from .appendix_outline import render_outline
        return render_outline(audit,cards,question,request)
    if not request or request['question_sha256']!=audit.get('question_sha256') or audit.get('status')!='COMPLETE':return None
    count=len(audit['groups']) if request['count_kind']=='GROUPS' else audit['declared_count']
    topic=request['topic'] or compact(question)
    if request['details_unverified'] or request['expected_count'] is not None and request['expected_count']!=count:return None
    if compact(audit['source_topic']) not in topic and not (request['topic'] and request['topic'] in compact(audit['source_topic'])):return None
    card=next((c for c in cards if c.get('answer_usage')=='PRIMARY' and c.get('evidence_id')==audit['evidence_id']
               and c.get('source_version')==audit['source_version']),None)
    if not card:return None
    if hashlib.sha256(Path(card['source_path']).read_bytes()).hexdigest()!=card['source_version']:return None
    parsed=parse_lists(card['excerpt'])
    if not any(p['declared_count']==audit['declared_count'] and p['groups']==audit['groups'] and p['topic']==audit['source_topic'] for p in parsed):return None
    name=card.get('display_file_name') or card['file_name'];sid=card['citation_id']
    lines=[f'依据{name}，{audit["source_topic"]}共{audit["declared_count"]}项，分为{len(audit["groups"])}类：']
    for group in audit['groups']:lines.append(group['name']+'：'+'、'.join(group['items'])+'。')
    return {'answer_status':'VERIFIED_LIST','status_label':'原文完整清单 · 数量与分组已核对','answer':'\n'.join(lines)+f' [{sid}]',
            'generation_mode':'VERIFIED_COMPLETE_LIST_NO_MODEL','support_check':'EXACT_NATIVE_ENUMERATION',
            'complete_list_audit':audit,'answer_completeness':'LIST_ITEMS_VERIFIED_NOT_BUSINESS_APPROVED','citations':[card],
            'notice':'清单数量、名称及分组与所引版本原文核对；未自动确认文件现行效力或各项具体流程。'}


def enforce_complete_list(question,result):
    if result.get('table_schema_audit') or result.get('debug',{}).get('table_schema_audit'):
        from .table_schema import enforce_schema
        return enforce_schema(question,result)
    if not list_request(question) or result.get('answer_status') in {'PIPELINE_ERROR','REVIEW_CONFLICT'}:return result
    audit=result.get('complete_list_audit') or result.get('debug',{}).get('complete_list_audit') or {}
    verified=render_list(audit,result.get('citations',[]),question)
    if verified:return {**result,**verified}
    if list_request(question)['details_unverified']:audit={**audit,'status':'ADDITIONAL_DETAILS_NOT_VERIFIED'}
    elif audit.get('status')=='COMPLETE':audit={**audit,'status':'CITATION_OR_QUERY_COVERAGE_NOT_CURRENT'}
    message='本题需要核对完整清单，当前尚未核齐数量、全部名称及同版引用，不用一个子节代答，也不调用模型补凑。'
    if audit.get('status')=='REQUEST_COUNT_DIFFERS_FROM_SOURCE':message=f'所问数量与当前来源声明的{audit["declared_count"]}项不一致，请核对数量或指定依据；本次不按预设数量补凑。'
    if audit.get('status')=='ADDITIONAL_DETAILS_NOT_VERIFIED':message='本题还包含职责、流程、比较或时间范围要求，完整名称清单不能代替这些内容；当前覆盖尚未核定。'
    return {**result,'answer_status':'LIST_COVERAGE_REQUIRED','status_label':'完整清单尚未核齐','answer':message,
            'claims':[],'answer_completeness':'UNANSWERED','generation_mode':'NO_GENERATION',
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in result.get('citations',[])],
            'complete_list_audit':audit or {**list_request(question),'status':'NO_VERIFIED_COMPLETE_LIST'}}
