"""Check the reviewed batch offline; run only with its separate human approval receipt."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.prompt_builder import build_prompt, build_prompt_v2
from app.answer_engine.llm.reviewed_packet_provider import ReviewedPacketProvider, sha, wire
from app.trial.assisted_chat import AssistedQuery, assemble, run_flow

HERE = Path(__file__).resolve().parent


def retrieval(task):
    return {'candidate_evidence': [
        {**card, 'document_id': card['source_id'], 'text': card['excerpt'], 'role': 'DIRECT'}
        for card in task['private_binding']
    ]}


def preflight(packet=HERE/'generation2_requests_for_review.json', price=HERE/'price_snapshot.json',expected_count=2,*,protocol_version='V1'):
    assert protocol_version in {'V1','V2'}, 'unsupported reviewed protocol'
    tasks = json.loads(Path(packet).read_text(encoding='utf-8'))
    prices = json.loads(Path(price).read_text(encoding='utf-8'))
    assert len(tasks) == expected_count and len({t['id'] for t in tasks}) == expected_count, 'batch must match the exact reviewed count'
    assert prices['request_packet_sha256'] == sha(packet), 'price snapshot binds a different packet'
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(prices['verified_at_utc'])).total_seconds()
    assert 0 <= age <= 86400, 'refresh official pricing before running this batch'
    estimate = 0
    for task in tasks:
        body = task['body']
        assert body['model'] == 'deepseek-v4-flash' and body['max_tokens'] == 4096
        assert body['response_format'] == {'type': 'json_object'} and body['thinking'] == {'type': 'disabled'}
        assert hashlib.sha256(wire(body).encode()).hexdigest() == task['request_sha256'], 'request hash mismatch'
        evidence, cards = assemble(retrieval(task))
        assert len(cards) == len(task['private_binding']) > 0, 'source missing or source version changed'
        for card in cards:
            path = Path(card['source_path'])
            normalize = lambda text: '\n'.join(line.rstrip() for line in text.splitlines())
            if path.suffix.lower()=='.docx' and 'table' in card['location']:
                from app.ingestion.scalar_evidence import _docx_parents
                loc=card['location']
                assert type(loc.get('table')) is int and type(loc.get('row')) is int and loc['table']>0 and loc['row']>0 and loc.get('header_row')==1, 'unsupported native table coordinates or header row'
                native=next((p for p in _docx_parents(path,card['source_version']) if p['location'].get('table')==loc['table'] and p['location'].get('row')==loc['row']),None)
                assert native is not None and normalize(card['excerpt'])==normalize(native['text']), 'native table row or cells differ from reviewed quote'
                continue
            if path.suffix.lower() == '.docx':
                from docx import Document
                source = '\n'.join(' '.join(p.text.split()) for p in Document(path).paragraphs if p.text.strip())
            else:
                source = path.read_text(encoding='utf-8')
            # Existing chunks trim line-end whitespace; preserve all words and paragraph anchors.
            assert normalize(card['excerpt']) in normalize(source), 'excerpt no longer matches source'
        prompt = (build_prompt_v2 if protocol_version=='V2' else build_prompt)(task['question'], policy_for_intent('GENERAL_QUERY'), evidence)
        assert body['messages'] == [{'role':'system','content':prompt.system_prompt}, {'role':'user','content':prompt.user_prompt}], 'runtime prompt differs from reviewed prompt'
        assert not re.search(r'[A-Za-z]:[\\/]',wire(body)), 'local path in outbound body'
        rates = prices['peak_cny_per_million']
        estimate += ((len(wire(body).encode())+1024)*rates['input_miss']+4096*rates['output'])/1_000_000
    assert prices['max_batch_budget_cny'] == 1 and estimate <= 1, 'estimated batch cost exceeds approved ceiling'
    return tasks, {'status':'PREFLIGHT_PASSED_NO_HTTP', 'packet_sha256':sha(packet), 'tasks':len(tasks), 'estimated_max_cny':round(estimate,6), 'new_real_calls':0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check','run'])
    args = parser.parse_args()
    tasks, receipt = preflight()
    if args.mode == 'check':
        (HERE/'preflight_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(receipt,ensure_ascii=False));return
    # One fixed output directory preserves the request limit across restarts.
    out = HERE/'real_batch_2'
    if (out/'request_attempts.jsonl').exists():raise SystemExit('本批已有计次记录，保留原结果，不重新执行。')
    provider = ReviewedPacketProvider(HERE/'generation2_requests_for_review.json', HERE/'generation2_approval.json', out)
    if not provider.available:raise SystemExit('本批没有匹配的明确授权，未发送请求。')
    for task in tasks:
        def save(run_id, state):
            (out/(task['id']+'_state.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        data = AssistedQuery(question=task['question'],conversation_id='reviewed-generation2',request_id=hashlib.sha256(task['id'].encode()).hexdigest()[:32])
        events = list(run_flow(data,lambda _:retrieval(task),ShadowAnswerGenerator(provider),save))
        (out/(task['id']+'_events.json')).write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
        print(task['id'],next(e['result']['answer_status'] for e in events if e['type']=='result'))


if __name__ == '__main__':main()
