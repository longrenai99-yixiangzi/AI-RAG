import pytest

from app.ingestion.atomic_search import answer_support_gap
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import _answer, _claim, render


def bundle(question, text, *, title='演示资料.md', verified=True, scope=None):
    evidence = {
        'evidence_id': 'E-DEMO', 'source_id': 'S-DEMO', 'source_version': 'synthetic-v1',
        'document_id': 'D-DEMO', 'source_path': 'synthetic/demo.md', 'file_name': title,
        'heading_path': '', 'role': 'DIRECT', 'text': text, 'raw_text': text,
        'location': {'line_start': 1}, 'scope': scope or {},
    }
    plan = plan_query(question).to_dict()
    return {
        'query_id': 'Q-DEMO', 'question': question, 'query_plan': plan,
        'bundle_status': 'VERIFIED' if verified else 'VERIFIED_PARTIAL',
        'candidate_evidence': [evidence], 'verified_evidence': [evidence] if verified else [],
        'supporting_evidence': [], 'conflicting_evidence': [], 'excluded_evidence': [],
        'coverage_map': [{'subquestion_id': 'SQ1', 'coverage_status': 'COVERED'}],
        'conflict_map': {}, 'structured_fact_map': {},
    }


def test_cited_source_title_can_supply_annual_context_but_not_the_count():
    question = '2030年度多少个项目成功打造为设计管理示范项目？'
    text = '最终4个项目成功打造为设计管理示范项目。'
    data = bundle(question, text, title='2030年度设计管理总结.md')
    answer = _answer(data, 'ANSWERED', [_claim('C1', 'DIRECT', 'SQ1', text, ['E-DEMO'])], [])
    assert answer['answer_status'] == 'ANSWERED'
    assert '4个项目' in answer['answer_text']
    assert answer['citations'][0]['evidence_id'] == 'E-DEMO'


@pytest.mark.parametrize(('question', 'text', 'context'), [
    ('演示设施能效怎么算？', '演示设施能效是一个示例指标。', '演示设施能效=示例甲+示例乙'),
    ('演示成果有多少项？', '演示成果尚待统计。', '演示成果共5项'),
    ('演示成果的数量和月份分别是多少？', '演示成果有5项。', '演示成果6月形成'),
    ('演示任务完成时间是什么？', '演示任务完成时间待定。', '2030年5月6日完成演示任务'),
    ('什么是演示设施？', '演示设施认证依据为演示标准。', '演示设施是指示例对象。'),
    ('演示流程是哪三步？', '演示流程包括准备、检查。', '演示流程包括准备、检查、归档。'),
])
def test_source_context_cannot_supply_missing_answer_values_or_forms(question, text, context):
    assert answer_support_gap(question, text, plan_query(question).to_dict(), subject_context=context)


@pytest.mark.parametrize('kind', ['uncited', 'unverified', 'scope_mismatch'])
def test_untrusted_or_uncited_title_cannot_complete_an_answer(kind):
    question = '演示厂房的墙面做法是什么？'
    text = '墙面做法为示例涂层。'
    data = bundle(question, text, title='演示厂房墙面做法.md', verified=kind != 'unverified',
                  scope={'project': 'MISMATCH'} if kind == 'scope_mismatch' else None)
    evidence_ids = ['E-OTHER'] if kind == 'uncited' else ['E-DEMO']
    answer = _answer(data, 'ANSWERED', [_claim('C1', 'DIRECT', 'SQ1', text, evidence_ids)], [])
    assert answer['answer_status'] != 'ANSWERED'


def test_exact_list_count_rejects_more_items_as_well_as_fewer():
    question = '演示部门的职责有哪三项？'
    for text, complete in [
        ('职责包括：接收输入；核对成果；记录反馈。', True),
        ('职责包括：接收输入；核对成果。', False),
        ('职责包括：接收输入；核对成果；记录反馈；归档原件。', False),
    ]:
        data = bundle(question, text, title='演示部门职责.md')
        answer = _answer(data, 'ANSWERED', [_claim('C1', 'DIRECT', 'SQ1', text, ['E-DEMO'])], [])
        assert (answer['answer_status'] == 'ANSWERED') is complete
        if not complete:
            assert answer['uncovered_subquestions'] == ['SQ1']


def test_definition_does_not_replace_formula_even_with_a_matching_title():
    question = '演示设施整体能效怎么算？'
    data = bundle(question, '演示设施是指用于合成测试的设施。', title='演示设施整体能效计算.md')
    answer = render(data)
    assert answer['answer_status'] != 'ANSWERED'


@pytest.mark.parametrize('question', ['设计任务书的数量是多少？', '设计任务书有多少份？', '设计任务书共多少份？'])
def test_unrelated_answer_count_is_not_rescued_by_the_source_title(question):
    text = '设计计划数量是7份。'
    data = bundle(question, text, title='设计任务书与设计计划数量.md')
    answer = _answer(data, 'ANSWERED', [_claim('C1', 'DIRECT', 'SQ1', text, ['E-DEMO'])], [])
    assert answer['answer_status'] != 'ANSWERED'


def test_count_value_and_unit_must_belong_to_the_requested_object():
    question = '设计任务书有多少份？'
    assert not answer_support_gap(question, '设计任务书有7份。')
    assert answer_support_gap(question, '设计任务书评审7次。')
    assert answer_support_gap(question, '设计任务书尚未编制；设计计划有7份。')
    assert answer_support_gap('演示成果有多少个？', '演示成果评审7次，完成率20个百分点。')
