"""Native-document layout sidecar for isolated trials; no source rewriting or OCR."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re
import uuid

import pymupdf
from pptx import Presentation


def compact(text):
    return re.sub(r'\s+', '', str(text))


def identity(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(map(str, parts))))


def record(path, digest, location, heading, text, layout=None):
    did = identity(str(path.resolve()).casefold(), digest)
    eid = identity(did, str(location), heading)
    return {'evidence_id':eid, 'document_id':did, 'source_id':did, 'source_version':digest,
            'source_path':str(path), 'file_name':path.name, 'file_type':path.suffix.lower(),
            'heading_path':heading, 'location':location, 'text':text, 'raw_text':text,
            'lineage_status':'LINEAGE_CONFIRMED', 'layout':layout}


def slide_nodes(slide, width, height):
    """Apply every OOXML group transform before assigning any column or parent."""
    nodes = []

    def walk(shapes, transform=(1,1,0,0), groups=()):
        sx, sy, tx, ty = transform
        for shape in shapes:
            if any(value is None for value in (shape.left,shape.top,shape.width,shape.height)):
                continue  # Missing inherited geometry is retained separately by the component reader.
            box = [(shape.left*sx+tx)/width, (shape.top*sy+ty)/height,
                   ((shape.left+shape.width)*sx+tx)/width, ((shape.top+shape.height)*sy+ty)/height]
            if shape.shape_type == 6:
                xfrm = shape._element.grpSpPr.xfrm
                if xfrm is None or xfrm.chExt is None or xfrm.chOff is None:continue
                child_sx = shape.width/xfrm.chExt.cx if xfrm.chExt.cx else 1
                child_sy = shape.height/xfrm.chExt.cy if xfrm.chExt.cy else 1
                walk(shape.shapes, (sx*child_sx,sy*child_sy,tx+sx*(shape.left-xfrm.chOff.x*child_sx),ty+sy*(shape.top-xfrm.chOff.y*child_sy)), groups+(str(shape.shape_id),))
                continue
            if getattr(shape,'has_table',False):
                matrix=[[cell.text for cell in row.cells] for row in shape.table.rows]
                table_text='\n'.join(' | '.join(row) for row in matrix)
                nodes.append({'shape_id':str(shape.shape_id),'groups':list(groups),'bbox':box,'text':table_text,'bold':False,'font_size':None,'paragraphs':[],'kind':'table','matrix':matrix})
                continue
            if not getattr(shape, 'has_text_frame', False) or not shape.text.strip():
                continue
            paragraphs = []
            for paragraph in shape.text_frame.paragraphs:
                if not paragraph.text.strip():
                    continue
                sizes = [run.font.size.pt for run in paragraph.runs if run.font.size]
                paragraphs.append({'text':paragraph.text.strip(), 'bold':any(run.font.bold for run in paragraph.runs), 'font_size':max(sizes) if sizes else None})
            sizes = [p['font_size'] for p in paragraphs if p['font_size']]
            nodes.append({'shape_id':str(shape.shape_id), 'groups':list(groups), 'bbox':box,
                          'text':shape.text.strip(), 'bold':any(p['bold'] for p in paragraphs),
                          'font_size':max(sizes) if sizes else None, 'paragraphs':paragraphs})
    walk(slide.shapes)
    return nodes


def list_regions(nodes):
    anchors = [n for n in nodes if .14 <= n['bbox'][1] <= .65 and len(compact(n['text'])) <= 30
               and re.search(r'模块|要点|问题|困难|流程|维度', compact(n['text']))
               and (n['bold'] or (n['font_size'] or 0) >= 18)]
    # A long paragraph containing headings is not itself a region heading.
    anchors = [n for n in anchors if len(n['paragraphs']) <= 2]
    regions = []
    for anchor in anchors:
        peers = sorted([n for n in anchors if abs(n['bbox'][1]-anchor['bbox'][1]) < .075], key=lambda n:n['bbox'][0])
        index = peers.index(anchor)
        # shortcut: left-aligned peer headings define columns; centered/overlapping headings need a layout model review.
        left = anchor['bbox'][0]-.025 if index else 0
        right = peers[index+1]['bbox'][0]-.025 if index+1<len(peers) else 1
        below = [n for n in nodes if n is not anchor and n['bbox'][1] > anchor['bbox'][1]+.03 and left <= (n['bbox'][0]+n['bbox'][2])/2 < right]
        headings = []
        for n in below:
            if len(compact(n['text'])) <= 32 and not re.fullmatch(r'[\d\W]+', n['text']) and (n['bold'] or (n['font_size'] or 0) >= 17):
                headings.append({'text':compact(n['text']), 'shape_id':n['shape_id'], 'bbox':n['bbox'], 'group_path':n['groups']})
            elif len(n['paragraphs']) > 1:
                for p in n['paragraphs']:
                    if p['bold'] and len(compact(p['text'])) <= 32:
                        headings.append({'text':compact(p['text']), 'shape_id':n['shape_id'], 'bbox':n['bbox'], 'group_path':n['groups']})
        unique = {h['text']:h for h in headings}
        items = sorted(unique.values(), key=lambda h:(round(h['bbox'][1]/.08),h['bbox'][0],headings.index(h)))
        if 2 <= len(items) <= 12:
            regions.append({'kind':'list_group', 'label':compact(anchor['text']), 'region_count':len(peers),
                            'items':items, 'bbox':[left,anchor['bbox'][1],right,1], 'anchor_shape_id':anchor['shape_id'],
                            'relation_status':'SPATIAL_CANDIDATE_NOT_OWNER_APPROVED'})
    return regions


def labeled_text_regions(nodes):
    """Bound explicit problem/measure labels across columns or stacked panels."""
    labels={'存在问题','改进措施','解决措施'}
    eligible=[n for n in nodes if n.get('bbox') and not n.get('review_reasons') and n.get('kind')!='table']
    anchors=[n for n in eligible if compact(n['text']).strip('【】[]:：') in labels]
    result=[]
    for anchor in anchors:
        cy=(anchor['bbox'][1]+anchor['bbox'][3])/2
        peers=sorted([n for n in anchors if abs((n['bbox'][1]+n['bbox'][3])/2-cy)<.075],key=lambda n:n['bbox'][0])
        centers=[(n['bbox'][0]+n['bbox'][2])/2 for n in peers];index=peers.index(anchor)
        left=(centers[index-1]+centers[index])/2 if index else 0
        right=(centers[index]+centers[index+1])/2 if index+1<len(peers) else 1
        following=[n['bbox'][1] for n in anchors if n['bbox'][1]>anchor['bbox'][1]+.075 and left<=(n['bbox'][0]+n['bbox'][2])/2<=right]
        bottom=min(following,default=1);members=[];crossing=[]
        for node in eligible:
            if node in anchors:continue
            x0,y0,x1,y1=node['bbox'];x=(x0+x1)/2;y=(y0+y1)/2
            if left<=x<=right and anchor['bbox'][1]-.015<=y<bottom:
                if x0<left-.02 or x1>right+.02 or y1>bottom+.015:crossing.append(node['shape_id'])
                else:members.append(node)
        members.sort(key=lambda n:(n['bbox'][1],n['bbox'][0]))
        result.append({'label':compact(anchor['text']).strip('【】[]:：'),'anchor_shape_id':anchor['shape_id'],'bbox':[left,anchor['bbox'][1],right,bottom],'shape_ids':[n['shape_id'] for n in members],'text':'\n'.join(n['text'] for n in members),'cross_boundary_shape_ids':crossing,'status':'NATIVE_LABELED_REGION_CANDIDATE'})
    return result


def pptx_evidence(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    presentation = Presentation(path)
    records = []
    for number, slide in enumerate(presentation.slides,1):
        nodes = slide_nodes(slide,presentation.slide_width,presentation.slide_height)
        context = ' > '.join(n['text'].replace('\n',' ') for n in nodes if n['bbox'][1] < .14)
        text = '\n'.join(n['text'] for n in nodes)
        if not text:
            continue
        parent = record(path,digest,{'slide':number},context or f'Slide {number}',text)
        parent['layout'] = {'kind':'slide_parent','nodes':nodes}
        records.append(parent)
        for region in list_regions(nodes):
            region['context'] = context
            region['source_context'] = text
            heading = context+' > '+region['label']
            body = heading+'\n'+'\n'.join(f'{i}. {item["text"]}' for i,item in enumerate(region['items'],1))
            child = record(path,digest,{'slide':number,'region_bbox':region['bbox'],'shape_ids':[i['shape_id'] for i in region['items']]},heading,body,region)
            child['parent_evidence_id'] = parent['evidence_id']
            records.append(child)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    return records


def pdf_evidence(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records = []
    with pymupdf.open(path) as document:
        repeated = Counter(line.strip() for page in document for line in page.get_text().splitlines()[:2] if line.strip())
        for number,page in enumerate(document,1):
            text = page.get_text()
            lines = [s.strip() for s in text.splitlines() if s.strip()]
            meaningful = [s for s in lines if not s.isdigit() and repeated[s] < max(3,len(document)*.3)]
            title = meaningful[0] if meaningful else f'Page {number}'
            footer = page.get_text(clip=pymupdf.Rect(0,page.rect.height*.88,page.rect.width,page.rect.height)).strip()
            printed = int(footer) if footer.isdigit() else None
            parent = record(path,digest,{'page':number,'printed_page':printed},title,text)
            records.append(parent)
            try:
                tables = page.find_tables().tables
            except Exception as error:
                parent['table_parse_error'] = str(error)
                continue
            for table_number,table in enumerate(tables,1):
                matrix = table.extract()
                if len(matrix)<2:
                    continue
                option_columns = [i for i,value in enumerate(matrix[0]) if re.fullmatch(r'方案[一二三四五六七八九十\d]+',compact(value or ''))]
                options = [{'text':compact(matrix[1][i]),'row':2,'column':i+1} for i in option_columns if i<len(matrix[1]) and matrix[1][i]]
                if len(options)<2:
                    continue
                location = {'page':number,'printed_page':printed,'table':table_number,'table_bbox':list(table.bbox),'option_row':2}
                layout = {'kind':'comparison_options','label':title,'context':title,'source_context':text,'items':options,'matrix':matrix,'cell_bboxes':[list(c) if c else None for c in table.cells], 'relation_status':'NATIVE_TABLE_NOT_OWNER_APPROVED'}
                body = title+'\n'+ '\n'.join(' | '.join(str(v or '') for v in row) for row in matrix)
                child = record(path,digest,location,title+' > 方案列',body,layout)
                child['parent_evidence_id'] = parent['evidence_id']
                records.append(child)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    return records
