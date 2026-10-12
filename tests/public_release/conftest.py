"""Synthetic fixtures only: no customer document, question or source version."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest


@pytest.fixture
def sample_case():
    content=b'SYNTHETIC_REPORT_FOR_PUBLIC_TESTS_ONLY'
    version=hashlib.sha256(content).hexdigest()
    quotes=[('ITEM-ALPHA','合成比较对象：方案甲与方案乙，适用条件待补。','TECHNICAL_REVIEW'),
            ('ITEM-BETA','缺示例成果表','SOURCE_REPORTED_GAP'),
            ('ITEM-GAMMA','缺专业人员，未评估','ASSESSMENT_GAP')]
    items=[]
    for number,(identifier,quote,gap) in enumerate(quotes,2):
        anchor={'table':3,'row':number,'table_title':'合成汇总表','source_row_id':identifier,'source_row_text':quote,'quote':quote,'char_start':0,'char_end':len(quote),'dimension':'技术可行性'}
        items.append({'item_id':identifier,'professional':'演示专业','quote':quote,'kind':'未评范围待补评' if gap=='ASSESSMENT_GAP' else '技术问题或建议待复核',
                      'gap_type':gap,'gap_label':'合成工作记录','dimensions':['技术可行性'],'anchors':[anchor],'taskbook_routes':[],'suggested_action':'合成准备动作，未审批'})
    from app.assessment_handoff import INPUT_FIELDS
    return {'project_id':'demo-project','project':'演示厂房项目','source':{'source_path':'synthetic/report.docx','file_name':'合成报告.docx','source_version':version,'observation_date':'2030-02-03'},
            'scope_note':'合成测试，不代表实际项目事实。','source_rows':[],'items':items,'input_fields':[{'id':k,'label':v} for k,v in INPUT_FIELDS.items()],
            'gap_policy':{'source_version':version,'project_id':'demo-project','policy':'合成演示口径，不代表实际用户批准。','fact_Gold_approval':False,'formal_adoption_authorized':False},
            'comparison_topic_specs':[{'source_item_id':'ITEM-ALPHA','subject':'演示对象','baseline_reference':'方案甲','candidate_reference':'方案乙'}]}


@pytest.fixture
def adapter_client(tmp_path,monkeypatch,sample_case):
    from fastapi.testclient import TestClient
    from app.trial import v2,live_shadow_v25 as shadow
    from app.retrieval import retrieval_trace
    root=tmp_path/'runtime';(root/'frozen_sources').mkdir(parents=True);(root/'primary_sources').mkdir();(root/'knowledge-ui/dist/assets').mkdir(parents=True)
    (root/'knowledge-ui/dist/index.html').write_text('<p>Synthetic test fixture</p>',encoding='utf-8')
    original=root/'frozen_sources/report.docx';original.write_bytes(b'SYNTHETIC_REPORT_FOR_PUBLIC_TESTS_ONLY')
    source=sample_case['source'];version=source['source_version'];candidate_hash='a'*64
    def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    write(root/'assessment_handoff.json',sample_case)
    case_sha=hashlib.sha256((root/'assessment_handoff.json').read_bytes()).hexdigest()
    write(root.parent/'PACKAGE_MANIFEST_PRIVATE.json',{'candidate_hash':candidate_hash,'files':[{'path':'runtime/assessment_handoff.json','sha256':case_sha}]})
    write(root/'evaluation/knowledge_os_v2_6/remediation_candidate_v2_6_2.json',{'candidate_hash':candidate_hash,'sources':[],'dense_embeddings':{'shape':[1,1024]}})
    write(root/'frozen_sources/catalog.json',{'records':{'synthetic|'+version:{**source,'frozen_path':'frozen_sources/report.docx','sha256':version}}})
    write(root/'primary_sources/catalog.json',{'records':{}})
    write(root/'project_navigation.json',{'candidate_hash':candidate_hash,'periods':[],'projects':[{'id':'demo-project','name':sample_case['project'],'aliases':[sample_case['project']],
          'assessment_handoff_available':True,'scheme_comparison_available':True,'sources':[{**source,'source_id':'SYNTHETIC_SOURCE'}],'subjects':[{'id':'assessment','name':'合成评估','pages':[],'coverage':'合成测试'}]}]})
    atomic={'DEMO_EVIDENCE':{**source,'source_id':'SYNTHETIC_SOURCE','evidence_id':'DEMO_EVIDENCE','raw_text':'合成原文，不是业务资料。'}}
    engine=SimpleNamespace(candidate_hash=candidate_hash,atomic=atomic,docs={},chunks=[],vectors=np.zeros((1,1024)),retired_source_versions=[])
    dense=SimpleNamespace(ready=True,load=lambda:None)
    for module,names in [(v2,['KNOWLEDGE_STORE','TRIAL','GROWTH','FEEDBACK_CANDIDATES','FEEDBACK_CASES','FEEDBACK_RUNS','RAG_DEFECTS','SOURCE_CLOSURE_REGISTER','TRIAL_FEEDBACK_QUESTIONS','_candidate_primary_answer']),
                         (shadow,['RUNS','REMEDIATION_MANIFESTS','_restore_source_origin']),(retrieval_trace,['TRACE_DIR','TRACE_FILE'])]:
        for name in names:monkeypatch.setattr(module,name,getattr(module,name))
    monkeypatch.setattr(v2,'_primary_mode',lambda:v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2,'_candidate_primary_runtime',lambda:(engine,dense))
    monkeypatch.setenv('RAG_RELEASE_SERVICE_KIND','PREVIEW');monkeypatch.setenv('RAG_EXPECTED_CANDIDATE_HASH',candidate_hash)
    path=Path(__file__).resolve().parents[2]/'deployment/private_package/release_adapter.py'
    spec=importlib.util.spec_from_file_location('synthetic_release_adapter',path);module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,module);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',root)
    with TestClient(module.create_app(state_root=tmp_path/'state')) as client:
        yield client,sample_case,original
