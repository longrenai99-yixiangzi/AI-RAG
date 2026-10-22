"""Import owner-confirmed replay history into a separate trial, never published knowledge."""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.answer_engine.llm.reviewed_packet_provider import sha, wire
from app.trial.platform_store import PlatformStore


def prepare(folder, batch, candidate_hash):
    folder, batch = Path(folder), Path(batch)
    owner_path = batch/'owner_confirmation_20261022.json'
    replay_path = batch/'offline_real_response_replay.json'
    owner = json.loads(owner_path.read_text(encoding='utf-8'))
    replay = json.loads(replay_path.read_text(encoding='utf-8'))
    if owner['status'] != 'OWNER_CONFIRMED_REPLAY_ANSWERS_AND_SOURCES' or owner['replay_sha256'] != sha(replay_path):
        raise ValueError('业务确认与回放文件不匹配。')
    if not candidate_hash:
        raise ValueError('没有明确的既有检索版本。')
    records = {r['task_id']:r for r in replay['results']}
    if len(records) != len(owner['items']):
        raise ValueError('业务确认的题目范围不一致。')
    for item in owner['items']:
        record = records[item['task_id']]; result = record['result']
        if (item.get('answer_correct') is not True or item.get('citation_sources_correct') is not True
                or item['question'] != record['question']
                or item['answer_sha256'] != hashlib.sha256(result['answer'].encode()).hexdigest()
                or item['citations_sha256'] != hashlib.sha256(wire(result['citations']).encode()).hexdigest()
                or item['raw_response_sha256'] != record['raw_response_sha256']):
            raise ValueError('答复或引用不属于已确认的版本。')
        for card in result['citations']:
            if sha(card['source_path']) != card['source_version']:
                raise ValueError('转换稿来源版本已变化。')
    for path,digest in json.loads((batch/'review.json').read_text(encoding='utf-8')).get('original_file_sha256',{}).items():
        if sha(path) != digest:
            raise ValueError('关联原件已变化。')
    manifest = folder/'prepared.json'
    if manifest.exists():
        old = json.loads(manifest.read_text(encoding='utf-8'))
        if old['owner_confirmation_sha256'] != sha(owner_path) or old['candidate_hash'] != candidate_hash:
            raise ValueError('已有试用对应另一份确认或检索版本，未覆盖。')
        return old
    if (folder/'state.json').exists():
        raise ValueError('已有未登记状态，未覆盖用户记录。')
    folder.mkdir(parents=True,exist_ok=True)
    store = PlatformStore(folder/'state.json')
    imported = []
    for item in owner['items']:
        record = records[item['task_id']]; result = copy.deepcopy(record['result'])
        result.update(answer_status='OWNER_CONFIRMED_OFFLINE_REPLAY', status_label='已业务核对 · 历史响应离线回放',
                      generation_mode='OWNER_CONFIRMED_HISTORY_NOT_NEW_GENERATION',
                      owner_confirmation_sha256=sha(owner_path),
                      notice='用户已确认本题答案及引用来源正确。这是历史真实响应经修复后的离线回放；不是本次新生成，不代表其他问题已验收，也未发布为正式业务知识。')
        request = hashlib.sha256((sha(owner_path)+item['task_id']).encode()).hexdigest()[:32]
        row,_ = store.begin_run(request,record['question'],'已确认历史回放导入')
        store.finish_run(row['query_run_id'],result)
        imported.append(row['query_run_id'])
    price_path = folder/'runtime/generation/pricing.json'
    price_path.parent.mkdir(parents=True,exist_ok=True)
    price_path.write_bytes((batch/'pricing.json').read_bytes())
    result = {'prepared_at_utc':datetime.now(timezone.utc).isoformat(),'candidate_hash':candidate_hash,
              'owner_confirmation_sha256':sha(owner_path),'replay_sha256':sha(replay_path),
              'reviewed_history_records':imported,'generation_execution_enabled':False,
              'published_knowledge':0,'source_inputs_modified':False}
    manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,default=ROOT/'evaluation/concise_trial_20261022')
    parser.add_argument('--batch',type=Path,default=ROOT/'evaluation/concise_real_validation_20261022/batch')
    args = parser.parse_args()
    candidate = json.loads((ROOT/'data/shadow/unified_entry_20261020_r1/manifest.json').read_text(encoding='utf-8'))['candidate_hash']
    print(json.dumps(prepare(args.folder,args.batch,candidate),ensure_ascii=False))
