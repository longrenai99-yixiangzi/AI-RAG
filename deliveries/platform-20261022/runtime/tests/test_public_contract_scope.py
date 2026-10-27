import pytest
from app.retrieval.contract_context import requested_subitems, project_conflict, context_bundle

@pytest.mark.parametrize('question,expected', [('第一项',[1]),('第（2）项',[2]),('第十五项',[15]),('第1项和第2项',[1,2])])
def test_public_synthetic_subitem_numbers(question,expected):
    assert requested_subitems(question)==expected

def test_public_empty_profile_never_invents_a_contract_modification():
    assert context_bundle('文件审查期限是多少？',[{'source_path':'synthetic.pdf','source_version':'test'}],source_scoped=True) is None

def test_public_project_scope_does_not_mix_different_projects():
    assert project_conflict('演示乙项目的要求是什么？',{'project_selector':'演示甲'})
    assert not project_conflict('本项目的要求是什么？',{'project_selector':'演示甲'})
