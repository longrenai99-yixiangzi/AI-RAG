"""Reviewed native PDF grids -> complete row records, with original cell owners retained."""
import hashlib
import re
from pathlib import Path
from collections import Counter

import pymupdf
from app.ingestion.pdf_native_geometry import character_layer,reconstruct_table,cell_text
from app.ingestion.pdf_text_recovery import PROFILES
from app.retrieval.table_schema import PDF_READ_LOCK


def unwrapped(text):return ''.join(text.splitlines()).strip()
def key(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()


def extract_table_records(specs):
    documents={};records=[];notes={}
    with PDF_READ_LOCK:
        try:
            for spec in specs:
                path=Path(spec['source_path']);version=spec['source_version'];identity=(str(path),version)
                if identity not in documents:
                    raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Native table original changed')
                    documents[identity]=pymupdf.open(stream=raw,filetype='pdf')
                doc=documents[identity];page=doc[spec['page']-1]
                profile=PROFILES.get(version);profile={**profile,'source_version':version} if profile else None
                chars,_=character_layer(page.get_text('rawdict'),version,profile)
                title_chars,_=character_layer(doc[spec['caption_page']-1].get_text('rawdict'),version,profile)
                caption=unwrapped(cell_text(title_chars,spec['caption_bbox']))
                if caption!=spec['caption']:raise ValueError('Native table caption differs')
                table=reconstruct_table(chars,spec['cell_boxes'],spec['page'],spec['table'],version)
                raw_headers=[unwrapped(v) for v in table['matrix'][0]]
                if raw_headers!=spec['headers']:raise ValueError('Native table header differs')
                duplicates=Counter(raw_headers)
                headers=[f'{v}（原表第{i+1}列）' if duplicates[v]>1 else v for i,v in enumerate(raw_headers)]
                table_id='pdf-table-'+key(version,spec['caption'],spec['group_pages'])
                note_ids=[]
                for note in spec.get('notes',[]):
                    npage=doc[note['page']-1];nchars,_=character_layer(npage.get_text('rawdict'),version,profile)
                    text=unwrapped(cell_text(nchars,note['bbox']))
                    if text!=note['text']:raise ValueError('Native table footnote differs')
                    nid='pdf-table-note-'+key(version,note['page'],text);note_ids.append(nid)
                    notes[nid]={'evidence_id':nid,'source_path':str(path),'source_version':version,'file_name':path.name,'file_type':'.pdf',
                        'text':text,'heading_path':caption+' > 原表注释','location':{'page':note['page'],'bbox':note['bbox']},
                        'display_location':f'PDF第{note["page"]}页 · {caption} · 原表注释','role':'DIRECT',
                        'native_pdf_table_note':{'table_id':table_id,'page':note['page'],'caption':caption,'appendix_number':spec.get('appendix_number')}}
                for n,matrix_row in enumerate(table['matrix'][1:],2):
                    values=[unwrapped(v) for v in matrix_row]
                    summary=values[0]=='汇总得分'
                    if not values[0].isdigit() and not summary:continue
                    cells=[c for c in table['cells'] if c['row']==n]
                    requires_note=any('见注' in v for v in values)
                    if requires_note and not note_ids:raise ValueError('Unresolved table footnote dependency')
                    conflicts=[]
                    fields=dict(zip(raw_headers,values))
                    if '考察' in fields.get('评价事项','') and '评估' in fields.get('评分标准',''):
                        conflicts.append({'left_field':'评价事项','left_term':'考察','right_field':'评分标准','right_term':'评估'})
                    columns=[i+1 for i,h in enumerate(raw_headers) if h in {'标准分值','实际得分','扣分说明','评价人'}] if summary else list(range(1,len(raw_headers)+1))
                    row_headers=[headers[i-1] for i in columns];row_values=[values[i-1] for i in columns]
                    meta={'table_id':table_id,'caption':caption,'page':spec['page'],'table':spec['table'],'row':n,
                        'original_headers':[raw_headers[i-1] for i in columns],'all_original_headers':raw_headers,'column_indices':columns,
                        'cells':cells,'header_cells':[c for c in table['cells'] if c['row']==1],'group_pages':spec['group_pages'],
                        'summary_row':summary,'appendix_number':spec.get('appendix_number'),
                        'table_complete':spec['table_complete'],'notes_evidence_ids':note_ids if requires_note else [],
                        'field_term_conflicts':conflicts,'empty_columns':[i for i in columns if not values[i-1]]}
                    records.append({'evidence_id':'pdf-table-row-'+key(version,spec['page'],spec['table'],n,values),
                        'source_path':str(path),'source_version':version,'file_name':path.name,'file_type':'.pdf','table_id':table_id,
                        'text':'表名：'+caption+('（原表汇总行）' if summary else '')+'\n表头：'+' | '.join(row_headers)+'\n行：'+' | '.join(row_values),
                        'heading_path':caption,'location':{'page':spec['page'],'table':spec['table'],'row':n},
                        'display_location':f'PDF第{spec["page"]}页 · {caption} · '+('原表汇总行' if summary else f'序号{values[0]}（物理第{n}行）'),
                        'role':'DIRECT','table_evidence':{'headers':row_headers,'values':row_values},'native_pdf_table':meta})
        finally:
            for doc in documents.values():doc.close()
    groups={}
    for record in records:groups.setdefault(record['table_id'],[]).append(record)
    for group in groups.values():
        anchors={}
        for record in group:
            parts=[]
            for header,value in zip(record['native_pdf_table']['original_headers'],record['table_evidence']['values']):
                if header not in {'风险类别','风险描述','评价维度','评价事项','评分标准'}:continue
                for part in re.split(r'[，,；;。、]',value):
                    part=re.sub(r'\s+','',part);parts.append(part)
                    short=re.sub(r'^(?:负责|参与|组织|协助|制定|统筹|确定|推进|建立)(?:组织|开展)?','',part)
                    parts.extend([short,short.removesuffix('工作')])
            anchors[record['evidence_id']]={p for p in parts if 4<=len(p)<=45}
        counts=Counter(a for values in anchors.values() for a in values)
        for record in group:
            meta=record['native_pdf_table'];values=record['table_evidence']['values'];raw_headers=meta['original_headers']
            peers=[r for r in group if r['table_evidence']['values'][0]==values[0] and r['native_pdf_table']['summary_row']==meta['summary_row']]
            labels=[v for h,v in zip(raw_headers,values) if h=='评价维度']
            score_column=meta['column_indices'][raw_headers.index('标准分值')] if '标准分值' in raw_headers else None
            owners=[]
            if score_column:
                for peer in peers:
                    cell=next(c for c in peer['native_pdf_table']['cells'] if c['column']==score_column)
                    owners.append((cell['page'],cell['owner_row'],cell['owner_column'],tuple(cell['bbox'])))
            meta.update(row_anchors=sorted(a for a in anchors[record['evidence_id']] if counts[a]==1),
                item_group_rows=len(peers),item_group_label=labels[-1] if labels else meta['caption'] if meta['summary_row'] else '',
                shared_standard_score=bool(owners) and len(set(owners))==1)
    return records+list(notes.values())
