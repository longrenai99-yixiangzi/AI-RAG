"""Source-bound prose context; table and diagram reading order is never inferred here."""
import hashlib
from pathlib import Path
import re

import pymupdf
from app.retrieval.table_schema import PDF_READ_LOCK


def compact(text):return re.sub(r'\s+','',text)


def native_lines(page):
    result=[]
    raw=page.get_text('rawdict',flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for block_id,block in enumerate(raw['blocks']):
        if block['type']!=0:continue
        for line in block['lines']:
            if abs(line['dir'][1])>.01 or line['dir'][0]<.99:continue
            chars=[c for span in line['spans'] for c in span['chars']]
            text=''.join(c['c'] for c in chars).strip()
            if not text:continue
            if line['bbox'][1]>page.rect.height*.9 and re.fullmatch(r'[-—–]?\s*\d{1,4}\s*[-—–]?',text):continue
            result.append({'text':text,'bbox':list(line['bbox']),'block':block_id,
                           'chars':[{'c':c['c'],'bbox':list(c['bbox'])} for c in chars if not c['c'].isspace()]})
    return result


def paragraph_text(lines,spec):
    ids=spec['line_ids'];context=spec.get('context_line_ids',[])
    if not ids or any(type(i) is not int for i in ids) or ids[0]<0 or ids!=list(range(ids[0],ids[-1]+1)) or ids[-1]>=len(lines):
        raise ValueError('Non-contiguous or invalid native paragraph lines')
    if context and (ids[0]==0 or context!=[ids[0]-1] or not re.fullmatch(r'\d+[）)]\s*[^。；]{2,30}',lines[context[0]]['text'])):
        raise ValueError('Unverified paragraph actor context')
    body='\n'.join(lines[i]['text'] for i in ids)
    if not body.endswith(('。','；')):raise ValueError('Native paragraph has no verified complete ending')
    return body,'\n'.join(lines[i]['text'] for i in context)


def complete_rows(records,specs):
    by_id={r['evidence_id']:r for r in records};changed={};documents={}
    with PDF_READ_LOCK:
        try:
            for spec in specs:
                path=Path(spec['source_path']);version=spec['source_version'];key=(str(path),version)
                if key not in documents:
                    raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Paragraph original version changed')
                    documents[key]=pymupdf.open(stream=raw,filetype='pdf')
                lines=native_lines(documents[key][spec['page']-1]);body,context=paragraph_text(lines,spec)
                left=by_id[spec['left_id']];right=by_id[spec['right_id']]
                if any(r['source_path']!=str(path) or r['source_version']!=version or r.get('location',{}).get('section')!=f'Page {spec["page"]}' for r in (left,right)):
                    raise ValueError('Cross-source paragraph completion')
                if any(r['evidence_id'] in changed for r in (left,right)):
                    raise ValueError('Dense overlapping cuts require resegmentation instead of repeated expansion')
                cut=spec['cut_in_paragraph'];positions=[i for i,c in enumerate(body) if not c.isspace()]
                if type(cut) is not int or not 0<cut<len(positions):raise ValueError('Invalid paragraph cut')
                offset=positions[cut];prefix,suffix=body[:offset],body[offset:]
                if not compact(left['text']).endswith(compact(prefix)) or not compact(right['text']).startswith(compact(suffix)):
                    raise ValueError('Indexed fragments do not meet inside the same native paragraph')
                values=[(left,left['text']+suffix),(right,(context+'\n' if context else '')+prefix+right['text'])]
                box=[min(lines[i]['bbox'][0] for i in spec['line_ids']),min(lines[i]['bbox'][1] for i in spec['line_ids']),
                     max(lines[i]['bbox'][2] for i in spec['line_ids']),max(lines[i]['bbox'][3] for i in spec['line_ids'])]
                for old,text in values:
                    if compact(body) not in compact(text):raise ValueError('Completion still loses paragraph text')
                    if len(text)>2000:raise ValueError('Completed context exceeds reviewed extract budget')
                    changed[old['evidence_id']]={**old,'text':text,'paragraph_completion':{
                        'method':'SOURCE_NATIVE_PARAGRAPH_COMPLETION','page':spec['page'],'bbox':box,
                        'line_ids':spec['line_ids'],'context_line_ids':spec.get('context_line_ids',[]),
                        'paragraph_sha256':hashlib.sha256(body.encode()).hexdigest(),'clue_id':spec['clue_id']}}
        finally:
            for doc in documents.values():doc.close()
    return changed


def prose_before_tables(records,specs):
    by_id={r['evidence_id']:r for r in records};changed={}
    with PDF_READ_LOCK:
        for spec in specs:
            old=by_id[spec['evidence_id']];path=Path(spec['source_path']);raw=path.read_bytes()
            if (hashlib.sha256(raw).hexdigest()!=spec['source_version'] or any(old[k]!=spec[k] for k in ('source_path','source_version'))
                    or old.get('location',{}).get('section')!=f'Page {spec["page"]}'):
                raise ValueError('Mixed-page prose version mismatch')
            with pymupdf.open(stream=raw,filetype='pdf') as doc:lines=native_lines(doc[spec['page']-1])
            ids=spec['line_ids']
            if not ids or ids!=list(range(ids[-1]+1)) or not lines[ids[-1]]['text'].endswith(('。','；')):
                raise ValueError('Unverified prose prefix ending')
            if any(lines[i]['bbox'][3]>=spec['table_bbox'][1] for i in ids):
                raise ValueError('Table cells cannot be promoted as prose')
            body=compact(''.join(lines[i]['text'] for i in ids));source=compact(old['text']);start=source.find(body)
            if start<0 or start>15 or re.sub(r'[-—–\d]','',source[:start]):
                raise ValueError('Safe prose is not an original prefix')
            positions=[i for i,c in enumerate(old['text']) if not c.isspace()]
            text=old['text'][:positions[start+len(body)-1]+1]
            changed[old['evidence_id']]={**old,'text':text,'paragraph_completion':{
                'method':'PRESERVE_NATIVE_PROSE_BEFORE_UNVERIFIED_TABLE','page':spec['page'],'line_ids':ids}}
    return changed
