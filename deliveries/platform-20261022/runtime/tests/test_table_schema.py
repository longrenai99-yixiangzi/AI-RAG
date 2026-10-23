import copy
import hashlib
from pathlib import Path

import pymupdf
import pytest

from app.retrieval.table_schema import schema_request,schema_bundle,enforce_schema,header_from_page
from app.trial.assisted_chat import assemble
from app.retrieval.complete_lists import enforce_complete_list
from test_daily_answers import daily,approve

QUESTION='依据《测试手册》“设备交接清单”有哪些字段？'


def pdf_record(tmp_path):
    path=tmp_path/'测试手册.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=520,height=400)
        page.insert_text((150,125),'设备交接清单',fontname='china-s',fontsize=12)
        for x in [50,130,310,470]:page.draw_line((x,150),(x,250))
        for y in [150,200,250]:page.draw_line((50,y),(470,y))
        for x,y,text in [(65,180,'序号'),(160,180,'交付类别'),(340,172,'计划'),(340,190,'日期'),
                         (65,230,'1'),(160,230,'示例设备'),(340,230,'XX月XX日')]:
            page.insert_text((x,y),text,fontname='china-s',fontsize=12)
        page.insert_text((235,195),'水印干扰',fontname='china-s',fontsize=12,rotate=90)
        pdf.save(path)
    return {'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'file_name':path.name,
            'source_id':'SRC_schema','document_id':'doc','evidence_id':'page1','heading_path':'Page 1',
            'text':'设备交接清单\n序号\n交付类别\n计划\n日期\n1\n示例设备\nXX月XX日','location':{'section':'Page 1'}}


def native_result(row,question=QUESTION):
    b=schema_bundle(question,[row],[]);_,cards=assemble(b,question,True)
    return enforce_schema(question,{'table_schema_audit':b['table_schema_audit'],'citations':cards})


@pytest.mark.parametrize('question',[
    QUESTION,'《测试手册》中设备交接清单有哪些栏目？','依据《测试手册》附件3，“设备交接清单”有哪些表头字段？',
    '依据局《测试手册》附件3，设备交接清单有哪些栏目？',
])
def test_request_binds_named_source_and_explicit_table_title(question):
    assert schema_request(question)['title']=='设备交接清单'
    assert schema_request('设备交接清单有哪些字段？') is None


def test_native_grid_header_filters_rotated_watermark_and_never_uses_example_values(tmp_path):
    row=pdf_record(tmp_path);header=header_from_page(row['source_path'],1,'设备交接清单')
    assert [x['name'] for x in header['fields']]==['序号','交付类别','计划日期']
    result=native_result(row)
    assert result['answer_status']=='SOURCE_EXTRACT' and result['generation_mode']=='VERIFIED_TABLE_SCHEMA_NO_MODEL'
    assert all(x not in result['answer'] for x in ['示例设备','XX月XX日','水印干扰'])
    assert result['answer_completeness']=='COLUMN_LABELS_ONLY'
    assert enforce_complete_list(QUESTION,result)['answer_status']=='SOURCE_EXTRACT'


@pytest.mark.parametrize('change',['version','excerpt','fields','missing_fields','primary','question','page'])
def test_old_or_modified_proof_never_becomes_a_field_answer(tmp_path,change):
    row=pdf_record(tmp_path);result=native_result(row);q=QUESTION
    if change=='version':Path(row['source_path']).write_bytes(b'changed')
    if change=='excerpt':result['citations'][0]['excerpt']='另一张表'
    if change=='fields':result['table_schema_audit']['fields'][1]['name']='伪造字段'
    if change=='missing_fields':result['table_schema_audit'].pop('fields')
    if change=='primary':result['citations'][0]['answer_usage']='BACKGROUND'
    if change=='question':q=QUESTION.replace('设备交接清单','其他交接清单')
    if change=='page':result['citations'][0]['location']['page']=99
    assert enforce_schema(q,result)['answer_status']=='TABLE_SCHEMA_UNVERIFIED'


@pytest.mark.parametrize('tail',['有哪些字段，本项目实际应填多少？','有哪些字段，谁负责填写？','有哪些字段，2027年应填什么？',
                                '有哪些必填字段？','除序号外有哪些字段？','有哪些字段及填写要求？','有哪些字段，含义是什么？','有哪些字段可以不填？'])
def test_template_header_cannot_fill_project_values_or_responsibilities(tmp_path,tail):
    row=pdf_record(tmp_path);q='《测试手册》“设备交接清单”'+tail
    assert schema_request(q)['extra_details']
    assert native_result(row,q)['answer_status']=='TABLE_SCHEMA_UNVERIFIED'


def test_wrong_column_count_is_not_forced_to_the_question(tmp_path):
    row=pdf_record(tmp_path);q='《测试手册》“设备交接清单”的4个字段有哪些？'
    assert native_result(row,q)['answer_status']=='TABLE_SCHEMA_UNVERIFIED'


def test_ambiguous_pages_missing_table_and_wrong_appendix_fail_closed(tmp_path):
    row=pdf_record(tmp_path)
    duplicate={**row,'heading_path':'Page 2','evidence_id':'page2'}
    b=schema_bundle(QUESTION,[row,duplicate],[])
    assert not b['candidate_evidence']
    q=QUESTION.replace('设备交接清单','其他交接清单')
    assert native_result(row,q)['answer_status']=='TABLE_SCHEMA_UNVERIFIED'
    q=QUESTION.replace('》','》附件3',1)
    assert native_result(row,q)['answer_status']=='TABLE_SCHEMA_UNVERIFIED'


def test_schema_stays_local_and_old_preview_cannot_invent_fill_values(daily,tmp_path):
    service,flow,store,_,_,_,calls,_,prices,run=daily;approve(daily)
    key=run();preview=flow.prepare(key,'CONCISE_V1');native=native_result(pdf_record(tmp_path))
    def change(state):
        state['query_runs'][key].update(question=QUESTION,result=native)
        state['generations'][preview['preview_id']].update(question=QUESTION)
    store._mutate(change);before=len(prices)
    assert service.apply(key)['result']['daily_model']['route']=='LOCAL_DIRECT'
    with pytest.raises(ValueError,match='原表栏目'):flow.prepare(key,'CONCISE_V1')
    with pytest.raises(ValueError,match='原表栏目'):flow.run(preview['preview_id'],preview['packet_sha256'],'test')
    assert not calls and len(prices)==before and service.status()['used_requests']==0


def test_verified_pdf_page_preview_returns_image_and_keeps_original(tmp_path):
    from fastapi.testclient import TestClient
    from app.trial.platform_app import create_app
    from test_platform_existing_content import ExistingFixture
    existing=ExistingFixture(tmp_path/'placeholder.md');row=pdf_record(tmp_path)
    existing.path=Path(row['source_path']);existing.hash=row['source_version']
    existing.source={**row,'current_hash':row['source_version']}
    with TestClient(create_app(tmp_path/'state.json',existing=existing)) as client:
        result=client.get('/api/platform/library/SRC_schema/pages/1')
        assert result.status_code==200 and result.headers['content-type']=='image/png'
        assert result.content.startswith(b'\x89PNG') and result.headers['cache-control']=='no-store'
        assert client.get('/api/platform/library/SRC_schema/original').content==existing.path.read_bytes()
        assert client.get('/api/platform/library/SRC_schema/pages/0').status_code==422
        assert client.get('/api/platform/library/SRC_schema/pages/2').status_code==404
        assert client.get('/api/platform/library/unknown/pages/1').status_code==404
        existing.path.write_bytes(b'changed')
        assert client.get('/api/platform/library/SRC_schema/pages/1').status_code==409


def test_page_preview_rejects_change_during_rendering_and_non_pdf(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.trial.platform_app import create_app
    from test_platform_existing_content import ExistingFixture
    existing=ExistingFixture(tmp_path/'text.md')
    with TestClient(create_app(tmp_path/'state.json',existing=existing)) as client:
        assert client.get('/api/platform/library/SRC_fixture/pages/1').status_code==422
    row=pdf_record(tmp_path);existing.source={**row,'current_hash':row['source_version']}
    checks=iter([True,False]);monkeypatch.setattr(existing,'version_current',lambda source:next(checks))
    with TestClient(create_app(tmp_path/'second.json',existing=existing)) as client:
        assert client.get('/api/platform/library/SRC_schema/pages/1').status_code==409
