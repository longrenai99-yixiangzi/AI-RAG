"""Read native slide components without mixing notes, hidden slides or image meaning."""
import re
from app.ingestion.layout_evidence import slide_nodes
from app.ingestion.loaders.ppt_loader import PPTLoader


def native_chart_cache(chart):
    plots=[]
    try:source_plots=list(chart.plots)
    except (ValueError,AttributeError,TypeError) as error:
        return {'plots':[],'status':'UNSUPPORTED_NATIVE_CHART_CACHE_REVIEW_REQUIRED','error_type':type(error).__name__,'derived_ratios_or_totals':False,'business_review_status':'PENDING_CONTENT_REVIEW'}
    for index,plot in enumerate(source_plots,1):
        try:categories=[str(category.label) for category in plot.categories]
        except (AttributeError,ValueError,TypeError):
            plots.append({'plot':index,'status':'NON_CATEGORY_CHART_REVIEW_REQUIRED'});continue
        series=[{'name':series.name,'values':list(series.values)} for series in plot.series]
        status='NATIVE_CATEGORY_CACHE_NOT_RECALCULATED' if all(len(s['values'])==len(categories) for s in series) else 'CATEGORY_VALUE_BINDING_REVIEW_REQUIRED'
        plots.append({'plot':index,'categories':categories,'series':series,'status':status})
    return {'plots':plots,'derived_ratios_or_totals':False,'business_review_status':'PENDING_CONTENT_REVIEW'}


def slide_components(slide,width,height):
    nodes=slide_nodes(slide,width,height)
    assets=[];tables={};uncertain_groups=set();rotated=set();native_text=[]

    def walk(shapes,groups=()):
        for shape in shapes:
            identity=str(shape.shape_id)
            if shape.shape_type==6:
                xfrm=shape._element.grpSpPr.xfrm
                if xfrm is None or xfrm.chExt is None or xfrm.chOff is None or xfrm.get('rot','0')!='0' or xfrm.get('flipH') in {'1','true'} or xfrm.get('flipV') in {'1','true'}:
                    uncertain_groups.add(identity)
                walk(shape.shapes,groups+(identity,));continue
            if shape.rotation:rotated.add(identity)
            if getattr(shape,'has_text_frame',False) and shape.text.strip():
                native_text.append({'shape_id':identity,'group_ids':list(groups),'text':shape.text.strip()})
            if getattr(shape,'has_table',False):
                table=shape.table
                cells=[{'row':r+1,'column':c+1,'text':cell.text,'is_merge_origin':cell.is_merge_origin,'is_spanned':cell.is_spanned,'span_width':cell.span_width,'span_height':cell.span_height} for r,row in enumerate(table.rows) for c,cell in enumerate(row.cells)]
                tables[identity]=cells
            kind=None
            if shape.shape_type==13:kind='PICTURE'
            elif getattr(shape,'has_chart',False):kind='CHART'
            elif shape.shape_type in (7,10):kind='OLE_OBJECT'
            elif shape._element.xpath('.//a:graphicData[@uri="http://schemas.openxmlformats.org/drawingml/2006/diagram"]'):kind='SMARTART'
            if kind:
                props=shape._element.xpath('.//p:cNvPr')
                asset={'shape_id':identity,'group_ids':list(groups),'kind':kind,'alt_text':props[0].get('descr','') if props else '', 'meaning_status':'NOT_VERIFIED'}
                if kind=='CHART':asset['native_chart_cache']=native_chart_cache(shape.chart)
                assets.append(asset)
    walk(slide.shapes)
    hidden=slide._element.get('show','1') in {'0','false','off'}
    for node in nodes:
        reasons=[]
        if hidden:reasons.append('HIDDEN_SLIDE_REVIEW_REQUIRED')
        if any(g in uncertain_groups for g in node['groups']):reasons.append('GROUP_TRANSFORM_REVIEW_REQUIRED')
        if node['shape_id'] in rotated:reasons.append('ROTATED_SHAPE_REVIEW_REQUIRED')
        if node.get('kind')=='table':
            node['native_cells']=tables[node['shape_id']]
            if any(cell['is_merge_origin'] or cell['is_spanned'] for cell in node['native_cells']):reasons.append('MERGED_TABLE_REVIEW_REQUIRED')
        node['review_reasons']=reasons
    notes=PPTLoader._notes_text(slide) if slide.has_notes_slide else ''
    assert len({n['shape_id'] for n in nodes})==len(nodes),'Duplicate shape IDs in one slide'
    located={n['shape_id'] for n in nodes}
    unlocated=[{**item,'status':'TEXT_GEOMETRY_UNRESOLVED'} for item in native_text if item['shape_id'] not in located]
    return {'hidden':hidden,'nodes':nodes,'unlocated_text':unlocated,'speaker_notes':{'text':notes,'role':'SPEAKER_NOTES_NOT_SLIDE_BODY','business_review_status':'PENDING_CONTENT_REVIEW'},'assets':assets,'unsupported_group_transforms':sorted(uncertain_groups)}


def resolve_inherited_text(item,native,source_version,profile_version,width,height):
    if source_version!=profile_version:raise ValueError('Inherited-geometry source version mismatch')
    data=native.get('data',{})
    if not native.get('success') or data.get('matches')!=1:raise ValueError('Ambiguous OfficeCLI shape')
    found=data['results'][0];fmt=found['format'];normalize=lambda value:re.sub(r'\s+','',value)
    if str(fmt['id'])!=item['shape_id'] or normalize(found['text'])!=normalize(item['text']):raise ValueError('OfficeCLI shape text or ID mismatch')
    def length(value):
        match=re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*(pt|cm|mm|in|emu)',str(value))
        if not match:raise ValueError('Unsupported native length')
        return float(match[1])*{'pt':12700,'cm':360000,'mm':36000,'in':914400,'emu':1}[match[2]]
    keys=['effective.x','effective.y','effective.width','effective.height']
    if not all(fmt.get(key+'.src') for key in keys):raise ValueError('Missing inherited-geometry provenance')
    x,y,w,h=[length(fmt[key]) for key in keys]
    if w<=0 or h<=0 or width<=0 or height<=0:raise ValueError('Invalid inherited shape dimensions')
    size=fmt.get('effective.size');font_size=length(size)/12700 if size else None
    return {'shape_id':item['shape_id'],'groups':item['group_ids'],'bbox':[x/width,y/height,(x+w)/width,(y+h)/height],'text':item['text'],'bold':fmt.get('effective.bold') in {True,'true','1'},'font_size':font_size,'paragraphs':[{'text':item['text'],'bold':False,'font_size':font_size}],'kind':'text','review_reasons':[],'geometry_origin':'OFFICECLI_EFFECTIVE_INHERITED','geometry_provenance':{key:fmt[key] for key in [*keys,*(key+'.src' for key in keys)]}}
