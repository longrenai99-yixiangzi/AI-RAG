"""Check a frozen two-question batch offline; execute only after explicit approval."""
import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.answer_engine.llm.grounded_concise import concise_packet
from app.answer_engine.llm.reviewed_packet_provider import ReviewedPacketProvider, sha, wire
from app.trial.platform_generation import GenerationWorkflow, selection_packet
from app.trial.platform_store import PlatformStore

CODE_FILES = [__file__, *[ROOT/p for p in (
    'app/answer_engine/llm/grounded_concise.py', 'app/answer_engine/llm/claim_validator.py',
    'app/answer_engine/llm/reviewed_packet_provider.py', 'app/answer_engine/llm/provider_runtime_guard.py',
    'app/trial/platform_generation.py', 'app/trial/platform_store.py',
    'app/trial/concise_extract.py', 'app/trial/source_field_answer.py',
    'app/answer_engine/question_scope.py')]]


def code_hashes():
    return {Path(p).relative_to(ROOT).as_posix(): sha(p) for p in CODE_FILES}


def current(card):
    try:
        return sha(card['source_path']) == card['source_version']
    except (OSError, KeyError):
        return False


def preflight(folder):
    folder = Path(folder)
    review = json.loads((folder/'review.json').read_text(encoding='utf-8'))
    packet, pricing = folder/'packet.json', folder/'pricing.json'
    if review['packet_sha256'] != sha(packet) or review['pricing_sha256'] != sha(pricing):
        raise ValueError('请求或核价文件已变化，原审查包不可执行。')
    if review['code_sha256'] != code_hashes():
        raise ValueError('答复或执行代码已变化，需重新冻结并审查。')
    if any(not current({'source_path':path,'source_version':digest})
           for path,digest in review.get('original_file_sha256',{}).items()):
        raise ValueError('关联原件已变化或不可读取，需重新核对来源链。')
    prices = json.loads(pricing.read_text(encoding='utf-8'))
    if sha(folder/'runtime/generation/pricing.json') != sha(pricing):
        raise ValueError('平台核价与批次核价不一致。')
    if prices['checked_on'] != datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('核价已跨日，需重新核价并重新冻结审查包。')
    tasks = json.loads(packet.read_text(encoding='utf-8'))
    if (len(tasks) != 2 or len({t['id'] for t in tasks}) != 2
            or review['max_requests'] != 2 or review['max_budget_cny'] != 1):
        raise ValueError('本批仅允许两次请求、合计预算1元。')
    store = PlatformStore(folder/'state.json')
    estimate = 0
    for task in tasks:
        row = store._read()['generations'][task['preview_id']]
        body = task['body']
        if (row['protocol'] != 'CONCISE_V1' or row['body'] != body or row['question'] != task['question']
                or row['citations'] != task['private_binding'] or row['units'] != task['units']
                or row['pricing_version'] != sha(folder/'runtime/generation/pricing.json')
                or sha(folder/'runtime/generation/previews'/task['preview_id']/'packet.json') != row['packet_sha256']):
            raise ValueError('平台冻结预览与批次内容不一致。')
        original = store.query_run(row['original_run_id'])
        if hashlib.sha256(wire(original).encode()).hexdigest() != task['local_run_sha256']:
            raise ValueError('本地回退依据已变化。')
        if any(c.get('answer_usage') != 'PRIMARY' or not current(c) for c in task['private_binding']):
            raise ValueError('主证据身份或来源版本已变化。')
        for card in task['private_binding']:
            text = Path(card['source_path']).read_text(encoding='utf-8-sig')
            normalize = lambda s: '\n'.join(line.rstrip() for line in s.splitlines())
            if normalize(card['excerpt']) not in normalize(text):
                raise ValueError('短证据不能逐字定位到原文。')
        base, units = selection_packet(task['question'], task['private_binding'])
        if body != concise_packet(task['question'], units, base) or task['units'] != units:
            raise ValueError('实际答复提示与已审请求不一致。')
        if hashlib.sha256(wire(body).encode()).hexdigest() != task['request_sha256']:
            raise ValueError('请求校验不一致。')
        # UTF-8 bytes plus a framing allowance conservatively bound input tokens.
        estimate += ((len(wire(body).encode())+4096)*prices['input_usd_per_million']
                     + body['max_tokens']*prices['output_usd_per_million'])/1_000_000*prices['fx_ceiling']
    if not 0 < estimate < 1:
        raise ValueError('保守估算超出本批合计预算或核价无效。')
    return tasks, {'status':'PREFLIGHT_PASSED_NO_HTTP', 'tasks':2, 'estimated_max_cny':round(estimate,6),
                   'packet_sha256':sha(packet), 'review_sha256':sha(folder/'review.json'), 'new_real_calls':0}


def run_batch(folder):
    folder = Path(folder)
    tasks, receipt = preflight(folder)
    approval_path = folder/'approval.json'
    if not approval_path.is_file():
        raise ValueError('本批尚未取得明确授权，未发送请求。')
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    if any(approval.get(k) != v for k,v in {'approved':True, 'packet_sha256':receipt['packet_sha256'],
            'review_sha256':receipt['review_sha256'], 'max_requests':2, 'max_budget_cny':1}.items()):
        raise ValueError('授权与本批冻结内容、次数或预算不一致。')
    # A one-shot marker survives a failed/partial run; never recreate a paid ledger on retry.
    with (folder/'execution.started').open('x', encoding='utf-8') as stream:
        stream.write(receipt['review_sha256'])
    pool = ReviewedPacketProvider(folder/'packet.json', approval_path, folder/'execution', max_requests=2)
    if not pool.available:
        raise ValueError('本批授权未通过执行校验，未发送请求。')

    def provider_factory(packet, approval, out, max_requests):
        _, checked = preflight(folder)
        if checked['review_sha256'] != receipt['review_sha256']:
            raise ValueError('运行期间审查包已变化。')
        single = json.loads(Path(packet).read_text(encoding='utf-8'))
        if max_requests != 1 or len(single) != 1 or single[0]['body'] not in [t['body'] for t in tasks]:
            raise ValueError('单次请求不属于已审批次。')
        return pool

    workflow = GenerationWorkflow(PlatformStore(folder/'state.json'), current, provider_factory)
    results = []
    for task in tasks:
        _, checked = preflight(folder)
        if checked['review_sha256'] != receipt['review_sha256']:
            raise ValueError('运行期间审查包已变化。')
        row = workflow.store._read()['generations'][task['preview_id']]
        results.append(workflow.run(task['preview_id'], row['packet_sha256'], '明确批准的新协议验证'))
        (folder/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('mode', choices=['check','run'])
    args = parser.parse_args()
    if args.mode == 'check':
        _, receipt = preflight(args.folder)
        (args.folder/'preflight_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(receipt))
    else:
        print(json.dumps({'completed_records':len(run_batch(args.folder))}))
