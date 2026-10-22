from types import SimpleNamespace

import numpy as np

from scripts import validate_platform_compatibility as bridge


def test_filtered_candidate_keeps_vectors_and_all_evidence_in_alignment(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge,'OUT',tmp_path/'isolated')
    monkeypatch.setattr(bridge,'inherited_approvals',lambda:{})
    raw = tmp_path/'原件.pdf'
    raw.write_text('source',encoding='utf-8')
    policy = tmp_path/'policy.json'
    policy.write_text('{}',encoding='utf-8')
    contract = SimpleNamespace(path=policy,decision=lambda path:(path == raw,'test_policy'))
    docs = {'keep':{'source_path':str(raw)},'drop':{'source_path':str(tmp_path/'导航.md')}}
    chunks = [{'chunk_id':str(i),'document_id':key,'raw_text':'设计策划 '+key} for i,key in enumerate(docs)]
    baseline = SimpleNamespace(docs=docs,chunks=chunks,vectors=np.array([[1,0],[0,1]]),atomic={'0':{'text':'原文'},'1':{'text':'导航'}},structured_rows=[{'document_id':key} for key in docs],candidate_hash='base')
    candidate,manifest = bridge.build_candidate(baseline,contract)
    assert set(candidate.docs) == {'keep'}
    assert [c['chunk_id'] for c in candidate.chunks] == ['0']
    assert set(candidate.atomic) == {'0'}
    assert candidate.structured_rows == [{'document_id':'keep'}]
    assert np.array_equal(candidate.vectors,baseline.vectors[:1])
    assert np.array_equal(np.load(bridge.OUT/'dense_embeddings.npy'),candidate.vectors)
    assert len(baseline.chunks) == 2 and manifest['chunks_after'] == 1
