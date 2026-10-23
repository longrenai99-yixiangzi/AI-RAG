"""Bounded appendix headings from existing PDF evidence, not full template contents."""
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from .complete_lists import NUM, number
from .named_source_scope import named_titles

APPENDIX = re.compile(r'^附件\s*('+NUM+r')\s*[：:]\s*(.{2,80})$')
CHAPTER = re.compile(r'^第('+NUM+r')章\s*(.{2,60})$')
SUBTITLE = re.compile(r'^(\d+\.\d+(?:\.\d+)*)\s*([\u4e00-\u9fff][^\n]{1,60})$')


def appendix_request(question):
    selected = re.findall(r'附件\s*('+NUM+r')', question)
    if not named_titles(question) or len(set(selected)) != 1 or not re.search(r'章节|目录|哪些章|几章', question):return None
    # Only an explicitly selected appendix is supported; do not guess from a topic name.
    return number(selected[0])


def build_outlines(records):
    sources = defaultdict(list)
    for row in records:
        page = re.fullmatch(r'Page (\d+)', row.get('heading_path', ''))
        if page:sources[(row['source_path'], row['source_version'])].append((int(page[1]), row))
    found = []
    for rows in sources.values():
        rows.sort(key=lambda item:item[0])
        lines = [(page,row,line.strip()) for page,row in rows for line in row['text'].splitlines()]
        markers = [(i,APPENDIX.fullmatch(line)) for i,(_,_,line) in enumerate(lines) if APPENDIX.fullmatch(line)]
        for (start,marker),(stop,following) in zip(markers,markers[1:]):
            if number(following[1]) != number(marker[1])+1:continue
            section = lines[start:stop+1];pages = {page for page,_,_ in section}
            if pages != set(range(min(pages),max(pages)+1)):continue
            chapters=[];invalid=False;quotes=[f'[PDF Page {lines[start][0]}] {lines[start][2]}'];heading_pages=[lines[start][0]]
            for page,row,line in lines[start+1:stop]:
                chapter=CHAPTER.fullmatch(line);subtitle=SUBTITLE.fullmatch(line)
                if chapter:
                    if number(chapter[1]) != len(chapters)+1:invalid=True;break
                    chapters.append({'number':number(chapter[1]),'title':chapter[2],'page':page,'subtitles':[]})
                    quotes.append(f'[PDF Page {page}] {line}')
                    heading_pages.append(page)
                elif subtitle and chapters and int(subtitle[1].split('.')[0])==chapters[-1]['number']:
                    chapters[-1]['subtitles'].append(subtitle[1]+' '+subtitle[2])
                    quotes.append(f'[PDF Page {page}] {line}')
                    heading_pages.append(page)
            if invalid or not chapters or len(chapters)>30:continue
            children=list(dict.fromkeys(row['evidence_id'] for _,row,_ in section))
            text='\n'.join(quotes);first=lines[start][1]
            audit={'kind':'APPENDIX_OUTLINE','appendix_number':number(marker[1]),'title':marker[2],
                   'chapters':chapters,'start_page':lines[start][0],'end_page':max(heading_pages),
                   'boundary_marker':lines[stop][2],'child_evidence_ids':children,'quote_sha256':hashlib.sha256(text.encode()).hexdigest()}
            key=hashlib.sha256((first['source_path']+first['source_version']+text).encode()).hexdigest()
            record={**first,'evidence_id':'appendix-outline-'+key,'text':text,'answer_usage':'PRIMARY','role':'DIRECT',
                    'retrieved_child_ids':children,'display_location':f'附件{audit["appendix_number"]} {audit["title"]} > PDF Page {audit["start_page"]}–{audit["end_page"]} > 章节标题摘录'}
            found.append({'kind':'APPENDIX_OUTLINE','audit':audit,'children':children,'record':record})
    return found


def outline_bundle(question,catalog,eligible,request):
    selected=appendix_request(question)
    if selected is None:return None
    rows=[row for row in catalog if row.get('kind')=='APPENDIX_OUTLINE'
          and row['audit']['appendix_number']==selected and set(row['children']).issubset(eligible)]
    # Explicit document filtering is performed by the existing caller before this selection.
    audit={**request,'kind':'APPENDIX_OUTLINE','status':'APPENDIX_OUTLINE_NOT_UNIQUE'}
    records=[]
    if len(rows)==1:
        row=rows[0];record=row['record']
        audit.update(row['audit'],source_version=record['source_version'],evidence_id=record['evidence_id'],status='INDEXED_OUTLINE_LOCATED')
        title=re.search(r'附件\s*'+NUM+r'\s*[“「『]([^”」』]+)[”」』]',question)
        if title and re.sub(r'\s+','',title[1])!=re.sub(r'\s+','',row['audit']['title']):audit['status']='APPENDIX_TITLE_MISMATCH'
        else:records=[record]
    return {'candidate_evidence':records,'bundle_status':'APPENDIX_OUTLINE_LOCATED' if records else 'COMPLETE_LIST_UNVERIFIED',
            'complete_list_audit':audit,'selection_notes':['仅定位指定附件的原文章节结构；不将目录核对冒充表格字段和填写要求已完整回答。']}


def render_outline(audit,cards,question,request):
    if request['question_sha256']!=audit.get('question_sha256') or request['details_unverified']:return None
    if appendix_request(question)!=audit.get('appendix_number') or audit.get('status')!='INDEXED_OUTLINE_LOCATED':return None
    if request.get('expected_count') is not None:return None
    card=next((c for c in cards if c.get('answer_usage')=='PRIMARY' and c.get('evidence_id')==audit.get('evidence_id')
               and c.get('source_version')==audit.get('source_version')),None)
    if not card:return None
    try:current=hashlib.sha256(Path(card['source_path']).read_bytes()).hexdigest()
    except OSError:return None
    if current!=card['source_version'] or hashlib.sha256(card['excerpt'].encode()).hexdigest()!=audit['quote_sha256']:return None
    original=[]
    for line in card['excerpt'].splitlines()[1:]:
        match=re.fullmatch(r'\[PDF Page (\d+)\] (.+)',line)
        if not match:return None
        chapter=CHAPTER.fullmatch(match[2]);subtitle=SUBTITLE.fullmatch(match[2])
        if chapter:
            if number(chapter[1])!=len(original)+1:return None
            original.append({'number':number(chapter[1]),'title':chapter[2],'page':int(match[1]),'subtitles':[]})
        elif subtitle and original:original[-1]['subtitles'].append(subtitle[1]+' '+subtitle[2])
        else:return None
    first=re.fullmatch(r'\[PDF Page \d+\] (.+)',card['excerpt'].splitlines()[0])
    marker=APPENDIX.fullmatch(first[1]) if first else None
    if not marker or number(marker[1])!=audit['appendix_number'] or marker[2]!=audit['title'] or original!=audit['chapters']:return None
    lines=[f'依据{card.get("display_file_name") or card["file_name"]}附件{audit["appendix_number"]}《{audit["title"]}》，现有同版原文定位到以下{len(audit["chapters"])}章：']
    for chapter in audit['chapters']:
        title=f'{chapter["number"]}. {chapter["title"]}'
        if chapter['subtitles']:title+='：'+'；'.join(chapter['subtitles'])+'。'
        lines.append(title)
    lines.append(f'[{card["citation_id"]}]')
    gap='本次核对的是附件边界与章节、小节标题；各表格字段、示例和填写要求未逐项组织，不能把目录当作完整内容答复。'
    details=bool(re.search(r'内容|要求|字段|表头|填写|示例|全文',question))
    if details:lines.append('尚未核定：'+gap)
    return {'answer_status':'SOURCE_EXTRACT','status_label':'附件章节已定位 · 详细内容待核定' if details else '原文附件章节结构 · 待业务核对',
            'answer':'\n'.join(lines),'citations':[card],'complete_list_audit':audit,
            'generation_mode':'VERIFIED_COMPLETE_LIST_NO_MODEL','support_check':'VERSIONED_BOUNDED_INDEX_HEADINGS',
            'answer_completeness':'PARTIAL' if details else 'INDEXED_OUTLINE_ONLY',
            'coverage_gaps':[gap] if details else [],'notice':gap+' 未确认模板现行效力，未调用生成模型。'}
