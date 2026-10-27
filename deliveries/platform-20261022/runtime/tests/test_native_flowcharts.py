import json
from pathlib import Path
import pytest
from app.retrieval.native_flowcharts import frame_bundle,frame_answer,append_flowcharts,is_flow_record














def test_dependency_mismatch_rejected_before_any_mutation(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'base_candidate_hash':'A','embedding_model_digest':'M','native_tables_manifest_sha256':'T'}))
    records=[];corpus=[]
    with pytest.raises(ValueError,match='dependency'):
        append_flowcharts(tmp_path,'OTHER','M','T',{},records,corpus,None)
    assert records==[] and corpus==[]






@pytest.mark.parametrize('problem',['tampered','nan','duplicate','unadmitted'])
def test_artifact_vector_and_admission_fail_before_mutating(tmp_path,monkeypatch,problem):
    import numpy as np
    import app.retrieval.native_flowcharts as module
    import hashlib
    row={'evidence_id':'flow-A','source_path':'manual.pdf','source_version':'V','text':'原文'}
    old={'evidence_id':'old','source_path':'manual.pdf','source_version':'V','document_id':'doc'}
    matrix=np.ones((1,1024),dtype=np.float32)/32
    if problem=='nan':matrix[0,0]=np.nan
    np.save(tmp_path/'vectors.npy',matrix)
    for name,value in [('records.json',[row]),('specs.json',[]),('charts.json',[]),('flow_clue_audit_12.json',[])]:
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    names=['records.json','specs.json','charts.json','flow_clue_audit_12.json','vectors.npy']
    m={'base_candidate_hash':'A','embedding_model_digest':'M','native_tables_manifest_sha256':'T',
       'artifact_sha256':{n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in names}}
    (tmp_path/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    monkeypatch.setattr(module,'extract_flow_records',lambda _: [row])
    if problem=='tampered':(tmp_path/'records.json').write_text('[]',encoding='utf-8')
    if problem=='duplicate':old['evidence_id']='flow-A'
    if problem=='unadmitted':old['source_version']='OTHER'
    records=[old];corpus=[['原片段']]
    with pytest.raises(ValueError):append_flowcharts(tmp_path,'A','M','T',{'doc':{}},records,corpus,np.zeros((1,1024)))
    assert records==[old] and corpus==[['原片段']]
