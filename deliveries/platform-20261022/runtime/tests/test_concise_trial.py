import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.answer_engine.llm.reviewed_packet_provider import sha, wire
from app.trial.platform_app import create_app
from app.trial.platform_store import PlatformStore
from scripts.prepare_concise_trial import prepare
from scripts import run_concise_reviewed_batch as batch
from test_concise_reviewed_batch import frozen, approve, fake_provider
from test_platform_existing_content import ExistingFixture, HEADERS, ask


@pytest.fixture
def reviewed(frozen, monkeypatch):
    approve(frozen); fake_provider(monkeypatch,[])
    results = batch.run_batch(frozen)
    tasks = json.loads((frozen/'packet.json').read_text(encoding='utf-8'))
    replay = {'results':[{'task_id':t['id'],'question':t['question'],'result':r['result'],
                         'raw_response_sha256':sha(frozen/'execution'/(t['id']+'_raw.json'))}
                        for t,r in zip(tasks,results)]}
    (frozen/'offline_real_response_replay.json').write_text(json.dumps(replay,ensure_ascii=False),encoding='utf-8')
    owner = {'status':'OWNER_CONFIRMED_REPLAY_ANSWERS_AND_SOURCES',
             'replay_sha256':sha(frozen/'offline_real_response_replay.json'),'items':[]}
    for r in replay['results']:
        owner['items'].append({'task_id':r['task_id'],'question':r['question'],'answer_correct':True,
            'citation_sources_correct':True,'answer_sha256':hashlib.sha256(r['result']['answer'].encode()).hexdigest(),
            'citations_sha256':hashlib.sha256(wire(r['result']['citations']).encode()).hexdigest(),
            'raw_response_sha256':r['raw_response_sha256']})
    (frozen/'owner_confirmation_20261022.json').write_text(json.dumps(owner),encoding='utf-8')
    return frozen


def test_only_confirmed_replay_history_is_imported_not_published_or_old_approval(reviewed, tmp_path):
    original = sha(reviewed/'state.json'); trial = tmp_path/'trial'
    manifest = prepare(trial,reviewed,'synthetic-candidate')
    state = PlatformStore(trial/'state.json')._read()
    assert len(state['query_runs']) == 2 and not state['knowledge'] and not state['generations'] and not state['jobs']
    assert all(r['result']['generation_mode']=='OWNER_CONFIRMED_HISTORY_NOT_NEW_GENERATION' for r in state['query_runs'].values())
    assert manifest['generation_execution_enabled'] is False and sha(reviewed/'state.json') == original
    assert not (trial/'approval.json').exists() and not (trial/'execution').exists()
    store = PlatformStore(trial/'state.json'); store.begin_run('b'*32,'保留新增记录','test')
    assert prepare(trial,reviewed,'synthetic-candidate') == manifest
    assert len(store._read()['query_runs']) == 3


def test_changed_replay_confirmation_or_source_is_rejected_before_import(reviewed, tmp_path):
    p = reviewed/'offline_real_response_replay.json'
    p.write_text(p.read_text(encoding='utf-8')+' ')
    with pytest.raises(ValueError,match='回放文件'): prepare(tmp_path/'trial',reviewed,'candidate')
    assert not (tmp_path/'trial/state.json').exists()


def test_existing_unregistered_trial_state_is_never_overwritten(reviewed,tmp_path):
    trial = tmp_path/'trial'; trial.mkdir(); (trial/'state.json').write_text('unregistered')
    with pytest.raises(ValueError,match='未登记状态'): prepare(trial,reviewed,'candidate')
    assert (trial/'state.json').read_text() == 'unregistered'


def test_trial_retrieves_and_previews_but_even_explicit_api_approval_cannot_call_model(tmp_path):
    existing = ExistingFixture(tmp_path/'source.md')
    def forbidden(*args,**kwargs): pytest.fail('trial must not construct a model provider')
    with TestClient(create_app(tmp_path/'state.json',existing=existing,provider_factory=forbidden,
                               generation_execution_enabled=False)) as client:
        state = client.get('/api/platform/state').json()
        assert state['capabilities']['generation_execution_enabled'] is False
        assert '独立试用' in state['notice']
        row = ask(client)
        preview = client.post('/api/platform/generation-preview',headers=HEADERS,
                              json={'query_run_id':row['query_run_id'],'protocol':'CONCISE_V1'}).json()
        response = client.post('/api/platform/generation/'+preview['preview_id']+'/run',headers=HEADERS,
                               json={'approved':True,'packet_sha256':preview['packet_sha256']})
        assert response.status_code == 403
        assert '未开放模型执行' in response.json()['detail']
        assert client.get('/api/platform/generation/'+preview['preview_id']).json()['status'] == 'AWAITING_APPROVAL'
        assert not (tmp_path/'runtime/generation/execution').exists()
