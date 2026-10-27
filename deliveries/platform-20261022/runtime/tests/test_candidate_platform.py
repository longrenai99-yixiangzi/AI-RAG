import hashlib
import uuid
from fastapi.testclient import TestClient
from app.trial.candidate_platform import create_candidate_app,CandidateKnowledge
from tests.test_unified_candidate import candidate


def test_candidate_platform_uses_existing_library_and_blocks_all_model_and_source_writes(tmp_path):
    c,_,encoder,_=candidate(tmp_path);app=create_candidate_app(tmp_path/'trial/state.json',c)
    with TestClient(app) as client:
        state=client.get('/api/platform/state').json()
        assert state['runtime']['candidate_hash']==c.candidate_hash and not state['capabilities']['generation_execution_enabled']
        assert state['capabilities']['read_only_source_trial'] and not state['capabilities']['daily_model_configured']
        items=client.get('/api/platform/library').json()['items'];source=items[0]
        content=client.get('/api/platform/library/'+source['source_id']+'/original')
        assert content.status_code==200 and hashlib.sha256(content.content).hexdigest()==source['current_hash']
        headers={'X-Platform-Request':'1'}
        q=client.post('/api/platform/query',headers=headers,json={'question':'甲校医院项目哪个岗位负责，配置多少人？','request_id':uuid.uuid4().hex})
        assert q.status_code==200 and q.json()['status']=='COMPLETED'
        for path in ['/api/platform/backups','/api/platform/imports/upload','/api/platform/candidates','/api/platform/generation/demo/run','/api/platform/daily-policy/actions']:
            assert client.post(path,headers=headers,json={}).status_code==403
        assert client.post('/api/platform/query',headers={**headers,'Origin':'https://foreign.example'},json={}).status_code==403
        assert client.get('/api/platform/state',headers={'host':'foreign.example'}).status_code==403
        assert client.get('/api/platform/state').json()['knowledge']==[]


def test_internal_reviewed_knowledge_features_reuse_local_models_without_enabling_import(tmp_path):
    c,_,encoder,_=candidate(tmp_path);c.manifest['embedding_model_digest']='fixed-local-model'
    encoder.embed_documents=lambda texts:[encoder.embed_query(t) for t in texts]
    bridge=CandidateKnowledge(c)
    vectors=bridge.features(['已核对的校正稿'])
    assert vectors['model_digest']=='fixed-local-model' and len(vectors['vectors'][0])==1024
    scores=bridge.features(['已核对的校正稿'],'核对什么？')
    assert len(scores['scores'])==1
    import pytest
    with pytest.raises(ValueError,match='来源不存在'):bridge.source_snapshot('source')


def test_snapshot_keeps_vector_rows_and_refuses_changed_or_reference_only_sources(tmp_path):
    import numpy as np
    import pytest
    c,_,_,docs=candidate(tmp_path);c.manifest['embedding_model_digest']='fixed-local-model';bridge=CandidateKnowledge(c)
    sid=c.sources(query='甲校医院')['items'][0]['source_id'];index=c.by_source[sid][0]
    snapshot=bridge.source_snapshot(sid)
    assert snapshot['records'][0]['evidence_id']==c.records[index]['evidence_id']
    assert np.array_equal(snapshot['vectors'][0],c.vectors[index])
    c.quality_exclusions[c.records[index]['evidence_id']]='held'
    with pytest.raises(ValueError,match='没有通过'):bridge.source_snapshot(sid)
    c.quality_exclusions.clear();c.reference_only.add(c.record_paths[index])
    with pytest.raises(ValueError,match='登记卡'):bridge.source_snapshot(sid)
    c.reference_only.clear()
    from pathlib import Path
    Path(docs[0]['source_path']).write_text('changed')
    with pytest.raises(ValueError,match='版本已变化'):bridge.source_snapshot(sid)


def test_explicit_admin_mode_does_not_enable_unlimited_model_execution(tmp_path):
    c,_,_,_=candidate(tmp_path);app=create_candidate_app(tmp_path/'admin/state.json',c,administrator_enabled=True)
    with TestClient(app) as client:
        caps=client.get('/api/platform/state').json()['capabilities']
        assert caps['administrator_operations_enabled'] and not caps['generation_execution_enabled']
        response=client.post('/api/platform/sources',headers={'X-Platform-Request':'1'},json={'name':'合成来源','version_label':'v1'})
        assert response.status_code==200
        response=client.post('/api/platform/generation/missing/run',headers={'X-Platform-Request':'1'},json={'approved':True,'packet_sha256':'0'*64})
        assert response.status_code==403
