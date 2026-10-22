import hashlib
import json
from datetime import datetime, timezone, timedelta

import pytest

from app.answer_engine.llm.reviewed_packet_provider import sha, wire
from app.trial.platform_existing import source_extract
from app.trial.platform_generation import GenerationWorkflow
from app.trial.platform_store import PlatformStore
from scripts import run_concise_reviewed_batch as batch


@pytest.fixture
def frozen(tmp_path):
    folder = tmp_path/'batch'; folder.mkdir()
    prices = {'input_usd_per_million':.3, 'output_usd_per_million':1.2, 'fx_ceiling':10, 'source':'synthetic price fixture',
              'checked_on':datetime.now(timezone(timedelta(hours=8))).date().isoformat()}
    (folder/'pricing.json').write_text(json.dumps(prices), encoding='utf-8')
    store = PlatformStore(folder/'state.json')
    flow = GenerationWorkflow(store, batch.current)
    flow.pricing_path.write_bytes((folder/'pricing.json').read_bytes())
    tasks = []
    for i,(question,text) in enumerate([('协调会如何记录？','协调会应记录责任人和期限。'),
                                       ('甲项目建筑面积多少？','甲项目，建筑面积约4万平方米。')]):
        path = folder/f'source{i}.md'; path.write_text(text,encoding='utf-8')
        cards = [{'citation_id':'S1','source_id':f'D{i}','file_name':path.name,'source_path':str(path),
                  'source_version':sha(path),'excerpt':text,'display_location':'合成第1条','answer_usage':'PRIMARY'}]
        row,_ = store.begin_run(str(i+1)*32, question, '合成测试')
        store.finish_run(row['query_run_id'], source_extract({'answer_status':'SOURCES_ONLY','citations':cards}, question))
        preview = flow.prepare(row['query_run_id'], 'CONCISE_V1')
        tasks.append({'id':f'T{i+1}','question':question,'preview_id':preview['preview_id'],
                      'body':preview['body'],'units':preview['units'],'private_binding':preview['citations'],
                      'request_sha256':hashlib.sha256(wire(preview['body']).encode()).hexdigest(),
                      'local_run_sha256':hashlib.sha256(wire(store.query_run(row['query_run_id'])).encode()).hexdigest()})
    (folder/'packet.json').write_text(json.dumps(tasks,ensure_ascii=False),encoding='utf-8')
    review = {'packet_sha256':sha(folder/'packet.json'),'pricing_sha256':sha(folder/'pricing.json'),
              'max_requests':2,'max_budget_cny':1,'code_sha256':batch.code_hashes()}
    (folder/'review.json').write_text(json.dumps(review),encoding='utf-8')
    return folder


def approve(folder):
    (folder/'approval.json').write_text(json.dumps({'approved':True,'packet_sha256':sha(folder/'packet.json'),
        'review_sha256':sha(folder/'review.json'),'max_requests':2,'max_budget_cny':1}),encoding='utf-8')


def fake_provider(monkeypatch, calls, after=None):
    original = batch.ReviewedPacketProvider

    def post(body):
        calls.append(body)
        unit = json.loads(body['messages'][1]['content'])['units'][0]
        if after: after(len(calls))
        raw = {'status':'ANSWERED','claims':[{'text':unit['text'],'evidence_ids':[unit['unit_id']],
                                             'support_quotes':[unit['text']]}],'gaps':[]}
        return {'choices':[{'message':{'content':json.dumps(raw,ensure_ascii=False)},'finish_reason':'stop'}]}

    monkeypatch.setattr(batch, 'ReviewedPacketProvider', lambda *a,**kw:original(*a,**kw,transport=post))


def test_preflight_is_offline_and_no_approval_cannot_create_execution(frozen, monkeypatch):
    monkeypatch.setattr(batch, 'ReviewedPacketProvider', lambda *a,**kw:pytest.fail('must not construct provider'))
    tasks, receipt = batch.preflight(frozen)
    assert len(tasks) == 2 and receipt['new_real_calls'] == 0 and receipt['estimated_max_cny'] < 1
    with pytest.raises(ValueError,match='授权'): batch.run_batch(frozen)
    assert not (frozen/'execution.started').exists() and not (frozen/'execution').exists()


@pytest.mark.parametrize('target', ['packet.json','pricing.json','source0.md'])
def test_changed_packet_price_or_original_is_rejected(frozen, target):
    with (frozen/target).open('a',encoding='utf-8') as stream: stream.write(' changed')
    with pytest.raises(ValueError): batch.preflight(frozen)


def test_cross_day_and_changed_runtime_code_fail_closed(frozen, monkeypatch):
    p = frozen/'pricing.json'; prices = json.loads(p.read_text()); prices['checked_on']='2000-01-01'
    p.write_text(json.dumps(prices)); (frozen/'runtime/generation/pricing.json').write_bytes(p.read_bytes())
    review = json.loads((frozen/'review.json').read_text()); review['pricing_sha256']=sha(p)
    (frozen/'review.json').write_text(json.dumps(review))
    with pytest.raises(ValueError,match='跨日'): batch.preflight(frozen)
    monkeypatch.setattr(batch,'code_hashes',lambda:{})
    with pytest.raises(ValueError,match='代码'): batch.preflight(frozen)


def test_two_simulated_calls_share_budget_and_cannot_restart(frozen, monkeypatch):
    calls = []; approve(frozen); fake_provider(monkeypatch,calls)
    results = batch.run_batch(frozen)
    assert len(calls) == 2 and all(r['result']['answer_status']=='MODEL_CONCISE_DRAFT' for r in results)
    ledger = frozen/'execution/request_budget.json'
    assert json.loads(ledger.read_text())['used_real_requests'] == 2
    ledger.write_text('corrupted')
    with pytest.raises(FileExistsError): batch.run_batch(frozen)
    assert len(calls) == 2


@pytest.mark.parametrize('change', ['source','review'])
def test_mid_batch_source_or_review_change_stops_second_call(frozen, monkeypatch, change):
    calls = []; approve(frozen)

    def after(count):
        if count != 1: return
        if change == 'source': (frozen/'source1.md').write_text('changed')
        else:
            p = frozen/'review.json'; value = json.loads(p.read_text()); value['changed']=True
            p.write_text(json.dumps(value))

    fake_provider(monkeypatch,calls,after)
    with pytest.raises(ValueError): batch.run_batch(frozen)
    assert len(calls) == 1 and (frozen/'results.json').exists()


def test_changed_local_fallback_cannot_pass_approved_packet(frozen):
    store = PlatformStore(frozen/'state.json')
    original = next(iter(store._read()['query_runs']))
    row = store.query_run(original); row['result']['answer']='changed'
    store.finish_run(original,row['result'])
    with pytest.raises(ValueError,match='回退依据'): batch.preflight(frozen)


def test_changed_linked_original_also_stops_batch(frozen):
    original = frozen/'synthetic_original.md'; original.write_text('synthetic original')
    p = frozen/'review.json'; review = json.loads(p.read_text())
    review['original_file_sha256'] = {str(original):sha(original)}
    p.write_text(json.dumps(review))
    assert batch.preflight(frozen)[1]['new_real_calls'] == 0
    original.write_text('changed')
    with pytest.raises(ValueError,match='关联原件'): batch.preflight(frozen)
