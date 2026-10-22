from copy import deepcopy

from app.retrieval.scalar_bridge import matching_links, scalar_bundle
from app.trial.assisted_chat import AssistedQuery, run_flow
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
from tests.test_existing_text_answers import bundle as source_fixture


def run(question, evidence):
    return list(run_flow(AssistedQuery(question=question, mode='sources'), lambda _: evidence,
                        ShadowAnswerGenerator(UnavailableLLMProvider('No external provider')),
                        lambda *args: None))[-2]['result']


def test_existing_scalar_renderer_is_used_in_sources_mode_with_real_citation(tmp_path):
    question = '甲学校项目合同金额是多少万元？'
    data, links, _, _ = source_fixture(tmp_path, question, '合同总价123456789.12元（暂定）')
    assert matching_links(question, links) == links
    evidence = scalar_bundle(question, data['candidate_evidence'], links)
    result = run(question, evidence)
    assert result['answer_status'] == 'SOURCE_EXTRACT_DRAFT'
    assert '12345.678912万元' in result['answer'] and '暂定' in result['answer']
    assert result['generation_mode'] == 'VERIFIED_SCALAR_NO_MODEL'
    assert result['claims'][0]['evidence_ids'] == [result['citations'][0]['citation_id']]
    assert result['citations'][0]['answer_usage'] == 'PRIMARY'


def test_wrong_phase_missing_metric_stale_and_extra_year_never_become_primary(tmp_path):
    question = '甲学校项目二期合同金额多少万元？'
    data, links, source, _ = source_fixture(tmp_path, question, '工程造价731万元')
    for q in [question, '甲学校项目合同金额多少万元？', '甲学校项目2030年工程造价多少万元？']:
        result = run(q, scalar_bundle(q, data['candidate_evidence'], links))
        assert result['answer_status'] == 'EVIDENCE_INSUFFICIENT'
        assert not result['claims'] and all(c['answer_usage'] == 'BACKGROUND' for c in result['citations'])
    source.write_text('changed', encoding='utf-8')
    result = run('甲学校项目工程造价多少万元？', scalar_bundle('甲学校项目工程造价多少万元？', data['candidate_evidence'], links))
    assert result['answer_status'] == 'EVIDENCE_INSUFFICIENT'


def test_non_numeric_management_questions_do_not_enter_scalar_route(tmp_path):
    _, links, _, _ = source_fixture(tmp_path, '甲学校项目合同金额？', '合同总价731万元')
    assert not matching_links('甲学校项目设计评估的作用是什么？', links)
    assert not matching_links('甲学校项目如何进行合同金额控制？', links)
    assert not matching_links('乙医院项目合同金额多少万元？', links)
