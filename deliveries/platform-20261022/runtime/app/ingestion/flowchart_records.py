"""Readable source records for verified frames; relations stay separate from text ordering."""
from pathlib import Path
from app.ingestion.pdf_flowchart import extract_charts,digest,compact


def flowchart_records(charts):
    records=[]
    for chart in charts:
        spec=chart['spec'];base={'source_path':spec['source_path'],'source_version':spec['source_version'],
             'file_name':Path(spec['source_path']).name,'file_type':'.pdf','role':'DIRECT'}
        cid='flow-chart-'+digest(spec['source_version'],spec['page'])
        header={'chart_id':cid,'appendix':spec['appendix'],'caption':spec['caption'],'chart_start':spec['chart_start'],
                'page':spec['page'],'node_phases':spec['phase_labels'],'lane_names':spec['lane_names'],
                'business_labels':spec['business_labels'],'bbox':spec['caption_bbox']}
        records.append({**base,'evidence_id':cid,'text':spec['caption']+'\n图内阶段：'+'、'.join(spec['phase_labels'])+'\n泳道列名：'+'、'.join(spec['lane_names']),
            'heading_path':spec['caption'],'display_location':f'PDF第{spec["page"]}页 · {spec["caption"]}',
            'location':{'page':spec['page'],'bbox':spec['caption_bbox']},'native_flow_header':header})
        for node in chart['nodes']:
            meta={**header,**node,'relations_complete':False}
            column='输出成果列' if node['kind']=='OUTPUT' else '角色泳道'
            text=f'图的起点：{spec["chart_start"]}；节点所在阶段：{node["phase"]}；图内业务：{node["business"]}；{column}：{node["lane"]}。\n图框原文：'+''.join(node['text'].splitlines())
            records.append({**base,'evidence_id':node['node_id'],'text':text,'heading_path':spec['caption']+' > '+node['phase']+' > '+node['business'],
                'display_location':f'PDF第{spec["page"]}页 · 附件{spec["appendix"]}（{spec["chart_start"]}开始） · {node["phase"]} · {node["business"]} · {node["lane"]}',
                'location':{'page':spec['page'],'bbox':node['bbox']},'native_flow_node':meta})
    return records


def extract_flow_records(specs):return flowchart_records(extract_charts(specs))
