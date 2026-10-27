"""Retain an adjacent timed Word heading only after checking the actual source."""
import hashlib
from pathlib import Path
import re
from zipfile import ZipFile,BadZipFile
import xml.etree.ElementTree as ET
from app.answer_engine.llm.claim_validator import TIMED_HEADING


def retain_timed_heading(record):
    heading=record.get('heading_path','').rsplit(' > ',1)[-1]
    location=record.get('location') or {};paths=location.get('native_paragraph_paths') or []
    path=Path(record.get('source_path',''))
    if not TIMED_HEADING.fullmatch(heading) or path.suffix.lower()!='.docx' or not paths:return record
    first=re.fullmatch(r'/body/p\[(?:@paraId=([A-Za-z0-9]+)|(\d+))\]',paths[0] or '')
    if not first:return record
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=record.get('source_version'):return record
        from io import BytesIO
        with ZipFile(BytesIO(data)) as archive:root=ET.fromstring(archive.read('word/document.xml'))
        body=root.find('w:body',ns)
        if body is None:return record
        paragraphs=body.findall('w:p',ns)
        matches=[i for i,p in enumerate(paragraphs,1) if (p.get('{http://schemas.microsoft.com/office/word/2010/wordml}paraId')==first[1] if first[1] else i==int(first[2]))]
        if len(matches)!=1:return record
        text=lambda p:''.join(t.text or '' for t in p.findall('.//w:t',ns)).strip()
        compact=lambda value:re.sub(r'\s+','',value)
        first_text=text(paragraphs[matches[0]-1])
        if not first_text or compact(first_text) not in compact(record['text']):return record
        previous=next(((i,p) for i,p in reversed(list(enumerate(paragraphs[:matches[0]-1],1))) if text(p)),None)
        if previous is None or compact(text(previous[1]))!=compact(heading):return record
        return {**record,'text':text(previous[1])+'\n'+record['text'],'location':{**location,'native_context_paragraph':previous[0]},'native_context_audit':{'method':'ADJACENT_TIMED_HEADING_SOURCE_VERIFIED','source_version':record['source_version']}}
    except (OSError,BadZipFile,KeyError,ET.ParseError):return record
