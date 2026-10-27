"""Native flowchart frames and unambiguous drawn arrows, without business inference."""
import hashlib,math
from pathlib import Path
from collections import defaultdict

import pymupdf
from app.ingestion.pdf_native_geometry import character_layer,cell_text
from app.ingestion.pdf_text_recovery import PROFILES
from app.retrieval.table_schema import PDF_READ_LOCK


def compact(text):return ''.join(text.split())
def digest(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()
def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])


def line_segments(drawings):
    result=[]
    for draw in drawings:
        for item in draw['items']:
            if item[0]=='l':result.append(tuple(item[1])+tuple(item[2]))
            elif item[0]=='re':
                x0,y0,x1,y1=item[1];result.extend([(x0,y0,x1,y0),(x0,y1,x1,y1),(x0,y0,x0,y1),(x1,y0,x1,y1)])
    return result


def cluster(values,tolerance):
    groups=[]
    for value in sorted(values):
        if groups and value-groups[-1][-1]<=tolerance:groups[-1].append(value)
        else:groups.append([value])
    return [sum(g)/len(g) for g in groups]


def edge_distance(point,box):
    x,y=point;x0,y0,x1,y1=box
    if x<x0-2 or x>x1+2 or y<y0-2 or y>y1+2:return float('inf')
    return min(abs(x-x0),abs(x-x1),abs(y-y0),abs(y-y1))


def frames_from_page(page,spec,chars,drawings):
    xs=spec['column_boundaries'];ys=spec['business_boundaries'];phases=spec['phase_boundaries']
    lanes=[]
    for c in range(2,len(xs)-1):
        box=[xs[c],spec['header_top'],xs[c+1],ys[0]];name=compact(cell_text(chars,box))
        if not name:raise ValueError('Empty flowchart lane header')
        lanes.append({'name':name,'x0':xs[c],'x1':xs[c+1],'kind':'OUTPUT' if name=='输出成果' else 'ACTOR'})
    phase_labels=[compact(cell_text(chars,[xs[0],a,xs[1],b])) for a,b in zip(phases,phases[1:])]
    business=[compact(cell_text(chars,[xs[1],a,xs[2],b])) for a,b in zip(ys,ys[1:])]
    if phase_labels!=spec['phase_labels'] or [r['name'] for r in lanes]!=spec['lane_names'] or business!=spec['business_labels']:
        raise ValueError('Flowchart reviewed grid labels changed')
    candidates=[];held=[]
    for draw in drawings:
        if len(draw['items'])!=1 or draw['items'][0][0]!='re':continue
        box=list(draw['items'][0][1]);x0,y0,x1,y1=box
        if y0<ys[0]-1 or y1>ys[-1]+1 or x1-x0<20 or y1-y0<8:continue
        owners=[r for r in lanes if x0>=r['x0']+1 and x1<=r['x1']-1]
        if len(owners)!=1:continue
        phase=[(i,a,b) for i,(a,b) in enumerate(zip(phases,phases[1:])) if y0>=a-1 and y1<=b+1]
        action=[(i,a,b) for i,(a,b) in enumerate(zip(ys,ys[1:])) if y0>=a-1 and y1<=b+1]
        if len(phase)!=1 or len(action)!=1:held.append({'seqno':draw['seqno'],'reason':'CROSSES_REVIEWED_GRID','bbox':box});continue
        text=cell_text(chars,box)
        if not text.strip():continue
        if not business[action[0][0]]:held.append({'seqno':draw['seqno'],'reason':'EMPTY_BUSINESS_LABEL','bbox':box});continue
        candidates.append({'seqno':draw['seqno'],'bbox':box,'text':text,'lane':owners[0]['name'],'kind':owners[0]['kind'],
                           'phase':phase_labels[phase[0][0]],'business':business[action[0][0]],
                           'stroke':list(draw['color']) if draw.get('color') is not None else None,
                           'fill':list(draw['fill']) if draw.get('fill') is not None else None})
    # Nested borders describe the same frame; retain the smallest containing text frame.
    nodes=[]
    for node in sorted(candidates,key=lambda n:(pymupdf.Rect(n['bbox']).get_area(),n['seqno'])):
        if any(pymupdf.Rect(node['bbox']).contains(pymupdf.Rect(old['bbox'])) and compact(node['text'])==compact(old['text']) for old in nodes):continue
        node['node_id']='flow-node-'+digest(spec['source_version'],spec['page'],node['seqno'],node['text'])
        nodes.append(node)
    return sorted(nodes,key=lambda n:(n['bbox'][1],n['bbox'][0])),held


def confirmed_arrows(nodes,drawings):
    paths=[];heads=[];held=[]
    for draw in drawings:
        if draw['type']=='s' and draw['width']>=.3 and all(i[0]=='l' for i in draw['items']):
            points=defaultdict(list)
            for item in draw['items']:
                a,b=tuple(item[1]),tuple(item[2]);points[a].append(b);points[b].append(a)
            ends=[p for p,adj in points.items() if len(adj)==1]
            if len(ends)==2 and all(len(adj)<=2 for adj in points.values()):
                seen=set();pending=[ends[0]]
                while pending:
                    point=pending.pop()
                    if point in seen:continue
                    seen.add(point);pending.extend(points[point])
                if len(seen)==len(points):paths.append((draw,ends,points))
        if draw['type']=='f' and len(draw['items'])==3 and all(i[0]=='l' for i in draw['items']):
            vertices=list(dict.fromkeys(tuple(i[1]) for i in draw['items']))
            if len(vertices)!=3:continue
            lengths=sorted((distance(vertices[a],vertices[b]),a,b) for a,b in [(0,1),(1,2),(2,0)])
            if lengths[1][0]<lengths[0][0]*1.1:continue
            _,a,b=lengths[0];tip=vertices[next(i for i in range(3) if i not in (a,b))]
            base=((vertices[a][0]+vertices[b][0])/2,(vertices[a][1]+vertices[b][1])/2);heads.append((draw,tip,base))
    edges=[]
    for head,tip,base in heads:
        targets=[n for n in nodes if edge_distance(tip,n['bbox'])<=2]
        matches=[]
        for path,ends,points in paths:
            if path.get('color')!=head.get('fill'):continue
            for end in ends:
                if min(distance(end,tip),distance(end,base))>1:continue
                previous=points[end][0];dx,dy=end[0]-previous[0],end[1]-previous[1];hx,hy=tip[0]-base[0],tip[1]-base[1]
                if (dx*hx+dy*hy)/(math.hypot(dx,dy)*math.hypot(hx,hy))<.95:continue
                source_end=ends[1] if end==ends[0] else ends[0]
                sources=[n for n in nodes if edge_distance(source_end,n['bbox'])<=2]
                if len(sources)==1 and len(targets)==1 and sources[0]['node_id']!=targets[0]['node_id']:
                    matches.append((path,sources[0],targets[0],source_end))
        if len(matches)!=1:
            held.append({'head_seqno':head['seqno'],'reason':'ENDPOINTS_NOT_UNIQUE','tip':tip});continue
        path,source,target,source_end=matches[0]
        # shortcut: diagonal connectors require a separate crossing review before admission.
        if any(abs(i[1][0]-i[2][0])>.1 and abs(i[1][1]-i[2][1])>.1 for i in path['items']):
            held.append({'head_seqno':head['seqno'],'reason':'DIAGONAL_CONNECTOR_NEEDS_REVIEW','tip':tip});continue
        # A foreign connector endpoint on this path is a possible bus/junction: do not infer its semantics.
        junction=False
        for other,ends,_ in paths:
            if other['seqno']==path['seqno']:continue
            for point in ends:
                if distance(point,source_end)<1 or distance(point,tip)<1:continue
                for item in path['items']:
                    a,b=tuple(item[1]),tuple(item[2]);length=distance(a,b)
                    if length and abs(distance(a,point)+distance(point,b)-length)<.05:junction=True
        if junction:
            held.append({'head_seqno':head['seqno'],'reason':'POSSIBLE_SHARED_BUS_OR_JUNCTION','tip':tip});continue
        crossing=False
        for node in nodes:
            if node['node_id'] in {source['node_id'],target['node_id']}:continue
            x0,y0,x1,y1=node['bbox'];x0+=1;y0+=1;x1-=1;y1-=1
            for item in path['items']:
                a,b=tuple(item[1]),tuple(item[2])
                if abs(a[0]-b[0])<.1 and x0<a[0]<x1 and max(min(a[1],b[1]),y0)<min(max(a[1],b[1]),y1):crossing=True
                elif abs(a[1]-b[1])<.1 and y0<a[1]<y1 and max(min(a[0],b[0]),x0)<min(max(a[0],b[0]),x1):crossing=True
        if crossing:
            held.append({'head_seqno':head['seqno'],'reason':'CONNECTOR_PASSES_OTHER_FRAME','tip':tip});continue
        edges.append({'edge_id':'flow-edge-'+digest(source['node_id'],target['node_id'],head['seqno']),
                      'source_node_id':source['node_id'],'target_node_id':target['node_id'],'path_seqno':path['seqno'],
                      'head_seqno':head['seqno'],'color':head['fill'],'tip':tip,'path_items':[[list(i[1]),list(i[2])] for i in path['items']],
                      'meaning':'DRAWN_DIRECTION_ONLY_NOT_APPROVAL_OR_TIME_RULE'})
    return edges,held


def extract_charts(specs):
    documents={};results=[]
    with PDF_READ_LOCK:
        try:
            for spec in specs:
                path=Path(spec['source_path']);version=spec['source_version'];key=(str(path),version)
                if key not in documents:
                    raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=version:raise ValueError('Flowchart original changed')
                    documents[key]=pymupdf.open(stream=raw,filetype='pdf')
                page=documents[key][spec['page']-1];profile=PROFILES.get(version)
                chars,_=character_layer(page.get_text('rawdict'),version,{**profile,'source_version':version} if profile else None)
                caption=compact(cell_text(chars,spec['caption_bbox']))
                if caption!=compact(spec['caption']):raise ValueError('Flowchart caption changed')
                draws=page.get_drawings();nodes,node_holds=frames_from_page(page,spec,chars,draws);edges,edge_holds=confirmed_arrows(nodes,draws)
                results.append({'spec':spec,'nodes':nodes,'edges':edges,'held_nodes':node_holds,'held_arrows':edge_holds})
        finally:
            for doc in documents.values():doc.close()
    return results
