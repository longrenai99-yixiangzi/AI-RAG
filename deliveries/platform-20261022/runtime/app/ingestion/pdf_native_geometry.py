"""Source-bound native PDF characters and cell geometry; never edits a PDF."""
from collections import defaultdict
import math


def character_layer(raw,source_version,profile=None):
    if profile and profile['source_version']!=source_version:raise ValueError('PDF exclusion profile version mismatch')
    kept=[];excluded=[]
    for block in raw['blocks']:
        if block['type']!=0:continue
        for line in block['lines']:
            for span in line['spans']:
                matches=bool(profile and span.get('alpha',255)==profile['alpha'] and span['font']==profile['font']
                             and math.isclose(span['size'],profile['size'],abs_tol=.01)
                             and all(math.isclose(a,b,abs_tol=.0001) for a,b in zip(line['dir'],profile['direction'])))
                if matches:
                    excluded.append({'text':''.join(c['c'] for c in span['chars']),'bbox':list(span['bbox']),'alpha':span.get('alpha',255),'direction':line['dir']})
                    continue
                kept.extend({'text':c['c'],'bbox':list(c['bbox']),'origin':list(c['origin']),'direction':list(line['dir'])} for c in span['chars'])
    return kept,excluded


def cell_text(chars,box):
    lines=defaultdict(list);selected=[]
    for char in chars:
        x0,y0,x1,y1=char['bbox'];x=(x0+x1)/2;y=(y0+y1)/2
        if box[0]<=x<=box[2] and box[1]<=y<=box[3]:
            selected.append(char);lines[round(char['origin'][1]*2)/2].append(char)
    if any(abs(char['direction'][1])>.01 or char['direction'][0]<.99 for char in selected):
        raise ValueError('Non-horizontal business text needs separate layout review')
    return '\n'.join(''.join(c['text'] for c in sorted(line,key=lambda c:c['origin'][0])).strip() for _,line in sorted(lines.items())).strip()


def reconstruct_table(chars,cell_boxes,page,table,source_version):
    rows=len(cell_boxes);cols=len(cell_boxes[0]);assert rows and cols and all(len(row)==cols for row in cell_boxes)
    owners=[(r,c,box) for r,row in enumerate(cell_boxes) for c,box in enumerate(row) if box]
    xs=sorted({round(box[i],2) for _,_,box in owners for i in (0,2)})
    ys=sorted({round(box[i],2) for _,_,box in owners for i in (1,3)})
    if len(xs)!=cols+1 or len(ys)!=rows+1:raise ValueError('Ambiguous native table grid')
    cells=[];matrix=[]
    for r,row in enumerate(cell_boxes):
        values=[]
        for c,box in enumerate(row):
            inherited=box is None
            if inherited:
                cx=(xs[c]+xs[c+1])/2;cy=(ys[r]+ys[r+1])/2
                candidates=[owner for owner in owners if owner[2][0]<=cx<=owner[2][2] and owner[2][1]<=cy<=owner[2][3]]
                if len(candidates)!=1:raise ValueError('Missing or ambiguous merged-cell owner')
                owner_r,owner_c,box=candidates[0]
            else:owner_r,owner_c=r,c
            text=cell_text(chars,box);values.append(text)
            cells.append({'page':page,'table':table,'row':r+1,'column':c+1,'text':text,'bbox':list(box),'merged_inheritance':inherited,'owner_row':owner_r+1,'owner_column':owner_c+1})
        matrix.append(values)
    return {'page':page,'table':table,'source_version':source_version,'matrix':matrix,'cells':cells,'column_boundaries':xs,'row_boundaries':ys,'status':'NATIVE_GEOMETRY_CANDIDATE_NOT_BUSINESS_APPROVED'}


def join_continuation(left,right,profile):
    if left['source_version']!=profile['source_version'] or right['source_version']!=profile['source_version']:
        raise ValueError('Cross-version PDF continuation')
    if (left['page'],left['table'],right['page'],right['table'])!=tuple(profile['tables']):
        raise ValueError('Continuation is outside the reviewed table pair')
    if right['page']!=left['page']+1 or len(left['column_boundaries'])!=len(right['column_boundaries']):raise ValueError('Non-adjacent or incompatible tables')
    if any(abs(a-b)>1 for a,b in zip(left['column_boundaries'],right['column_boundaries'])):raise ValueError('Cross-page columns do not align')
    tail=left['matrix'][-1];head=right['matrix'][0];column=profile['continuation_column']-1
    if not tail[0].isdigit() or head[0] or any(value for i,value in enumerate(head) if i!=column):raise ValueError('Ambiguous continuation row')
    if len(right['matrix'])<2 or not right['matrix'][1][0].isdigit() or int(right['matrix'][1][0])!=int(tail[0])+1:raise ValueError('Unproven continuation sequence')
    merged=[row[:] for row in left['matrix']];merged[-1][column]+='\n'+head[column]
    merged.extend(right['matrix'][1:])
    return {'source_version':left['source_version'],'matrix':merged,'fragments':left['cells']+right['cells'],'joined_row_fragments':[{'page':left['page'],'table':left['table'],'row':len(left['matrix'])},{'page':right['page'],'table':right['table'],'row':1}],'status':'PROFILED_ADJACENT_CONTINUATION_CANDIDATE'}


def outline_anchors(toc,pages):
    normalize=lambda value:''.join(c.lower() for c in value if c.isalnum())
    result=[]
    for index,(level,title,page) in enumerate(toc):
        item={'entry':index+1,'level':level,'title':title,'page':page,'status':'DESTINATION_TITLE_NOT_VERIFIED'}
        if page<=0:item['status']='NO_IN_DOCUMENT_DESTINATION';result.append(item);continue
        if page>len(pages):item['status']='DESTINATION_OUT_OF_RANGE';result.append(item);continue
        lines=pages[page-1]['lines'];found={}
        for start in range(len(lines)):
            for length in (1,2,3):
                group=lines[start:start+length]
                if len(group)!=length or any(abs(line['direction'][1])>.01 for line in group):continue
                text=''.join(span['text'] for line in group for span in line['spans'])
                if normalize(text)==normalize(title):
                    indices=tuple(start+i for i,line in enumerate(group) if normalize(''.join(span['text'] for span in line['spans'])))
                    if indices:found[indices]=[lines[i] for i in indices]
        if len(found)==1:
            indices,group=next(iter(found.items()));item.update(status='TITLE_FOUND_AT_NATIVE_DESTINATION',line_start=indices[0]+1,bbox=[min(l['bbox'][0] for l in group),min(l['bbox'][1] for l in group),max(l['bbox'][2] for l in group),max(l['bbox'][3] for l in group)])
        elif len(found)>1:item['status']='AMBIGUOUS_DESTINATION_TITLE'
        result.append(item)
    return result
