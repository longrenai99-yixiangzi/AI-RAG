"""Complete explicitly reviewed source spans, including adjacent-page continuations."""
import hashlib
from pathlib import Path
import pymupdf
from app.ingestion.pdf_paragraph_context import native_lines,compact
from app.retrieval.table_schema import PDF_READ_LOCK

def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def read_span(document,part):
    page=part['page'];ids=part['line_ids']
    if type(page) is not int or not 1<=page<=len(document):raise ValueError('Invalid source span page')
    lines=native_lines(document[page-1])
    if not ids or any(type(i) is not int for i in ids) or ids!=list(range(ids[0],ids[-1]+1)) or ids[0]<0 or ids[-1]>=len(lines):raise ValueError('Invalid source span lines')
    text='\n'.join(lines[i]['text'] for i in ids)
    if digest(text)!=part['text_sha256']:raise ValueError('Source span text changed')
    box=[min(lines[i]['bbox'][0] for i in ids),min(lines[i]['bbox'][1] for i in ids),max(lines[i]['bbox'][2] for i in ids),max(lines[i]['bbox'][3] for i in ids)]
    if any(abs(a-b)>.05 for a,b in zip(box,part['bbox'])):raise ValueError('Source span coordinates changed')
    return text

def span_paragraph(document,spec):
    parts=spec['segments'];pages=[p['page'] for p in parts]
    if len(parts) not in {1,2} or pages!=list(range(pages[0],pages[0]+len(parts))):raise ValueError('Only reviewed adjacent pages may continue prose')
    body='\n'.join(read_span(document,p) for p in parts)
    context='\n'.join(read_span(document,p) for p in spec.get('context_segments',[]))
    if not body.endswith(('。','；','：')) or digest(body)!=spec['paragraph_sha256']:raise ValueError('Incomplete reviewed source unit')
    return body,context

def complete_spans(records,specs):
    by_id={r['evidence_id']:r for r in records};changed={};docs={}
    with PDF_READ_LOCK:
        try:
            for spec in specs:
                path=spec['source_path'];version=spec['source_version'];key=(path,version)
                if spec['segments'][0]['page']!=spec['page']:raise ValueError('Source span starts on another page')
                if key not in docs:
                    raw=Path(path).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Source span original changed')
                    docs[key]=pymupdf.open(stream=raw,filetype='pdf')
                body,context=span_paragraph(docs[key],spec)
                first=read_span(docs[key],spec['segments'][0])
                right=by_id[spec['right_id']];targets=[right]
                if spec['mode']=='RIGHT_CONTINUATION_ONLY':
                    if compact(right['text'])!=compact(first):raise ValueError('Continuation is not the indexed whole page tail')
                    values=[(right,(context+'\n' if context else '')+body)]
                elif spec['mode']=='PAIR_COMPLETION':
                    left=by_id[spec['left_id']];targets.append(left)
                    positions=[i for i,c in enumerate(body) if not c.isspace()];cut=spec['cut_in_paragraph']
                    if type(cut) is not int or not 0<cut<len(compact(first)):raise ValueError('Boundary not inside first-page prose')
                    offset=positions[cut];prefix,suffix=body[:offset],body[offset:]
                    first_tail=compact(first)[cut:]
                    if not compact(left['text']).endswith(compact(prefix)) or not compact(right['text']).startswith(first_tail):raise ValueError('Indexed cut does not match original span')
                    if len(spec['segments'])==2:
                        if compact(right['text'])!=first_tail:raise ValueError('Cross-page tail contains other paragraphs')
                        right_text=body
                    else:right_text=prefix+right['text']
                    left_text=left['text']+suffix
                    if context and compact(context) not in compact(left_text):left_text+='\n[原文关联上下文]\n'+context
                    values=[(left,left_text),(right,(context+'\n' if context else '')+right_text)]
                else:raise ValueError('Unreviewed source span operation')
                for row in targets:
                    if row['source_path']!=path or row['source_version']!=version or row.get('location',{}).get('section')!=f'Page {spec["page"]}':raise ValueError('Source span bound to another source/page')
                    if row['evidence_id'] in changed:raise ValueError('Overlapping source span repairs require resegmentation')
                pages=sorted({p['page'] for p in spec['segments']+spec.get('context_segments',[])})
                for row,text in values:
                    if compact(body) not in compact(text) or len(text)>2000:raise ValueError('Source span completion loses text or exceeds budget')
                    meta={**spec,'method':'REVIEWED_NATIVE_SOURCE_SPANS','bbox':spec['segments'][0]['bbox']}
                    changed[row['evidence_id']]={**row,'text':text,'paragraph_completion':meta,
                        'location':{**row.get('location',{}),'page':spec['page'],'pages':pages},
                        'display_location':spec['display_location']}
        finally:
            for doc in docs.values():doc.close()
    return changed
