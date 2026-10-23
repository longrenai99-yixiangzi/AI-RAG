"""Opt-in section boundaries for existing Word-to-Markdown exports; no source writes."""
from collections import defaultdict
import hashlib
from pathlib import Path
import re

from docx import Document
from docx.oxml.ns import qn
from app.ingestion.normalization.markdown_normalizer import normalize_markdown_text

ANCHOR = re.compile(r'^\[/body/p\[@paraId=([A-Fa-f0-9]+)\]\]\s*', re.M)
NUMBERED = re.compile(r'^(\d+(?:\.\d+)+)\s*([^\d].*)$')


def pdf_explanation_blocks(candidate):
    """Recover explicit numbered notes already present in one native PDF chunk."""
    if Path(candidate.get('source_path','')).suffix.lower()!='.pdf':return []
    text=candidate.get('text') or '';result=[]
    titles=list(re.finditer(r'^《([^》\n]{2,60})》说明[：:]\s*$',text,re.M))
    for title in titles:
        boundary=re.search(r'^(?:第[一二三四五六七八九十\d]+章[^\n]+|附件\s*\d+[：:][^\n]+|《[^》\n]+》说明[：:])',text[title.end():],re.M)
        # shortcut: require an explicit following boundary in this same chunk; cross-chunk notes stay unverified.
        if not boundary:continue
        stop=title.end()+boundary.start();body=text[title.end():stop].strip()
        markers=list(re.finditer(r'^(\d{1,2})[）)]\s*',body,re.M))
        if len(markers)<2 or [int(m[1]) for m in markers]!=list(range(1,len(markers)+1)):continue
        if body[:markers[0].start()].strip():continue
        items=[body[m.start():markers[i+1].start() if i+1<len(markers) else len(body)].strip() for i,m in enumerate(markers)]
        if any(not item.endswith(('。','；',';')) for item in items):continue
        quote=text[title.start():stop].strip();heading=(candidate.get('heading_path') or '原文位置')+' > 《'+title[1]+'》说明'
        key=hashlib.sha256((candidate['source_path']+candidate['source_version']+quote).encode()).hexdigest()
        result.append({**candidate,'evidence_id':'pdf-note-'+key,'text':quote,'heading_path':heading,
                       'display_location':heading+f' > 原文第1—{len(items)}点',
                       'location':{**(candidate.get('location') or {}),'section':heading,'char_start':title.start(),'char_end':stop},
                       'retrieved_child_ids':[candidate['evidence_id']],
                       'explanation_block':{'title':title[1],'item_count':len(items),'kind':'EXPLICIT_NUMBERED_NOTE','full_table_fields_verified':False}})
    return result


def effective_outline(paragraph):
    # Reused from the 20261014 structure trial's docx_outline.effective_outline.
    chain, seen = [], set()
    style = paragraph.style
    while style is not None:
        if style.style_id in seen:raise ValueError('Cyclic Word style inheritance')
        seen.add(style.style_id);chain.append(style.element);style=style.base_style
    level = None
    for element in [*reversed(chain),paragraph._p]:
        ppr=element.find(qn('w:pPr'))
        node=ppr.find(qn('w:outlineLvl')) if ppr is not None else None
        if node is not None:
            level=int(node.get(qn('w:val')))
            if not 0<=level<=9:raise ValueError('Invalid Word outline level')
    return level+1 if level is not None and level<9 else None


def sections_for(markdown_path, original_path):
    """Use Word-declared headings, then conservative numbered siblings inside them."""
    path, original = Path(markdown_path),Path(original_path)
    raw=path.read_bytes();original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    text=normalize_markdown_text(raw.decode('utf-8-sig'))
    matches=list(ANCHOR.finditer(text));document=Document(original)
    native={}
    for p in document.paragraphs:
        anchor=p._p.get(qn('w14:paraId'))
        if anchor:
            if anchor in native:raise ValueError('Duplicate native paragraph anchor')
            native[anchor]=(p.text,effective_outline(p),p._p.find('w:pPr/w:numPr',p._p.nsmap) is not None)
    units=[];seen=set()
    normalize=lambda value:re.sub(r'\s+','',value)
    for i,m in enumerate(matches):
        anchor=m[1];end=matches[i+1].start() if i+1<len(matches) else len(text)
        body=text[m.end():end].strip()
        if anchor in seen or anchor not in native:raise ValueError('Missing or duplicate paragraph anchor')
        native_text,level,numbered=native[anchor]
        comparable=re.sub(r'^(?:[（(][\d一二三四五六七八九十]+[）)]|[\d一二三四五六七八九十]+[、.)）．]|[•●])\s*','',body) if numbered else body
        if normalize(body)!=normalize(native_text) and normalize(comparable)!=normalize(native_text):
            raise ValueError('Markdown paragraph does not match native source: '+anchor)
        seen.add(anchor);units.append({'anchor':anchor,'text':body,'start':m.start(),'end':end,'level':level,'origin':'WORD_DECLARED_OUTLINE'})
    if not units:raise ValueError('No supported direct-body paragraph anchors')
    # shortcut: infer only short decimal siblings beneath a matching declared numbered parent; other plain headings remain body.
    groups=defaultdict(list);parent=None
    for i,u in enumerate(units):
        if u['level'] is not None:
            parent=i;continue
        m=NUMBERED.fullmatch(u['text'])
        root=re.match(r'^(\d+)[、．.]',units[parent]['text']) if parent is not None else None
        if m and root and m[1].split('.')[0]==root[1] and len(u['text'])<=70 and not re.search(r'[。；：，!?！？]',m[2]):
            groups[(parent,'.'.join(m[1].split('.')[:-1]))].append((i,m[1]))
    for (parent,_),siblings in groups.items():
        if len(siblings)<2 or len({n for _,n in siblings})!=len(siblings):continue
        for i,number in siblings:
            units[i].update(level=units[parent]['level']+number.count('.'),origin='NUMBERED_SIBLINGS_INFERRED_NOT_OWNER_REVIEWED')
    result=[];stack=[]
    for i,u in enumerate(units):
        if u['level'] is None:continue
        while stack and stack[-1]['level']>=u['level']:stack.pop()
        end=next((j for j in range(i+1,len(units)) if units[j]['level'] is not None and units[j]['level']<=u['level']),len(units))
        # Retrieval packages use the nearest subsection, never the whole declared ancestor.
        direct_end=next((j for j in range(i+1,end) if units[j]['level'] is not None),end)
        section_text=text[u['start']:units[direct_end]['start'] if direct_end<len(units) else len(text)].strip()
        heading=' > '.join([s['title'] for s in stack]+[u['text']])
        item={'section_id':hashlib.sha256((str(path.resolve())+hashlib.sha256(raw).hexdigest()+u['anchor']).encode()).hexdigest()[:32],
              'title':u['text'],'heading_path':heading,'level':u['level'],'heading_origin':u['origin'],
              'text':section_text,'paragraph_anchors':[x['anchor'] for x in units[i:direct_end]],
              'source_path':str(path),'source_version':hashlib.sha256(raw).hexdigest(),'original_source_path':str(original),'original_source_sha256':original_hash,
              'location':{'section_path':heading,'line_start':text[:u['start']].count('\n')+1,'line_end':text[:units[direct_end]['start'] if direct_end<len(units) else len(text)].rstrip().count('\n')+1,'paragraph_anchor':u['anchor']}}
        result.append(item);stack.append(item)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=hashlib.sha256(raw).hexdigest() or hashlib.sha256(original.read_bytes()).hexdigest()!=original_hash:
        raise ValueError('Source changed during section extraction')
    return result


def expand_candidates(candidates, sections):
    """Expand hit anchors to bounded subsections, preserving other source candidates."""
    lookup={(s['source_path'],s['source_version'],a):s for s in sections for a in s['paragraph_anchors']}
    result=[];seen=set()
    for c in candidates:
        result.extend(pdf_explanation_blocks(c))
        found={}
        for anchor in ANCHOR.finditer(c.get('text') or ''):
            section=lookup.get((c.get('source_path'),c.get('source_version'),anchor[1]))
            if section:found[section['section_id']]=section
        if not found:result.append(c);continue
        for sid,s in found.items():
            if sid in seen:continue
            seen.add(sid)
            result.append({**c,'evidence_id':'section-'+sid,'text':s['text'],'heading_path':s['heading_path'],'location':s['location'],
                           'display_location':s['heading_path'],'heading_origin':s['heading_origin'],'retrieved_child_ids':[c['evidence_id']]})
    return result
