import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.bm25 import tokenize
from app.ingestion.pdf_text_recovery import clean_source_records
from app.retrieval.unified_candidate import UnifiedCandidate, file_sha
from app.trial.candidate_platform import CandidateKnowledge
from tests.test_focused_candidate import Reranker
from tests.test_pdf_text_recovery import native_pdf
from tests.test_unified_candidate import candidate


def prepared(tmp_path, native_pdf, watermark_only=False):
    _, pack, encoder, _ = candidate(tmp_path)
    records = [json.loads(line) for line in (pack/'evidence.jsonl').read_text(encoding='utf-8').splitlines()]
    docs = [json.loads(line) for line in (pack/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    source = {k:native_pdf[k] for k in ('source_path','source_version','file_name')}
    docs[0].update(source, file_type='.pdf')
    records[0].update(source, file_type='.pdf', text=next(line for line in native_pdf['excerpt'].splitlines() if 'Company' in line) if watermark_only else native_pdf['excerpt'],
                      location={'section':'Page 1'}, heading_path='Page 1')
    for name, values in [('documents',docs),('evidence',records)]:
        (pack/(name+'.jsonl')).write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values),encoding='utf-8')
    sparse = json.loads((pack/'bm25.json').read_text())
    sparse['corpus'][0] = tokenize(records[0]['text'])
    (pack/'bm25.json').write_text(json.dumps(sparse),encoding='utf-8')
    manifest = json.loads((pack/'manifest.json').read_text())
    manifest['embedding_model_digest'] = 'same-model'
    manifest['artifact_sha256'].update({name:file_sha(pack/name) for name in ['documents.jsonl','evidence.jsonl','bm25.json']})
    (pack/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    layer = tmp_path/'clean'; layer.mkdir()
    clean = clean_source_records([records[0]])[0]
    revision = {**{k:records[0][k] for k in ('evidence_id','source_path','source_version')}, 'text':clean['text'],
                'original_text_sha256':hashlib.sha256(records[0]['text'].encode()).hexdigest(), 'vector_row':None if watermark_only else 0}
    (layer/'records.json').write_text(json.dumps([revision]),encoding='utf-8')
    matrix = np.zeros((0 if watermark_only else 1,1024),dtype=np.float32)
    if not watermark_only: matrix[0,2] = 1
    np.save(layer/'vectors.npy',matrix)
    from app.ingestion import pdf_text_recovery
    spec = {'base_candidate_hash':manifest['candidate_hash'],'embedding_model_digest':'same-model',
            'profile_sha256':file_sha(Path(pdf_text_recovery.__file__).with_suffix('.json')),
            'artifact_sha256':{n:file_sha(layer/n) for n in ('records.json','vectors.npy')}}
    (layer/'manifest.json').write_text(json.dumps(spec),encoding='utf-8')
    return pack,encoder,layer,records


def test_cleanup_precedes_recall_preview_and_incremental_snapshot_for_any_question(tmp_path,native_pdf):
    pack,encoder,layer,old = prepared(tmp_path,native_pdf)
    c = UnifiedCandidate(pack,encoder,Reranker(),text_cleanup_folder=layer)
    assert 'Company' not in c.records[0]['text'] and '2024-12-30' in c.records[0]['text']
    assert tokenize('Company')[0] not in c.bm25.doc_freqs[0]
    assert c.vectors[0,2]==1 and np.load(pack/'dense_embeddings.npy')[0,0]==1
    sid=c.records[0]['source_id'];preview=c.source_evidence(sid)['items'][0]
    assert preview['raw_text']==c.records[0]['text'] and preview['text_cleanup']['removed_chars']>0
    snapshot=CandidateKnowledge(c).source_snapshot(sid)
    assert snapshot['records'][0]['text']==preview['excerpt'] and snapshot['vectors'][0][2]==1
    for question in ['原文是什么？','谁确认了该资料？','是否有业务日期？']:
        bundle=c.retrieve('《'+Path(native_pdf['source_path']).name+'》'+question)
        assert bundle['candidate_evidence'] and all('Company' not in r['text'] for r in bundle['candidate_evidence'])
    assert old[0]['text'] in (pack/'evidence.jsonl').read_text(encoding='utf-8').replace('\\n','\n')


def test_watermark_only_chunks_are_visible_as_excluded_and_never_recalled(tmp_path,native_pdf):
    pack,encoder,layer,_=prepared(tmp_path,native_pdf,True)
    c=UnifiedCandidate(pack,encoder,Reranker(),text_cleanup_folder=layer)
    assert c.records[0]['text']=='' and not c.vectors[0].any()
    sid=c.records[0]['source_id'];assert 'WATERMARK_ONLY' in c.source_evidence(sid)['items'][0]['answer_exclusion_reason']
    bundle=c.retrieve('《'+Path(native_pdf['source_path']).name+'》什么内容？')
    assert not encoder.calls and all(r['answer_usage']=='BACKGROUND' for r in bundle['candidate_evidence'])
    with pytest.raises(ValueError,match='没有通过'):CandidateKnowledge(c).source_snapshot(sid)


@pytest.mark.parametrize('damage',['model','vector','text','version'])
def test_changed_text_vector_or_model_alignment_stops_startup(tmp_path,native_pdf,damage):
    pack,encoder,layer,_=prepared(tmp_path,native_pdf)
    spec=json.loads((layer/'manifest.json').read_text())
    if damage=='model':spec['embedding_model_digest']='other-model'
    elif damage=='vector':(layer/'vectors.npy').write_bytes(b'changed')
    else:
        rows=json.loads((layer/'records.json').read_text())
        rows[0]['text' if damage=='text' else 'source_version']='invented' if damage=='text' else 'f'*64
        (layer/'records.json').write_text(json.dumps(rows))
        spec['artifact_sha256']['records.json']=file_sha(layer/'records.json')
    (layer/'manifest.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError):UnifiedCandidate(pack,encoder,Reranker(),text_cleanup_folder=layer)
