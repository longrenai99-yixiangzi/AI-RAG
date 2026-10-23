import json
import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.retrieval.named_source_scope import path_key
from app.retrieval.section_scope import SectionTitleIndex
from app.trial import assisted_chat as flow
from app.trial.knowledge_store import TrialKnowledgeStore
from app.trial.platform_existing import ExistingKnowledge
from tests.test_unified_candidate import candidate
from tests.test_assisted_chat import fixture
from tests.test_focused_candidate import Reranker,Titles
from app.retrieval.focused_candidate import FocusedCandidate


def test_source_pool_filters_before_sparse_dense_fusion_and_section_addition(tmp_path):
    c,_,encoder,_=candidate(tmp_path)
    wanted=c.records[0];other=c.records[1]
    c.focused.title_index=SimpleNamespace(search=lambda q,**kwargs:[{**other,'role':'DIRECT','score':99}])
    result=c.retrieve('查找标记是什么？',source_versions={wanted['source_id']:wanted['source_version']})
    assert encoder.calls and result['retrieval_audit']['eligible_rows']==1
    assert {r['source_id'] for r in result['candidate_evidence']}=={wanted['source_id']}
    assert result['retrieval_source_filter']['status']=='EXACT_SOURCE_VERSIONS'
    assert result['bundle_status']=='PRIMARY_SECTION_CANDIDATE'


@pytest.mark.parametrize('change',['unknown','old_version','changed_bytes','explicit_other_project','explicit_other_file'])
def test_bad_scope_never_falls_back_to_other_source_or_encodes_query(tmp_path,change):
    c,_,encoder,_=candidate(tmp_path);row=c.records[0];other=c.records[1]
    scope={row['source_id']:row['source_version']};question='查找标记是什么？'
    if change=='unknown':scope={'SRC_unknown':row['source_version']}
    if change=='old_version':scope[row['source_id']]='a'*64
    if change=='changed_bytes':Path(row['source_path']).write_bytes(b'changed')
    if change=='explicit_other_project':question='乙方工厂项目查找标记是什么？'
    if change=='explicit_other_file':question='《'+other['file_name']+'》查找标记是什么？'
    result=c.retrieve(question,source_versions=scope)
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING' and not result['candidate_evidence'] and not encoder.calls


def test_title_candidates_are_filtered_before_top_eight_limit():
    rows=[{'section_id':str(i),'source_path':'D:/synthetic/'+str(i)+'.md','source_version':'a'*64,
           'heading_path':'方案比选','text':'方案比选','location':{}} for i in range(12)]
    titles=SectionTitleIndex(rows);last=rows[-1]
    titles.bm25.search=lambda q,limit:[(str(i),12-i) for i in range(12)]
    result=titles.search('方案比选',allowed_versions={(path_key(last['source_path']),last['source_version'])})
    assert len(result)==1 and result[0]['section_id']=='11'


@pytest.mark.parametrize('scope',[{}, {'D:/private/source.md':'a'*64},{'SRC_demo':'short'},{'SRC_demo':'A'*64},
                                  {f'SRC_{i}':'a'*64 for i in range(21)}])
def test_scope_wire_validation_rejects_paths_unknown_hash_shapes_and_oversized_lists(scope):
    with pytest.raises(ValidationError):flow.AssistedQuery(question='查找方法',source_versions=scope)


def test_adapter_forwards_only_filter_ids_and_versions_without_generation():
    versions={'SRC_demo':'a'*64};seen=[]
    def transport(request):
        body=json.loads(request.content);seen.append(body)
        assert body['source_versions']==versions and body['mode']=='sources'
        return httpx.Response(200,text='data: '+json.dumps({'type':'result','result':{'answer_status':'SOURCES_ONLY','citations':[]}})+'\n\n')
    existing=ExistingKnowledge(httpx.Client(base_url='http://127.0.0.1:8894',transport=httpx.MockTransport(transport)))
    existing.retrieve('方法是什么？','1'*32,source_versions=versions)
    assert len(seen)==1


def test_api_cache_identity_includes_source_version_filter(tmp_path):
    bundle,_,_=fixture(tmp_path);app=FastAPI();app.include_router(flow.router)
    app.state.assisted_store=TrialKnowledgeStore(tmp_path/'state.json');calls=[]
    def retrieve(q,*,source_versions=None):calls.append(source_versions);return bundle
    app.state.assisted_retrieve=retrieve
    versions={'SRC_demo':'a'*64}
    body={'question':'查找方法','mode':'sources','source_versions':versions,'request_id':uuid.uuid4().hex}
    with TestClient(app,base_url='http://127.0.0.1:8891') as client:
        headers={'Origin':'http://127.0.0.1:8891'}
        assert client.post('/api/v2/assisted/query',headers=headers,json=body).status_code==200
        assert client.post('/api/v2/assisted/query',headers=headers,json=body).status_code==200
        assert len(calls)==1 and calls[0]==versions
        assert client.post('/api/v2/assisted/query',headers=headers,json={**body,'source_versions':{'SRC_other':'b'*64}}).status_code==409
        assert client.post('/api/v2/assisted/query',headers=headers,json={**body,'source_versions':None}).status_code==409


@pytest.mark.parametrize('missing_anchor',[False,True])
def test_criteria_focus_uses_existing_sibling_outline_and_never_reintroduces_excluded_body(tmp_path,missing_anchor):
    path=tmp_path/'source.md'
    texts=['[/body/p[@paraId=01]] 3、设计方案比选',
           '[/body/p[@paraId=02]] 3.1方案比选流程\n[/body/p[@paraId=03]] 各方案从效益、质量、进度等方面开展比选。',
           '[/body/p[@paraId=04]] 3.2方案比选类型\n[/body/p[@paraId=05]] 比选类型包括整体方案和材料设备。']
    path.write_text('\n'.join(texts),encoding='utf-8');version=hashlib.sha256(path.read_bytes()).hexdigest()
    base={'source_path':str(path),'source_version':version,'source_id':'SRC_demo','document_id':'D','evidence_id':'raw','text':'\n'.join(texts),'heading_path':'总标题','role':'DIRECT'}
    ss=[{**base,'section_id':str(i),'title':'主题','heading_path':'三 实施要点 > 3、设计方案比选'+('' if i==0 else ' > '+['','3.1方案比选流程','3.2方案比选类型'][i]),
         'text':text,'paragraph_anchors':anchors,'location':{},'heading_origin':'FROZEN_SYNTHETIC'} for i,(text,anchors) in enumerate(zip(texts,[['01'],['02','03'],['04','05']]))]
    eligible={**base,'text':base['text'].replace('[/body/p[@paraId=03]]','') if missing_anchor else base['text']}
    provider=FocusedCandidate(ss,Titles(),Reranker(),records=[eligible])
    seed={**base,'evidence_id':'hit','text':texts[2],'heading_path':ss[2]['heading_path']}
    result=provider.rank('方案比选需要比较哪些方面，最优方案应兼顾什么？',[seed])
    primary=[r for r in result['candidate_evidence'] if r.get('answer_usage')=='PRIMARY']
    if missing_anchor:
        assert not primary and result['bundle_status']=='SOURCE_SCOPE_MISSING'
    else:
        assert len(primary)==1 and '3.1方案比选流程' in primary[0]['heading_path']
        assert '效益、质量、进度' in primary[0]['text'] and '比选类型' not in primary[0]['text']
        assert result['chapter_coverage']['status']=='PARENT_FOCUS_EVIDENCE_COLLECTED'
    types=provider.rank('方案比选包括哪些类型？',[seed])
    assert types['chapter_coverage']['status']=='NOT_PARENT_OVERVIEW'
