"""Shorten only to an already reviewed native unit, retaining its complete context."""
import hashlib,re
from pathlib import Path
import pymupdf
from app.ingestion.pdf_source_spans import span_paragraph
from app.retrieval.table_schema import PDF_READ_LOCK
from app.retrieval.named_source_scope import named_titles
from app.bm25 import tokenize

def compact(s):return re.sub(r'\s+','',s).casefold()

def native_unit_excerpt(card,question):
    spec=card.get('paragraph_completion') or {}
    if not spec.get('segments') or spec.get('unit_scope')=='INTRO_WITH_EXPLICIT_MODIFICATION':return None
    task=question
    for title in named_titles(question) or []:task=task.replace('《'+title+'》','')
    if re.search(r'全文|全部|完整|所有|整个|逐项|对比|比较|区别|多少|几人|几天|合计|计算|占比|如何|怎么|为什么|审批权限|现行|生效|效力',task):return None
    codes=set(re.findall(r'(?<!\d)\d+\.\d+(?:\.\d+){0,2}(?![\d.])',task))
    if len(codes)!=1:return None
    path=Path(card.get('source_path',''));version=card.get('source_version')
    if str(path)!=spec['source_path'] or version!=spec['source_version']:return None
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Shortened source original changed')
    with PDF_READ_LOCK,pymupdf.open(stream=raw,filetype='pdf') as doc:body,context=span_paragraph(doc,spec)
    unit=(context+'\n' if context else '')+body
    native_codes=set(re.findall(r'(?m)^(\d+\.\d+(?:\.\d+){0,2})(?![\d.])',context+'\n'+body))
    if not codes<=native_codes:return None
    item=re.match(r'^[（(](\d+)[）)]',body)
    asked=re.findall(r'第[（(]?(\d+)[）)]?项',task)
    if item and asked!=[item[1]]:return None
    if not item and asked:return None
    if not item and re.search(r'包括哪些|包含哪些|有哪些内容|全部内容',task):return None
    query=re.sub(r'\d+\.\d+(?:\.\d+){0,2}','',task).replace('排除','不包括')
    query=re.sub(r'第\s*[（(]?\d+[）)]?\s*项(?:中)?|这一项|这一条|这项|该项','',query).replace('及',' ')
    stop={'根据','通用','专用','条件','原文','处理','要求','这一','哪些','中','什么','是否','规定','第','项','须知'}
    if re.search(r'\d+\s*(?:天|日|小时)',body):stop.add('期限')
    terms={t for t in tokenize(query) if len(t)>1 and t not in stop and not t.isdigit()}
    if len(terms)<(1 if item else 2) or any(compact(t) not in compact(unit) for t in terms):return None
    if any(compact(part) not in compact(card['excerpt']) for part in (body,context) if part):return None
    if len(compact(unit))>=len(compact(card['excerpt'])):return None
    return unit,'REVIEWED_NATIVE_UNIT_WITH_FULL_CONTEXT'
