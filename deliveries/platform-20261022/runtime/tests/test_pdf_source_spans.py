from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest,pymupdf
from app.ingestion.pdf_source_spans import complete_spans,span_paragraph
from app.ingestion.pdf_paragraph_context import native_lines,compact

def fixture(tmp_path):
    path=tmp_path/'跨页.pdf';doc=pymupdf.open()
    page=doc.new_page();page.insert_text((70,90),'4.3.2 项目经理\n每月在场时间不得少于实际施工天数的80%，每少一天，',fontname='china-s')
    page=doc.new_page();page.insert_text((70,90),'承包人支付违约金；请假须按规定审批。\n4.3.3 其他事项',fontname='china-s')
    doc.save(path);doc.close();version=hashlib.sha256(path.read_bytes()).hexdigest()
    with pymupdf.open(path) as doc:
        def part(number,ids):
            lines=native_lines(doc[number-1]);text='\n'.join(lines[i]['text'] for i in ids)
            return {'page':number,'line_ids':ids,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'bbox':[min(lines[i]['bbox'][0] for i in ids),min(lines[i]['bbox'][1] for i in ids),max(lines[i]['bbox'][2] for i in ids),max(lines[i]['bbox'][3] for i in ids)]}
        first=part(1,[0,1]);second=part(2,[0]);body='\n'.join([l['text'] for l in native_lines(doc[0])]+[native_lines(doc[1])[0]['text']])
    cut=compact(body).index('实际')+1;offset=[i for i,c in enumerate(body) if not c.isspace()][cut];tail_first=body[offset:body.index('\n承包人')]
    base={'source_path':str(path),'source_version':version,'location':{'section':'Page 1'}}
    records=[{**base,'evidence_id':'left','text':body[:offset]},{**base,'evidence_id':'right','text':tail_first}]
    spec={**base,'page':1,'segments':[first,second],'context_segments':[],'paragraph_sha256':hashlib.sha256(body.encode()).hexdigest(),
        'left_id':'left','right_id':'right','mode':'PAIR_COMPLETION','cut_in_paragraph':cut,'clue_id':'test','display_location':'PDF第1、2页 · 4.3.2'}
    return path,records,spec,body

def test_adjacent_page_completion_preserves_condition_and_precise_pages(tmp_path):
    path,records,spec,body=fixture(tmp_path);before=deepcopy(records);changed=complete_spans(records,[spec])
    assert records==before
    for row in changed.values():
        assert compact(body) in compact(row['text']) and row['location']['pages']==[1,2]
        assert '4.3.3' not in row['text']

@pytest.mark.parametrize('damage',['source','coordinates','text','page','cut','tail','duplicate','nonadjacent','mixed_version'])
def test_source_boundary_tampering_stops_completion(tmp_path,damage):
    path,records,spec,_=fixture(tmp_path);specs=[spec]
    if damage=='source':path.write_bytes(b'changed')
    elif damage=='coordinates':spec['segments'][0]['bbox'][0]+=2
    elif damage=='text':spec['segments'][1]['text_sha256']='0'*64
    elif damage=='page':spec['page']=2
    elif damage=='cut':spec['cut_in_paragraph']=99999
    elif damage=='tail':records[1]['text']+='其他无关条款。'
    elif damage=='duplicate':specs.append(deepcopy(spec))
    elif damage=='nonadjacent':spec['segments'][1]['page']=3
    else:records[1]['source_version']='0'*64
    with pytest.raises((ValueError,RuntimeError)):complete_spans(records,specs)

def test_source_table_number_at_bottom_is_not_removed_as_pagination(tmp_path):
    doc=pymupdf.open();page=doc.new_page();page.insert_text((90,800),'130503');page.insert_text((290,815),'7')
    lines=native_lines(page);assert any(r['text']=='130503' for r in lines);assert not any(r['text']=='7' for r in lines)
    doc.close()



@pytest.mark.parametrize('question',[
 '根据《招标文件》，第2.9项原文是什么？',
 '根据《招标文件》，第13项管理动作原文是什么？',
 '根据《招标文件》，第十三项管理动作原文是什么？',
 '根据《招标文件》，第1.4.3条原文是什么？',
])
def test_clause_ordinals_do_not_become_list_counts(question):
    from app.retrieval.complete_lists import list_request
    assert list_request(question) is None

def test_actual_counts_still_detected():
    from app.retrieval.complete_lists import list_request
    assert list_request('EPC项目13个设计管理动作有哪些？')['expected_count']==13





@pytest.mark.parametrize('question,conflict',[
 ('通用16.2.1是否可以直接当作该项目的约定？',False),
 ('通用16.2.1是否可以直接当作本项目的约定？',False),
 ('示例厂房项目的约定是什么？',True),
])
def test_generic_project_references_are_not_new_project_names(question,conflict):
    from app.retrieval.contract_context import project_conflict
    assert project_conflict(question,{'project_selector':'示例实验中学'}) is conflict
