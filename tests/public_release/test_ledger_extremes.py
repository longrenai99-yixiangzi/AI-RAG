import pytest

from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import _structured_extreme_claims, render
from tests.public_release.test_answer_coverage_context import bundle


def rows(values, headers=('专业类别', '创效策划点')):
    return [{'row_id':f'R{i}', 'row_number':i, 'source_path':'synthetic/ledger.xlsx',
             'table_id':'T1', 'source_version':'synthetic-v1', 'bundle_evidence_id':'E-DEMO',
             'professional':value[0], 'cells':[{'header':h,'value':v} for h,v in zip(headers,value)]}
            for i,value in enumerate(values,1)]


def test_numbered_category_is_not_a_numeric_measurement():
    data=bundle('专业类别最大值是多少？','合成表格')
    claims=_structured_extreme_claims(data,rows([('(4)演示类别','条目甲')]))
    assert not any(c['claim_type']=='DIRECT' for c in claims)


@pytest.mark.parametrize('operation, marker, expected', [('MAX','最多','演示甲、演示乙'),('MIN','最少','演示丙')])
def test_counts_use_detail_rows_and_keep_ties(operation, marker, expected):
    data=bundle(f'合成台账有多少个专业类别？策划点条数{marker}的是哪个专业、共几条？','合成表格')
    data['subquestions']=data['query_plan']['subquestions']
    data['structured_rows']=rows([('演示甲','点1'),('演示乙','点2'),('演示甲','点3'),('演示乙','点4'),('演示丙','点5')])
    data['structured_rows'].append({**data['structured_rows'][0],'is_summary':True,'row_id':'SUM','row_number':6})
    data['structured_evidence_complete']=True
    claims=_structured_extreme_claims(data,data['structured_rows'])
    assert '3个专业类别' in claims[0]['claim_text'] and '5条明细' in claims[0]['claim_text']
    assert expected in claims[1]['claim_text']
    assert claims[1]['subquestion_id']=='SQ2'


def test_budget_table_cannot_answer_item_counts():
    data=bundle('台账有多少个专业类别？策划点条数最多的是哪个专业？','合成表格')
    claims=_structured_extreme_claims(data,rows([('(4)演示类别','50')],('专业类别','概算限额')))
    assert all(c['claim_type']=='LIMITATION' for c in claims)


def test_serialled_ledger_excludes_secondary_headers_and_footer_examples():
    data=bundle('台账有多少个专业类别？策划点条数最多的是哪个专业？','合成表格')
    records=rows([('1','演示甲','点甲'),('2','演示甲','点乙'),('3','演示乙','点丙'),('序号','专业类别','创效策划点'),('','示例专业','示例条目')],('序号','专业类别','创效策划点'))
    for r in records:r['professional']=r['cells'][1]['value']
    claims=_structured_extreme_claims(data,records)
    assert '2个专业类别，共3条明细' in claims[0]['claim_text']
    assert '演示甲' in claims[1]['claim_text'] and '2条' in claims[1]['claim_text']


def test_numeric_extremes_accept_signed_unit_values_but_not_embedded_digits():
    data=bundle('哪个项目的金额最大？','合成表格')
    data['query_plan']['aggregation_plan']=['MAX']
    records=rows([('演示甲','-5万元'),('演示乙','1,200万元')],('项目名称','金额（万元）'))
    claims=_structured_extreme_claims(data,records)
    assert '1,200万元' in claims[0]['claim_text'] and '演示乙' in claims[0]['claim_text']
    records.extend(rows([('演示丙','方案9待定')],('项目名称','金额（万元）')))
    assert all(c['claim_type']=='LIMITATION' for c in _structured_extreme_claims(data,records))


def test_project_and_topic_commas_do_not_create_fake_subquestions():
    plan=plan_query('演示基地项目，设计完整度评估方面，建筑专业的完整度是多少？')
    assert len(plan.subquestions)<=1
    assert plan.query_type!='MULTI_FACT'
    assert len(plan_query('演示项目的完整度和深度分别是多少？').subquestions)==2


def test_computed_complete_ledger_covers_stale_lexical_coverage():
    data=bundle('台账有多少个专业类别？策划点条数最多的是哪个专业、共几条？','合成表格')
    data.update(subquestions=data['query_plan']['subquestions'],structured_rows=rows([('演示甲','点甲'),('演示甲','点乙'),('演示乙','点丙')]),structured_evidence_complete=True,bundle_status='VERIFIED_PARTIAL')
    data['coverage_map']=[{'subquestion_id':f'SQ{i}','subquestion':q,'coverage_status':'EVIDENCE_INSUFFICIENT'} for i,q in enumerate(data['subquestions'],1)]
    answer=render(data)
    assert answer['answer_status']=='ANSWERED'
    assert '证据不足' not in answer['answer_text']


def test_single_minimum_count_is_not_replaced_with_an_unrelated_raw_excerpt():
    data=bundle('演示项目策划点台账策划点条数最少的是哪个专业？','表名：合成表格\n行：合计 | 100',title='演示项目策划点台账.xlsx')
    data.update(subquestions=data['query_plan']['subquestions'],structured_rows=rows([('演示甲','点甲'),('演示甲','点乙'),('演示乙','点丙')]),structured_evidence_complete=True,bundle_status='VERIFIED_PARTIAL')
    answer=render(data)
    assert answer['answer_status']=='ANSWERED' and '演示乙' in answer['answer_text'] and '1条' in answer['answer_text']
    assert '行：合计' not in answer['answer_text']


def test_conflict_statement_requires_same_source_version_location_and_body():
    from app.ingestion.atomic_search import source_statement_matches
    statement={'source_version':'synthetic-v1','location':{'sheet_name':'演示专业','row_start':9},'required_text':['85']}
    record={'source_version':'synthetic-v1','location':{'sheet_name':'演示专业','row_start':9},'raw_text':'深度评价 | 85'}
    assert source_statement_matches(record,{},statement)
    assert not source_statement_matches({**record,'source_version':'different'}, {},statement)
    assert not source_statement_matches({**record,'location':{'sheet_name':'演示专业','row_start':10}}, {},statement)
    assert not source_statement_matches({**record,'raw_text':'深度待核'}, {},statement)
    assert not source_statement_matches({**record,'scope':{'project':'MISMATCH'}}, {},statement)
    assert source_statement_matches({'source_version':'demo','location':{'page':2}}, {'source_version':'demo'}, {'page':2})


def test_venue_seat_count_requires_numeric_seats_not_just_a_seating_topic():
    from app.ingestion.atomic_search import answer_support_gap
    q='演示场馆项目的建设规模与座位数是多少？';plan=plan_query(q).to_dict()
    assert not answer_support_gap(q,'总建筑面积2.5万㎡；包含3000座体育馆。',plan)
    assert answer_support_gap('座位数是多少？','体育馆座椅安装方案待核。',plan_query('座位数是多少？').to_dict())


def test_reviewed_cross_file_difference_is_preserved_and_cannot_use_just_one(monkeypatch):
    import app.verified_answer_engine_v2 as engine
    issue={'review_reason':'尚未裁定。','statements':[
        {'source_version':'synthetic-v1','location':{'table':1},'required_text':['80'],'location_label':'演示报告','text':'深度80%。'},
        {'source_version':'synthetic-v2','location':{'sheet_name':'演示专业','row_start':9},'required_text':['85'],'location_label':'演示附件','text':'深度85%。'}]}
    monkeypatch.setattr(engine,'source_statement_reviews',lambda _: [issue])
    data=bundle('演示专业深度是多少？','演示专业深度80%。')
    first=data['candidate_evidence'][0];first['location']={'table':1}
    first.update(source_content_role='HISTORICAL_PROJECT_REPORT',observation_date='2030-01-01')
    second={**first,'evidence_id':'E-SECOND','source_version':'synthetic-v2','location':{'sheet_name':'演示专业','row_start':9},'text':'演示专业深度85%。','raw_text':'演示专业深度85%。'}
    data['candidate_evidence']=[first,second]
    answer=render(data)
    assert answer['answer_status']=='CONFLICTING_ANSWER'
    assert '80%' in answer['answer_text'] and '85%' in answer['answer_text'] and len({c['evidence_id'] for c in answer['citations']})==2
    data['candidate_evidence']=[first]
    assert render(data)['answer_status']=='INSUFFICIENT_EVIDENCE'


def test_ranked_evidence_can_cover_one_part_of_a_multi_fact_question():
    from scripts.build_verified_evidence_bundle_v1 import _direct_candidate
    data=bundle('演示项目建筑专业完整度和深度分别是多少？','表头：专业 | 完整度（%）\n行：建筑 | 80%')
    c={**data['candidate_evidence'][0],'candidate_rank':13,'lineage_status':'LINEAGE_CONFIRMED','scope':{'project':'MATCH','specialty':'MATCH'},'negative_questions':[]}
    assert _direct_candidate(c,data['query_plan'])
    c.update(text='表头：专业 | 权重\n行：建筑 | 20%')
    assert not _direct_candidate(c,data['query_plan'])
