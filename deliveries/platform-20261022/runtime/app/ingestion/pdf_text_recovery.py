"""Read-only, version-bound PDF watermark removal and complete native-page extracts."""
import hashlib
import json
from pathlib import Path
import re

from .pdf_native_geometry import character_layer

PROFILES = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))


def without_watermarks(text, stamps, protected_text=''):
    # shortcut: identical visible business text wins over deletion; use geometry-aligned chunks if such collisions matter.
    stamps = {s.strip() for s in stamps if s.strip() and s.strip() not in protected_text}
    lines = text.splitlines()
    kept = []
    for i, line in enumerate(lines):
        value = line.strip()
        # Old chunk boundaries can truncate the final stamp; a name alone is never enough.
        clipped = i == len(lines)-1 and len(value) >= 12 and value not in protected_text and any(s.startswith(value) for s in stamps)
        if value not in stamps and not clipped:
            kept.append(line)
    return '\n'.join(kept).strip()


def page_watermarks(page, version):
    profile = PROFILES.get(version)
    if not profile:
        return [], ''
    kept, excluded = character_layer(page.get_text('rawdict'), version, {**profile, 'source_version': version})
    return [s['text'] for s in excluded], ''.join(char['text'] for char in kept)


def clean_pdf_page(page, version):
    stamps, business_text = page_watermarks(page, version)
    return without_watermarks(page.get_text(), stamps, business_text)


def clean_source_records(records):
    cards = [{**r, 'excerpt':r['text'], 'answer_usage':'BACKGROUND'} for r in records]
    cleaned = recover_pdf_citations(cards, '')
    return [{**r, 'text':c['excerpt'], **({'text_cleanup':c['pdf_text_audit']} if c.get('pdf_text_audit') else {})}
            for r,c in zip(records, cleaned, strict=True)]


def clean_markdown_lines(path, text):
    """Keep source line numbers even when a verified watermark line is blanked."""
    version=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if not PROFILES.get(version,{}).get('original_path'):
        return text.splitlines()
    cleaned=clean_source_records([{'text':text,'source_path':str(path),'source_version':version}])[0]['text']
    retained=set(cleaned.splitlines())
    return [line if line in retained or not line.strip() else '' for line in text.splitlines()]


def page_answer_span(text, question):
    """Select only explicit definitions or a complete requested sequence of level labels."""
    q = re.sub(r'[\s、，,]', '', question)
    q = re.sub(r'^(?:依据|根据)?《[^》]+》(?:中的|中|[：:])?', '', q)
    q = re.sub(r'^(?:请问|请说明|请)', '', q)
    if re.search(r'\d|对比|比较|区别|仅|条件下', q):
        return None
    definitions = list(re.finditer(r'^(?:\d+[）)]\s*)?([^\n：:]{2,30})定义[：:]', text, re.M))
    selected = []
    for m in definitions:
        if not q.startswith(m[1]) or not re.search(r'定义|公式|计算|公示', q):
            continue
        tail = re.sub(r'定义|计算|公式|公示|是什么|分别|如何|怎么|怎样|多少|什么', '', q[len(m[1]):])
        if re.fullmatch(r'[的是指为及和与、？?。；;：:]*', tail):
            selected.append(m)
    if len(selected) == 1:
        m = selected[0]
        boundary = re.search(r'^\d+(?:\.\d+)*(?:[）)]|\s*$)', text[m.end():], re.M)
        if boundary:
            end = m.end()+boundary.start()
            if text[m.start():end].strip().endswith('。'):
                return m.start(), end, 'NATIVE_DEFINITION_BLOCK'
    levels = list(re.finditer(r'^([一二三四五六七八九十])级([^\n：:]{2,30})[：:]', text, re.M))
    if len(levels) < 2 or len({m[2] for m in levels}) != 1:
        return None
    sequence = ''.join(m[1] for m in levels)
    if sequence != '一二三四五六七八九十'[:len(levels)] or sequence+'级' not in q:
        return None
    if not any(levels[0][2][-n:] in q for n in range(2, len(levels[0][2])+1)):
        return None
    boundary = re.search(r'^\d+[）)]', text[levels[-1].end():], re.M)
    if not boundary:
        return None
    end = levels[-1].end()+boundary.start()
    blocks = [text[m.start():levels[i+1].start() if i+1<len(levels) else end].strip()
              for i, m in enumerate(levels)]
    if not all(b.endswith('。') for b in blocks):
        return None
    return levels[0].start(), end, 'NATIVE_COMPLETE_LEVEL_BLOCKS'


def recover_pdf_citations(cards, question):
    """Clean frozen PDFs and verified Markdown exports; unknown/changed sources stay untouched."""
    import pymupdf
    from app.retrieval.table_schema import PDF_READ_LOCK
    documents = {}; verified_sources = {}; native_marks = {}
    result = []
    PDF_READ_LOCK.acquire()
    try:
        for card in cards:
            row = dict(card)
            version = card.get('source_version')
            profile = PROFILES.get(version)
            path = Path(card.get('source_path', ''))
            if profile and profile.get('original_path') and path.suffix.lower() in {'.md','.markdown'}:
                source_key=(str(path),version)
                if source_key not in verified_sources:
                    try:verified_sources[source_key]=hashlib.sha256(path.read_bytes()).hexdigest()==version
                    except OSError:verified_sources[source_key]=False
                original_path=Path(profile['original_path']);native_version=profile['original_version'];key=(str(original_path),native_version)
                if key not in documents:
                    try:
                        raw=original_path.read_bytes()
                        documents[key]=pymupdf.open(stream=raw,filetype='pdf') if hashlib.sha256(raw).hexdigest()==native_version else None
                    except (OSError,pymupdf.FileDataError):documents[key]=None
                if verified_sources[source_key] and documents[key] is not None:
                    if key not in native_marks:
                        stamps=[];business=[]
                        for page in documents[key]:
                            marks,body=page_watermarks(page,native_version);stamps.extend(marks);business.append(body)
                        native_marks[key]=(stamps,'\n'.join(business))
                    text=card.get('excerpt','');cleaned=without_watermarks(text,*native_marks[key])
                    if cleaned!=text:
                        row.update(excerpt=cleaned,pdf_text_audit={'method':'FROZEN_MARKDOWN_NATIVE_PDF_WATERMARK_PROFILE',
                            'original_excerpt_sha256':hashlib.sha256(text.encode()).hexdigest(),'removed_chars':len(text)-len(cleaned),
                            'native_original_path':str(original_path),'native_original_version':native_version})
                result.append(row)
                continue
            location = card.get('location') or {}
            match = re.match(r'^Page (\d+)(?:$| > )', str(location.get('section') or ''))
            page_number = location.get('page') or (int(match[1]) if match else None)
            if not profile or path.suffix.lower() != '.pdf' or not isinstance(page_number,int):
                result.append(row)
                continue
            key = (str(path), version)
            if key not in documents:
                try:
                    data = path.read_bytes()
                    documents[key] = pymupdf.open(stream=data, filetype='pdf') if hashlib.sha256(data).hexdigest() == version else None
                except (OSError, pymupdf.FileDataError):
                    documents[key] = None
            document = documents[key]
            if document is None or not 1 <= page_number <= len(document):
                result.append(row)
                continue
            page = document[page_number-1]
            stamps, business_text = page_watermarks(page, version)
            original = card.get('excerpt', '')
            cleaned = without_watermarks(original, stamps, business_text)
            audit = {'method': 'VERSION_BOUND_NATIVE_WATERMARK_PROFILE', 'page': page_number,
                     'original_excerpt_sha256': hashlib.sha256(original.encode()).hexdigest(),
                     'removed_chars': len(original)-len(cleaned)}
            row['excerpt'] = cleaned
            if card.get('answer_usage') == 'PRIMARY' and page_number in profile.get('reviewed_pages', []):
                native = without_watermarks(page.get_text(), stamps, business_text)
                corrected = False
                for fix in profile.get('formula_corrections', []):
                    if page_number != fix['page'] or native.count(fix['start']) != 1 or native.count(fix['end']) != 1:
                        continue
                    start = native.index(fix['start']); end = native.index(fix['end'])
                    if start < end:
                        native = native[:start]+fix['replacement']+native[end:]
                        corrected = True
                span = page_answer_span(native, question)
                if span:
                    start, end, method = span
                    quote = native[start:end].strip()
                    compact = lambda value: re.sub(r'\s+', '', value)
                    if not any(compact(line) in compact(quote) for line in cleaned.splitlines() if len(compact(line)) >= 12):
                        result.append(row)
                        continue
                    # Preserve authored paragraph labels while joining line wraps within each paragraph.
                    quote = re.sub(r'(?<![。；])\n(?![一二三四五六七八九十]+级[^\n：]{2,30}：)', '', quote)
                    row.update(excerpt=quote, lineage_evidence_id=card['evidence_id'],
                               evidence_id='native-page-'+hashlib.sha256((version+str(page_number)+quote).encode()).hexdigest(),
                               location={**location, 'page': page_number, 'native_text_start': start, 'native_text_end': end},
                               display_location=f'PDF第{page_number}页 · 同页完整原文段落')
                    audit.update(extract_method=method, formula_layout_restored=corrected,
                                 printed_page=re.search(r'^-\s*(\d+)\s*-$', page.get_text(), re.M)[1]
                                 if re.search(r'^-\s*(\d+)\s*-$', page.get_text(), re.M) else None)
            if row['excerpt'] != original:
                row['pdf_text_audit'] = audit
            result.append(row)
    finally:
        for document in documents.values():
            if document is not None:
                document.close()
        PDF_READ_LOCK.release()
    return result
