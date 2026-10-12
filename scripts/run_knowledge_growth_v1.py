from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from pathlib import Path

from app.knowledge_growth_v1 import candidate_for_trace, merge_candidate, trace_from_runtime

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Create proposed improvements in a separate directory; never publish knowledge.')
    parser.add_argument('--input', type=Path, default=ROOT/'evaluation/verified_answer_engine_v2_final/fresh_run_trace.jsonl')
    parser.add_argument('--runtime-state', type=Path)
    parser.add_argument('--trace-dir', type=Path)
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--candidate-hash', default='')
    parser.add_argument('--output', type=Path, default=ROOT/'data/shadow/knowledge_growth_v1')
    parser.add_argument('--rebuild', action='store_true')
    args = parser.parse_args(argv)
    if args.candidate_hash and not re.fullmatch(r'[a-fA-F0-9]{64}', args.candidate_hash):
        parser.error('--candidate-hash must be the complete 64-character fingerprint.')
    if args.rebuild:
        parser.error('Rebuild can discard review context. Use a new output directory instead.')
    traces=[]; skipped=[]
    if args.runtime_state:
        if not args.trace_dir:
            parser.error('--runtime-state requires --trace-dir')
        state=json.loads(args.runtime_state.read_text(encoding='utf-8-sig'))
        manifest=json.loads(args.source_manifest.read_text(encoding='utf-8-sig')) if args.source_manifest else {}
        if manifest and args.candidate_hash and args.candidate_hash!=manifest.get('candidate_hash'):
            parser.error('Candidate fingerprint does not match the source manifest.')
        for audit in state.get('query_runs', {}).values():
            path=(args.trace_dir/(audit['query_run_id']+'.json')).resolve()
            if not path.is_relative_to(args.trace_dir.resolve()):
                raise ValueError('TRACE_PATH_OUTSIDE_DIRECTORY')
            if not path.is_file():
                skipped.append({'question_id':audit['query_run_id'], 'reason':'TRACE_UNAVAILABLE'});continue
            raw=json.loads(path.read_text(encoding='utf-8'))
            if args.candidate_hash and raw.get('candidate_hash')!=args.candidate_hash:
                skipped.append({'question_id':audit['query_run_id'], 'reason':'HISTORICAL_CANDIDATE'});continue
            traces.append(trace_from_runtime(audit, raw, manifest))
    else:
        if not args.input.is_file():
            parser.error('Input trace file does not exist.')
        traces=read_jsonl(args.input)
    registry=args.output/'growth_candidates.jsonl'
    existing={row['candidate_fingerprint']:row for row in read_jsonl(registry)}
    events=[]; results=[]
    for trace in traces:
        candidate=candidate_for_trace(trace)
        if candidate is None:
            results.append({'question_id':trace['question_id'], 'status':'NO_PROPOSAL', 'traffic_kind':trace.get('traffic_kind','UNCLASSIFIED')});continue
        key=candidate['candidate_fingerprint'];previous=existing.get(key)
        updated=merge_candidate(previous,candidate) if previous else candidate
        changed=updated!=previous
        existing[key]=updated
        results.append({'question_id':trace['question_id'],'status':'PROPOSED' if previous is None else 'MERGED' if changed else 'ALREADY_RECORDED','candidate_id':updated['candidate_id']})
        if changed:
            events.append({'event_type':'CANDIDATE_PROPOSED' if previous is None else 'CANDIDATE_QUERY_LINKED','candidate_id':updated['candidate_id'],'source_query_id':trace['question_id'],'candidate_fingerprint':key,'automatic_publish':0})
    write_jsonl(registry,list(existing.values()))
    with (args.output/'growth_events.jsonl').open('a',encoding='utf-8') as stream:
        for event in events:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
    report={'candidates':len(existing),'new_events':len(events),'records':results,'skipped':skipped,
            'review_records_preserved':True,'automatic_knowledge_publish':0,'runtime_input':False}
    (args.output/'generation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('candidates','new_events','review_records_preserved','automatic_knowledge_publish')}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
