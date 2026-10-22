import asyncio
import hashlib
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.trial import native_workbench as web
from app.trial import native_workbench_worker as worker
from scripts.run_source_completion_trial import save


@pytest.fixture
def app_setup(tmp_path,monkeypatch):
    source=tmp_path/'原件.pptx';source.write_bytes(b'original-version')
    record={'evidence_id':'e','source_id':'s','source_path':str(source),'source_version':hashlib.sha256(source.read_bytes()).hexdigest(),
            'file_name':source.name,'location':{'slide':1},'text':'合同金额为731万元。','scalar':{'source_context':'完整原文，合同金额为731万元。'},'source_scope':{}}
    monkeypatch.setattr(web,'JOBS',tmp_path/'jobs')
    monkeypatch.setattr(web,'native_records',lambda:[record])
    monkeypatch.setattr(web,'validate_manifest',lambda:{'candidate_hash':'candidate'})
    monkeypatch.setattr(web,'tasks',set())
    async def finish(folder):
        state=web.read(folder/'state.json');state.update(status='complete',stage='完成',result={'answer':'测试结果','citations':[]})
        save(folder/'state.json',state)
    monkeypatch.setattr(web,'run_job',finish)
    with TestClient(web.app,base_url='http://127.0.0.1:8878') as client:yield client,record


def test_local_origin_scope_history_and_source_version_guard(app_setup):
    client,record=app_setup
    status=client.get('/api/status');assert status.status_code==200
    assert not status.json()['generation_enabled'] and 'api_key' not in status.text
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/api/questions',json={'question':'合同金额？'}).status_code==403
    headers={'Origin':'http://127.0.0.1:8878'}
    assert client.post('/api/questions',headers=headers,json={'question':' ','mode':'answer'}).status_code==422
    assert client.post('/api/questions',headers=headers,json={'question':'金额','source_id':'unlisted'}).status_code==400
    response=client.post('/api/questions',headers=headers,json={'question':'合同金额？','mode':'answer','source_id':'s'})
    assert response.status_code==202
    job=response.json()['id'];assert client.get('/api/questions/'+job).json()['question']=='合同金额？'
    assert client.get('/api/questions').json()[0]['id']==job
    assert client.get('/api/questions/not-a-job').status_code==404
    evidence=client.get('/api/evidence/e').json();assert '完整原文' in evidence['text']
    assert client.get('/api/sources/s/file').content==b'original-version'
    raw={'question':'合同金额？','answer':'731万元','mode':'answer','citations':[{'evidence_id':'e'}]}
    assert web.project_result(raw)['answer']=='731万元'
    Path(record['source_path']).write_bytes(b'changed')
    assert web.project_result(raw)['status']=='SOURCE_SCOPE_MISSING' and not web.project_result(raw)['citations']
    assert client.get('/api/evidence/e').status_code==409
    assert client.get('/api/sources/s/file').status_code==409


def test_recovery_marks_interrupted_job_without_automatic_retry(tmp_path,monkeypatch):
    job=tmp_path/uuid.uuid4().hex;save(job/'state.json',{'id':job.name,'status':'running','question':'已保存问题'})
    monkeypatch.setattr(web,'JOBS',tmp_path)
    web.recover_interrupted_jobs();state=web.read(job/'state.json')
    assert state['status']=='error' and state['question']=='已保存问题' and '没有自动重试' in state['error']


def test_history_is_submission_order_even_when_older_work_finishes_last(tmp_path,monkeypatch):
    monkeypatch.setattr(web,'JOBS',tmp_path)
    save(tmp_path/'new'/'state.json',{'id':'new','created_at':'2026-10-19T02:00:00+00:00'})
    save(tmp_path/'old'/'state.json',{'id':'old','created_at':'2026-10-19T01:00:00+00:00'})
    assert [r['id'] for r in web.history()]==['new','old']


def test_unvalidated_calculation_is_recorded_without_claiming_it_was_answered(tmp_path,monkeypatch):
    folder=tmp_path/'job';save(folder/'state.json',{'id':'job','mode':'answer','question':'两项费用相差多少万元？','status':'queued'})
    async def forbidden(*args,**kwargs):raise AssertionError('Unvalidated calculation must not run an answer worker')
    monkeypatch.setattr(web.asyncio,'create_subprocess_exec',forbidden)
    asyncio.run(web.run_job(folder));state=web.read(folder/'state.json')
    assert state['status']=='complete' and state['result']['status']=='UNSUPPORTED_TASK' and '不能把列出' in state['result']['answer']


def test_sources_mode_does_not_invoke_answer_renderer(monkeypatch):
    record={'evidence_id':'e','source_id':'s'}
    monkeypatch.setattr(worker,'native_records',lambda:[record])
    from app.trial import native_workbench_candidate as candidate
    monkeypatch.setattr(candidate,'retrieve_native',lambda *args:['e'])
    class Engine:
        def run(self,*args,**kwargs):raise AssertionError('Sources mode must not invoke answers')
    result=worker.answer(Engine(),'问题',np.ones(1024),'sources')
    assert result['status']=='SOURCES_ONLY' and not result['generation_enabled']


def test_static_ui_keeps_request_identity_and_uses_text_content():
    script=(web.PAGE/'app.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in script and 'textContent' in script
    assert 'active!==id||ticket!==epoch' in script and 'nativeTrialLastJob' in script
