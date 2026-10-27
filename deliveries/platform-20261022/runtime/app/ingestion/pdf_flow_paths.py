"""Use complete native polylines; shared-line connectivity is not transitive evidence."""
import math
from collections import defaultdict
import pymupdf
from app.ingestion.pdf_flowchart import distance,edge_distance

def inside_segment(a,b,box):
    x0,y0,x1,y1=box[0]+1,box[1]+1,box[2]-1,box[3]-1
    lo,hi=0.,1.;dx,dy=b[0]-a[0],b[1]-a[1]
    for p,q in [(-dx,a[0]-x0),(dx,x1-a[0]),(-dy,a[1]-y0),(dy,y1-a[1])]:
        if abs(p)<1e-8:
            if q<0:return False
        elif p<0:lo=max(lo,q/p)
        else:hi=min(hi,q/p)
    return lo<hi and hi>0 and lo<1

def direct_paths(chart,drawings):
    nodes=chart['nodes'];paths=[];heads=[]
    for draw in drawings:
        if draw['type']=='s' and draw['width']>=.15 and all(i[0]=='l' for i in draw['items']):
            points=defaultdict(list)
            for i in draw['items']:
                a,b=tuple(i[1]),tuple(i[2]);points[a].append(b);points[b].append(a)
            ends=[p for p,adj in points.items() if len(adj)==1]
            seen=set();queue=[ends[0]] if ends else []
            while queue:
                p=queue.pop()
                if p in seen:continue
                seen.add(p);queue.extend(points[p])
            if len(ends)==2 and all(len(adj)<=2 for adj in points.values()) and len(seen)==len(points):paths.append((draw,ends,points))
        if draw['type']=='f' and len(draw['items'])==3 and all(i[0]=='l' for i in draw['items']):
            vertices=list(dict.fromkeys(tuple(i[1]) for i in draw['items']))
            if len(vertices)!=3:continue
            lengths=sorted((distance(vertices[a],vertices[b]),a,b) for a,b in [(0,1),(1,2),(2,0)])
            if lengths[1][0]<lengths[0][0]*1.1:continue
            _,a,b=lengths[0];tip=vertices[next(i for i in range(3) if i not in {a,b})];base=((vertices[a][0]+vertices[b][0])/2,(vertices[a][1]+vertices[b][1])/2)
            heads.append((draw,tip,base))
    rows=[];duplicates={}
    for head,tip,base in heads:
        key=(tuple(round(v,2) for v in tip),tuple(round(v,2) for v in base),tuple(head['fill']))
        if key in duplicates:rows.append({'head_seqno':head['seqno'],'status':'DUPLICATE_NATIVE_HEAD','duplicate_of':duplicates[key]});continue
        duplicates[key]=head['seqno'];targets=[n for n in nodes if edge_distance(tip,n['bbox'])<=2];matches=[];blocked=[]
        if len(targets)==1:
            for path,ends,points in paths:
                if path.get('color')!=head.get('fill'):continue
                for end in ends:
                    if min(distance(end,tip),distance(end,base))>1:continue
                    previous=points[end][0];dx,dy=end[0]-previous[0],end[1]-previous[1];hx,hy=tip[0]-base[0],tip[1]-base[1]
                    if (dx*hx+dy*hy)/(math.hypot(dx,dy)*math.hypot(hx,hy))<.95:continue
                    source_end=ends[1] if end==ends[0] else ends[0]
                    sources=[n for n in nodes if edge_distance(source_end,n['bbox'])<=2 or pymupdf.Rect(n['bbox']).contains(pymupdf.Point(source_end))]
                    if len(sources)!=1 or sources[0]['node_id']==targets[0]['node_id']:continue
                    excluded={sources[0]['node_id'],targets[0]['node_id']}
                    crossing=[n['node_id'] for n in nodes if n['node_id'] not in excluded and any(inside_segment(i[1],i[2],n['bbox']) for i in path['items'])]
                    if crossing:blocked.append({'path_seqno':path['seqno'],'crossed_nodes':crossing});continue
                    matches.append({'source_node_id':sources[0]['node_id'],'target_node_id':targets[0]['node_id'],'path_seqno':path['seqno'],
                                    'path_items':[[list(i[1]),list(i[2])] for i in path['items']],'source_end':list(source_end)})
        rows.append({'head_seqno':head['seqno'],'tip':list(tip),'base':list(base),'color':list(head['fill']),
            'status':'EXPLICIT_NATIVE_PATHS' if matches and not blocked else 'HELD','paths':matches,'blocked_paths':blocked})
    return rows
