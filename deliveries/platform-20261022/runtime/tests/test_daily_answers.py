import copy
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.answer_engine.llm.llm_provider import GenerationResult
from app.trial.daily_answers import DailyAnswers, PRICE_URL
from app.trial.platform_app import create_app
from app.trial.platform_generation import GenerationWorkflow
from app.trial.platform_store import PlatformStore
from test_platform_existing_content import ExistingFixture, HEADERS, ask


@pytest.fixture
def daily(tmp_path):
    existing=ExistingFixture(tmp_path/'source.md')
    existing.status=lambda:{'candidate_hash':'a'*64,'model_http_enabled':False}
    original=tmp_path/'original.md';original.write_text('原件版本',encoding='utf-8')
    policy={'schema_version':1,'policy_id':'synthetic-finite-trial','candidate_hash':'a'*64,'model':'deepseek-v4-flash',
            'valid_days':7,'max_requests':20,'max_budget_cents':1000,'max_request_cents':100,'max_request_bytes':32768,
            'sources':[{'source_id':'SRC_fixture','source_path':str(existing.path),'source_version':existing.hash,
                        'display_file_name':'合成协调规则','original_path':str(original),'original_version':hashlib.sha256(original.read_bytes()).hexdigest()}],
            'pricing':{'source':PRICE_URL,'page_sha256':hashlib.sha256(b'approved-price-page').hexdigest(),
                       'input_usd_per_million':.3,'output_usd_per_million':1.2,'fx_ceiling':10}}
    calls=[];price_calls=[];now=[datetime(2026,10,22,2,tzinfo=timezone.utc)]
    store=PlatformStore(tmp_path/'state.json')
    class Provider:
        failed=False
        invalid=False
        def __init__(self,*args,**kwargs):pass
        def generate(self,system,user,**kwargs):
            reserved=store._read()['daily_answer_policy']['reservations']
            assert any(r['status']=='RESERVED' for r in reserved.values())
            assert any(r['status']=='RUNNING' for r in store._read()['query_runs'].values())
            calls.append(json.loads(user))
            if self.failed:raise RuntimeError('synthetic HTTP failure')
            value={'status':'ANSWERED','claims':[{'text':'协调会应记录责任人和期限。','evidence_ids':['U1'],'support_quotes':['协调会应记录责任人和期限。']}],'gaps':[]}
            return GenerationResult('invalid' if self.invalid else json.dumps(value,ensure_ascii=False),None,0,{'finish_reason':'stop'})
    flow=GenerationWorkflow(store,lambda c:hashlib.sha256(existing.path.read_bytes()).hexdigest()==c['source_version'],Provider,clock=lambda:now[0])
    def prices():price_calls.append(1);return b'approved-price-page'
    service=DailyAnswers(store,flow,existing,policy,clock=lambda:now[0],price_reader=prices)
    def run(result=None):
        row,_=store.begin_run(uuid.uuid4().hex,'协调会如何记录？','synthetic-test')
        base={'answer_status':'SOURCE_EXTRACT','generation_mode':'LOCAL_EXTRACTIVE_SUMMARY_NO_MODEL','answer':'协调会应记录责任人和期限。',
              'citations':existing.retrieve('question','request')['citations']}
        store.finish_run(row['query_run_id'],{**base,**(result or {})})
        return row['query_run_id']
    return service,flow,store,existing,policy,Provider,calls,now,price_calls,run


def approve(daily):
    service=daily[0];return service.approve(service.policy_hash,'synthetic-human-confirmation')


def test_unapproved_policy_never_constructs_call_or_reads_price(daily):
    service,_,_,_,_,_,calls,_,prices,run=daily
    assert service.apply(run())['result']['daily_model']['route']=='NOT_ACTIVE'
    assert not service.status()['approved'] and calls==prices==[]


def test_approved_one_call_reserved_before_provider_and_no_duplicate_history(daily):
    service,_,store,_,_,_,calls,_,_,run=daily;approve(daily)
    key=run();saved=service.apply(key)
    assert saved['result']['answer_status']=='MODEL_CONCISE_DRAFT' and len(calls)==1
    assert len(store._read()['query_runs'])==1 and service.status()['used_requests']==1
    assert service.status()['reserved_cny']>0
    # A repeated execution cannot consume a second reservation.
    service.apply(key)
    assert len(calls)==1 and service.status()['used_requests']==1
    assert calls[0]['units'][0]['file_name']=='source.md'


@pytest.mark.parametrize('mode',['HUMAN_REVIEWED_EXACT_QUESTION','VERIFIED_SCALAR_NO_MODEL','LOCAL_PROJECT_AREA_FIELD_NO_MODEL','LOCAL_PROJECT_MONEY_FIELD_NO_MODEL'])
def test_verified_local_routes_do_not_spend(daily,mode):
    service,*_=daily;approve(daily)
    assert service.apply(daily[-1]({'generation_mode':mode}))['result']['daily_model']['route']=='LOCAL_DIRECT'
    assert daily[6]==[] and service.status()['used_requests']==0


@pytest.mark.parametrize('method',['NATIVE_ROLE_COUNT_CLAUSE','NATIVE_SINGLE_ROW_FIELDS'])
def test_existing_native_personnel_results_do_not_spend(daily,method):
    service=daily[0];approve(daily)
    saved=service.apply(daily[-1]({'summary_audit':[{'method':method}]}))
    assert saved['result']['daily_model']['route']=='LOCAL_DIRECT' and daily[6]==[]


@pytest.mark.parametrize('change',['source_version','source_path','source_id','background','insufficient'])
def test_wrong_scope_and_missing_evidence_do_not_spend(daily,change):
    service,_,store,_,_,_,calls,_,_,run=daily;approve(daily);key=run();r=store.query_run(key)['result']
    if change=='background':r['citations'][0]['answer_usage']='BACKGROUND'
    elif change=='insufficient':r['answer_status']='EVIDENCE_INSUFFICIENT'
    else:r['citations'][0][change]='different'
    store.finish_run(key,r);saved=service.apply(key)
    assert saved['result']['daily_model']['route'] in {'OUTSIDE_APPROVED_SCOPE','NO_SUPPORTED_EVIDENCE'} and calls==[]


@pytest.mark.parametrize('change',['source','original','candidate','price','platform_disabled'])
def test_changes_stop_before_model(daily,change):
    service,flow,_,existing,policy,_,calls,now,_,run=daily;approve(daily)
    if change=='source':existing.path.write_text('changed')
    elif change=='original':
        from pathlib import Path
        Path(policy['sources'][0]['original_path']).write_text('changed')
    elif change=='candidate':existing.status=lambda:{'candidate_hash':'b'*64}
    elif change=='platform_disabled':service.store._mutate(lambda state:state['sources'].update({'SRC_fixture':{'source_id':'SRC_fixture','status':'WITHDRAWN'}}))
    else:
        now[0]+=timedelta(days=1);service.price_reader=lambda:b'changed-price-page'
    assert service.apply(run())['result']['daily_model']['route']=='NOT_SENT'
    assert calls==[] and service.status()['used_requests']==0


def test_next_day_rechecks_unchanged_price_without_new_approval(daily):
    service,_,_,_,_,_,calls,now,prices,run=daily;approve(daily)
    service.apply(run());now[0]+=timedelta(days=1);service.apply(run())
    assert len(calls)==2 and len(prices)==2 and service.status()['approved']


@pytest.mark.parametrize('limit',['count','budget','single','bytes'])
def test_hard_caps_never_overspend(daily,limit):
    service,flow,store,existing,policy,_,calls,now,prices,run=daily
    limits={'count':('max_requests',1),'budget':('max_budget_cents',1),'single':('max_request_cents',1),'bytes':('max_request_bytes',1)}
    k,v=limits[limit];policy[k]=v
    service=DailyAnswers(store,flow,existing,policy,clock=lambda:now[0],price_reader=lambda:b'approved-price-page')
    service.approve(service.policy_hash,'test');service.apply(run());service.apply(run())
    assert len(calls)==(1 if limit=='count' else 0)
    assert service.status()['reserved_cny']<=policy['max_budget_cents']/100


@pytest.mark.parametrize('failed',[True,False])
def test_transport_or_validation_failure_counts_once_and_keeps_local_fallback(daily,failed):
    service,_,_,_,_,provider,calls,_,_,run=daily;approve(daily)
    provider.failed=failed;provider.invalid=not failed
    saved=service.apply(run())
    assert saved['result']['answer_status']=='MODEL_FAILED_LOCAL_FALLBACK'
    assert len(calls)==1 and service.status()['used_requests']==1
    assert saved['result']['answer']=='协调会应记录责任人和期限。'


def test_pause_restart_resume_do_not_reset_usage_or_extend_expiry(daily):
    service,flow,store,existing,policy,_,calls,now,_,run=daily;approve(daily);service.apply(run())
    expiry=service.status()['expires_at'];service.pause('test');service.apply(run())
    restored=DailyAnswers(store,flow,existing,policy,clock=lambda:now[0],price_reader=lambda:b'approved-price-page')
    restored.approve(restored.policy_hash,'test');assert restored.status()['used_requests']==1 and restored.status()['expires_at']==expiry
    now[0]+=timedelta(days=7)
    assert restored.apply(run())['result']['daily_model']['route']=='NOT_ACTIVE'
    with pytest.raises(ValueError,match='到期'):restored.approve(restored.policy_hash,'test')
    assert len(calls)==1


def test_uncertain_save_keeps_reservation_and_blocks_further_calls(daily,monkeypatch):
    service,flow,_,_,_,_,calls,_,_,run=daily;approve(daily);real=flow.run
    def interrupted(key,packet,actor,**kwargs):
        kwargs['before_send'](service.store._read()['generations'][key])
        raise OSError('synthetic interrupted state save')
    monkeypatch.setattr(flow,'run',interrupted)
    assert service.apply(run())['result']['daily_model']['route']=='OUTCOME_UNKNOWN'
    monkeypatch.setattr(flow,'run',real);service.apply(run())
    assert calls==[] and service.status()['used_requests']==1


def test_concurrent_questions_share_one_atomic_reservation(daily,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    service,_,_,_,_,provider,calls,_,_,run=daily;approve(daily)
    entered=Event();release=Event();generate=provider.generate
    def blocked(self,*args,**kwargs):
        entered.set()
        assert release.wait(5)
        return generate(self,*args,**kwargs)
    monkeypatch.setattr(provider,'generate',blocked)
    a,b=run(),run()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(service.apply,a)
        try:
            assert entered.wait(5)
            second=pool.submit(service.apply,b).result(timeout=5)
            assert second['result']['daily_model']['route']=='NOT_SENT'
        finally:release.set()
        assert first.result(timeout=5)['result']['answer_status']=='MODEL_CONCISE_DRAFT'
    assert len(calls)==1 and service.status()['used_requests']==1


def test_approved_policy_is_frozen_and_background_is_never_sent(daily):
    service,_,store,_,policy,_,calls,_,_,run=daily;approve(daily)
    policy['sources'][0]['source_version']='b'*64
    key=run();result=store.query_run(key)['result']
    result['citations'][0]['display_file_name']='合成可读名称'
    result['citations'].append({**result['citations'][0],'citation_id':'S2','answer_usage':'BACKGROUND','excerpt':'PRIVATE_BACKGROUND_DO_NOT_SEND'})
    store.finish_run(key,result);service.apply(key)
    assert len(calls)==1
    assert calls[0]['units'][0]['file_name']=='合成可读名称'
    assert 'PRIVATE_BACKGROUND_DO_NOT_SEND' not in json.dumps(calls[0])


def test_source_change_after_preview_still_blocks_before_spending(daily,monkeypatch):
    service,flow,_,existing,_,_,calls,_,_,run=daily;approve(daily);factory=flow.provider_factory
    def changing(*args,**kwargs):
        existing.path.write_text('changed after preview')
        return factory(*args,**kwargs)
    monkeypatch.setattr(flow,'provider_factory',changing)
    saved=service.apply(run())
    assert saved['result']['daily_model']['route']=='NOT_SENT'
    assert calls==[] and service.status()['used_requests']==0


def test_original_changes_during_generation_discard_answer_without_refunding_usage(daily,monkeypatch):
    from pathlib import Path
    service,_,_,_,policy,provider,calls,_,_,run=daily;approve(daily);generate=provider.generate
    def changed(self,*args,**kwargs):
        response=generate(self,*args,**kwargs)
        Path(policy['sources'][0]['original_path']).write_text('changed during HTTP')
        return response
    monkeypatch.setattr(provider,'generate',changed)
    result=service.apply(run())['result']
    assert result['answer_status']=='SOURCE_VERSION_UNCONFIRMED' and result['citations']==[]
    assert '协调会应记录' not in result['answer']
    assert len(calls)==1 and service.status()['used_requests']==1


def test_content_backup_cannot_rewind_usage_or_resume_paused_policy(daily):
    from app.trial.platform_backup import create_backup,restore_backup
    service,_,store,_,_,_,calls,_,_,run=daily
    before_approval=create_backup(store);approve(daily);before_call=create_backup(store)
    key=run();service.apply(key);service.pause('test');expires=service.status()['expires_at']
    for backup in [before_approval,before_call]:
        restore_backup(store,backup['backup_id'],backup['sha256'],'test')
        assert service.status()['used_requests']==1 and not service.status()['active']
        assert service.status()['expires_at']==expires
        assert store.query_run(key)['result']['answer_status']=='MODEL_CONCISE_DRAFT'
    assert len(calls)==1


def test_backup_cannot_resurrect_an_approval_missing_from_current_state(daily):
    from app.trial.platform_backup import create_backup,restore_backup
    service,_,store,_,_,_,calls,_,_,_=daily;approve(daily);backup=create_backup(store)
    store._mutate(lambda state:state.pop('daily_answer_policy'))
    restore_backup(store,backup['backup_id'],backup['sha256'],'test')
    assert not service.status()['approved'] and calls==[]


def test_api_requires_exact_confirmation_and_preserves_per_request_shutdown(daily,monkeypatch,tmp_path):
    _,_,_,existing,policy,provider,calls,_,_,_=daily
    monkeypatch.setattr(DailyAnswers,'_price_page',staticmethod(lambda:b'approved-price-page'))
    # Use an API-local provider so the reservation assertion refers to this app's own store.
    class APIProvider:
        def __init__(self,*args,**kwargs):pass
        def generate(self,*args,**kwargs):
            calls.append(1)
            return GenerationResult(json.dumps({'status':'INSUFFICIENT','claims':[],'gaps':['合成缺口']},ensure_ascii=False),None,0,{'finish_reason':'stop'})
    app=create_app(tmp_path/'api.json',existing=existing,provider_factory=APIProvider,generation_execution_enabled=False,daily_policy=policy)
    with TestClient(app) as client:
        status=client.get('/api/platform/state').json();h=status['daily_model']['policy_sha256']
        payload={'action':'approve','policy_sha256':h}
        assert client.post('/api/platform/daily-model-policy',headers=HEADERS,json=payload).status_code==403
        assert client.post('/api/platform/daily-model-policy',headers=HEADERS,json={**payload,'confirmed':True}).status_code==200
        key=uuid.uuid4().hex;a=ask(client,request_id=key);b=ask(client,request_id=key)
        assert a==b and len(calls)==1 and len(app.state.platform_store._read()['query_runs'])==1
        assert existing.last_source_versions is None
        assert not client.get('/api/platform/state').json()['capabilities']['generation_execution_enabled']


def replacement(daily):
    service,flow,store,existing,policy,_,_,now,_,_=daily
    new=copy.deepcopy(policy);new['policy_id']='synthetic-next-period'
    return DailyAnswers(store,flow,existing,new,clock=lambda:now[0],price_reader=lambda:b'approved-price-page')


def test_renewal_requires_new_explicit_approval_and_inactive_previous_policy(daily):
    old=daily[0];approve(daily);new=replacement(daily)
    with pytest.raises(ValueError,match='上一期策略'):new.approve(new.policy_hash,'test')
    with pytest.raises(ValueError,match='仍在启用'):new.approve(new.policy_hash,'test',previous_policy_hash=old.policy_hash)
    assert old.status()['active'] and not new.status()['approved']


def test_renewal_archives_usage_and_old_policy_cannot_be_reactivated(daily):
    old,_,store,_,_,_,calls,now,_,run=daily;approve(daily);key=run();old.apply(key)
    previous=copy.deepcopy(store._read()['daily_answer_policy']);now[0]+=timedelta(days=8);new=replacement(daily)
    assert new.status()['previous_policy_sha256']==old.policy_hash
    new.approve(new.policy_hash,'new-human-approval',previous_policy_hash=old.policy_hash)
    assert store._read()['daily_answer_policy_history'][old.policy_hash]==previous
    assert new.status()['used_requests']==0 and new.status()['history'][0]['used_requests']==1
    new.apply(key);assert len(calls)==1
    with pytest.raises(ValueError,match='已经结束|已结束'):old.approve(old.policy_hash,'test',previous_policy_hash=new.policy_hash)


@pytest.mark.parametrize('pending',['reservation','generation','query'])
def test_renewal_blocks_unsettled_requests(daily,pending):
    old,_,store,_,_,_,_,_,_,_=daily;approve(daily);old.pause('test');new=replacement(daily)
    def change(state):
        if pending=='reservation':state['daily_answer_policy']['reservations']['pending']={'cents':1,'status':'RESERVED'}
        elif pending=='generation':state['generations']['pending']={'status':'EXECUTING'}
        else:state['query_runs']['pending']={'status':'RUNNING'}
    store._mutate(change)
    with pytest.raises(ValueError,match='待对账'):new.approve(new.policy_hash,'test',previous_policy_hash=old.policy_hash)
    assert store._read()['daily_answer_policy']['policy_sha256']==old.policy_hash


def test_restore_keeps_both_current_policy_and_archived_ledgers(daily):
    from app.trial.platform_backup import create_backup,restore_backup
    old,_,store,_,_,_,_,_,_,run=daily;approve(daily);old.apply(run());backup=create_backup(store);old.pause('test')
    new=replacement(daily);new.approve(new.policy_hash,'test',previous_policy_hash=old.policy_hash)
    new.apply(run());new.pause('test')
    before=copy.deepcopy(store._read());restore_backup(store,backup['backup_id'],backup['sha256'],'test')
    after=store._read()
    for key in ['daily_answer_policy','daily_answer_policy_history']:assert after[key]==before[key]
    assert new.status()['used_requests']==1 and new.status()['history'][0]['used_requests']==1 and not new.status()['active']


def test_same_policy_cannot_be_renewed_with_reset_budget(daily):
    old=daily[0];approve(daily);old.pause('test')
    with pytest.raises(ValueError,match='新的策略'):old.approve(old.policy_hash,'test',previous_policy_hash=old.policy_hash)


def test_api_renewal_requires_confirmation_and_exact_previous_hash(daily,monkeypatch,tmp_path):
    old,_,store,existing,policy,_,calls,_,_,_=daily;approve(daily);old.pause('test')
    new_policy=copy.deepcopy(policy);new_policy['policy_id']='synthetic-api-next-period'
    monkeypatch.setattr(DailyAnswers,'_price_page',staticmethod(lambda:b'approved-price-page'))
    app=create_app(store.path,existing=existing,generation_execution_enabled=False,daily_policy=new_policy)
    app.state.daily_answers.clock=old.clock
    app.state.daily_answers.generation.clock=old.clock
    with TestClient(app) as client:
        info=client.get('/api/platform/state').json()['daily_model']
        body={'action':'renew','policy_sha256':info['policy_sha256'],'previous_policy_sha256':old.policy_hash}
        assert client.post('/api/platform/daily-model-policy',headers=HEADERS,json=body).status_code==403
        assert client.post('/api/platform/daily-model-policy',headers=HEADERS,json={**body,'confirmed':True,'previous_policy_sha256':'f'*64}).status_code!=200
        response=client.post('/api/platform/daily-model-policy',headers=HEADERS,json={**body,'confirmed':True})
        assert response.status_code==200 and response.json()['active']
        assert response.json()['history'][0]['policy_sha256']==old.policy_hash and not calls
