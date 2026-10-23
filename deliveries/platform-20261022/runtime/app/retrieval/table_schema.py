"""Read only a named table's column labels from admitted native PDF geometry."""
import hashlib
import re
import threading
from pathlib import Path

import pymupdf

from .named_source_scope import named_titles
from .complete_lists import NUM,number

PDF_READ_LOCK=threading.Lock()


def compact(text):return re.sub(r'\s+','',text)


def schema_request(question):
    if not named_titles(question) or not re.search(r'表头|字段|栏目|列名',question):return None
    task=question
    for title in named_titles(question):task=task.replace('《'+title+'》','')
    appendices=re.findall(r'附件\s*('+NUM+r')',task)
    if len(set(appendices))>1:return None
    task=re.sub(r'附件\s*'+NUM,'',task)
    task=re.sub(r'^(?:(?:依据|根据|按照|按|参照)(?:局|公司|本|该)?|请问|请列出)\s*','',task).strip('中，,：: ')
    quoted=re.findall(r'[“「『]([^”」』]{2,60}(?:清单|台账|表))[”」』]',task)
    plain=re.match(r'^([^，,。；;！？?]{2,45}?(?:清单|台账|表))(?:的|有|包括|包含|应|需)',task)
    titles=list(dict.fromkeys(quoted or ([plain[1]] if plain else [])))
    if len(titles)!=1:return None
    tail=task.replace(titles[0],'')
    count=re.search(r'('+NUM+r')\s*(?:个|项|列)?\s*(?:字段|栏目|列名)',tail)
    return {'title':titles[0],'appendix':number(appendices[0]) if appendices else None,
            'expected_count':number(count[1]) if count else None,
            'question_sha256':hashlib.sha256(question.encode()).hexdigest(),
            'extra_details':bool(re.search(r'谁|哪天|哪年|多久|何时|本项目|实际|对比|比较|为什么|如何|怎么|(?:19|20)\d{2}|填(?:多少|什么|几)|金额|人数|必填|选填|可不填|不填|不含|不包括|除外|除.{1,20}外|填写要求|填写说明|填报规则|填写规则|含义|解释|用途',tail))}


def header_from_page(path,page_number,title):
    with PDF_READ_LOCK,pymupdf.open(path) as document:
        page=document[page_number-1]
        lines=[line for block in page.get_text('rawdict')['blocks'] for line in block.get('lines',[])
               if abs(line['dir'][0]-1)<.001 and abs(line['dir'][1])<.001]
        titles=[line for line in lines if compact(''.join(c['c'] for s in line['spans'] for c in s.get('chars',[])))==compact(title)]
        found=[]
        for table in page.find_tables().tables:
            if not any(0<=table.bbox[1]-line['bbox'][3]<=90 and table.bbox[0]<=(line['bbox'][0]+line['bbox'][2])/2<=table.bbox[2] for line in titles):continue
            if not table.rows:continue
            cells=table.rows[0].cells
            # shortcut: one unmerged header row beginning with 序号; grouped headers need separate verification.
            if len(cells)<2 or len(cells)>30 or any(cell is None for cell in cells):continue
            fields=[]
            for cell in cells:
                box=pymupdf.Rect(cell);pieces=[]
                for line in lines:
                    chars=[c for span in line['spans'] for c in span.get('chars',[])
                           if box.contains(pymupdf.Point((c['bbox'][0]+c['bbox'][2])/2,(c['bbox'][1]+c['bbox'][3])/2))]
                    if chars:pieces.append((line['bbox'][1],''.join(c['c'] for c in chars)))
                fields.append({'name':compact('\n'.join(text for _,text in sorted(pieces))),'bbox':[round(x,3) for x in cell]})
            names=[field['name'] for field in fields]
            if names[0]!='序号' or len(set(names))!=len(names) or any(not 1<=len(n)<=30 or not re.search(r'[\u4e00-\u9fffA-Za-z]',n) for n in names):continue
            found.append({'fields':fields,'table_bbox':[round(x,3) for x in table.bbox]})
        if len(found)!=1:raise ValueError('原表表头未唯一核定，未将合并表头或示例行作为字段。')
        return found[0]


def schema_bundle(question,records,outline_catalog):
    request=schema_request(question)
    if not request:return None
    audit={**request,'status':'TABLE_HEADER_UNVERIFIED'}
    if request['extra_details']:audit['status']='SCHEMA_NOT_PROJECT_VALUES';return {'candidate_evidence':[],'table_schema_audit':audit}
    candidates={}
    for row in records:
        page=re.fullmatch(r'Page (\d+)',row.get('heading_path',''))
        if not page or Path(row['source_path']).suffix.lower()!='.pdf':continue
        if not any(compact(line)==compact(request['title']) for line in row['text'].splitlines()):continue
        if request['appendix'] is not None:
            bound=[entry for entry in outline_catalog if entry.get('kind')=='APPENDIX_OUTLINE'
                   and entry['audit']['appendix_number']==request['appendix'] and entry['record']['source_path']==row['source_path']
                   and entry['record']['source_version']==row['source_version']
                   and entry['audit']['start_page']<=int(page[1])<=entry['audit']['end_page']]
            if len(bound)!=1:continue
        candidates[(row['source_path'],row['source_version'],int(page[1]))]=row
    if len(candidates)!=1:return {'candidate_evidence':[],'table_schema_audit':audit}
    (path,version,page),row=next(iter(candidates.items()))
    try:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=version:raise ValueError('原件版本已变。')
        header=header_from_page(path,page,request['title'])
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=version:raise ValueError('读取期间原件版本已变。')
    except (OSError,ValueError,RuntimeError,IndexError) as error:
        audit['reason']=str(error);return {'candidate_evidence':[],'table_schema_audit':audit}
    text='表名：'+request['title']+'\n原表栏目：'+' | '.join(field['name'] for field in header['fields'])
    key=hashlib.sha256((path+version+text).encode()).hexdigest()
    record={**row,'evidence_id':'table-schema-'+key,'text':text,'role':'DIRECT','answer_usage':'PRIMARY',
            'location':{**(row.get('location') or {}),'page':page},
            'display_location':f'PDF Page {page} > {request["title"]} > 原表表头（不含示例值）'}
    audit.update(status='HEADER_VERIFIED',source_path=path,source_version=version,page=page,evidence_id=record['evidence_id'],
                 fields=header['fields'],table_bbox=header['table_bbox'],excerpt_sha256=hashlib.sha256(text.encode()).hexdigest())
    return {'candidate_evidence':[record],'table_schema_audit':audit,'bundle_status':'NATIVE_TABLE_HEADER'}


def enforce_schema(question,result):
    audit=result.get('table_schema_audit') or result.get('debug',{}).get('table_schema_audit') or {}
    request=schema_request(question);cards=result.get('citations',[])
    verified=bool(request and not request['extra_details'] and audit.get('status')=='HEADER_VERIFIED'
                  and request['question_sha256']==audit.get('question_sha256') and request['title']==audit.get('title'))
    card=next((c for c in cards if c.get('answer_usage')=='PRIMARY' and c.get('evidence_id')==audit.get('evidence_id')
               and c.get('source_version')==audit.get('source_version') and c.get('source_path')==audit.get('source_path')),None)
    if verified and card:
        try:
            verified=card.get('location',{}).get('page')==audit['page']
            verified=verified and hashlib.sha256(Path(card['source_path']).read_bytes()).hexdigest()==card['source_version']
            verified=verified and hashlib.sha256(card['excerpt'].encode()).hexdigest()==audit['excerpt_sha256']
            verified=verified and header_from_page(card['source_path'],audit['page'],audit['title'])=={'fields':audit['fields'],'table_bbox':audit['table_bbox']}
            verified=verified and hashlib.sha256(Path(card['source_path']).read_bytes()).hexdigest()==card['source_version']
        except (OSError,ValueError,RuntimeError,IndexError,KeyError,TypeError):verified=False
    else:verified=False
    if verified:
        names=[field['name'] for field in audit['fields']]
        if request.get('expected_count') is not None and request['expected_count']!=len(names):
            audit={**audit,'status':'REQUEST_COLUMN_COUNT_DIFFERS_FROM_SOURCE'}
            return {**result,'answer_status':'TABLE_SCHEMA_UNVERIFIED','answer':'所问栏目数量与当前原表不一致，请核对数量或指定原表；本次不按预设数量补凑。',
                    'generation_mode':'NO_GENERATION','claims':[],'answer_completeness':'UNANSWERED','table_schema_audit':audit,
                    'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards]}
        return {**result,'answer_status':'SOURCE_EXTRACT','status_label':'原表栏目 · 未包含项目填报值',
                'answer':f'所引原表“{audit["title"]}”的栏目为：'+'、'.join(names)+f'。 [{card["citation_id"]}]',
                'generation_mode':'VERIFIED_TABLE_SCHEMA_NO_MODEL','answer_completeness':'COLUMN_LABELS_ONLY',
                'table_schema_audit':audit,'citations':[card],
                'notice':'栏目名称来自本次引用版本的原表；未把模板示例或空白单元格作为项目填报值。具体填写要求及适用效力请核对原文。'}
    return {**result,'answer_status':'TABLE_SCHEMA_UNVERIFIED','status_label':'原表栏目或所问项目值尚未核定',
            'answer':'当前只支持核对指定原表的栏目名称；表头未唯一核定，或问题还要求实际项目值、填写判断等内容。本次不猜测、不用模板示例代填。',
            'generation_mode':'NO_GENERATION','claims':[],'answer_completeness':'UNANSWERED','table_schema_audit':audit,
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards],
            'applicability':'这里只核对原表栏目，不代表已有实际项目填报值或填写判断。'}
