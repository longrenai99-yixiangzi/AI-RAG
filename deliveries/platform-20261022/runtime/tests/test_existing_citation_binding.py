import json

import httpx
import pytest

from app.trial.platform_existing import ExistingKnowledge


@pytest.mark.parametrize('wrong',['none','version','path'])
def test_legacy_path_citation_binds_only_to_exact_catalog_source_version(wrong):
    source_path='D:/synthetic/source.md';version='a'*64
    result={'answer_status':'SOURCES_ONLY','citations':[{'citation_id':'S1','source_id':source_path,
            'source_path':source_path,'source_version':version,'file_name':'source.md','excerpt':'synthetic','answer_usage':'PRIMARY'}]}
    calls=[]
    def transport(request):
        calls.append(request)
        if request.url.path=='/api/v2/assisted/query':
            assert json.loads(request.content)['mode']=='sources'
            return httpx.Response(200,text='data: '+json.dumps({'type':'result','result':result})+'\n\n')
        assert request.url.path=='/api/v2/knowledge/sources'
        row={'source_id':'SRC_catalog','source_path':source_path if wrong!='path' else 'D:/synthetic/other.md',
             'current_hash':version if wrong!='version' else 'b'*64}
        return httpx.Response(200,json={'items':[row],'total':1})
    existing=ExistingKnowledge(httpx.Client(base_url='http://127.0.0.1:8894',transport=httpx.MockTransport(transport)))
    if wrong=='none':
        card=existing.retrieve('synthetic','1'*32)['citations'][0]
        assert card['source_id']=='SRC_catalog' and card['lineage_source_id']==source_path
    else:
        with pytest.raises(ValueError,match='路径和版本'):existing.retrieve('synthetic','1'*32)
    assert len(calls)==2
