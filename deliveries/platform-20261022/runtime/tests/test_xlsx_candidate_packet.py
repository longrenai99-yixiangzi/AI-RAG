import pytest
from app.retrieval.xlsx_candidate_packet import explicit_table_scope,explicit_project_scope,hydrate_candidate_packet,ambiguous_native_field,literal_row_matches,missing_amount_basis,missing_parallel_rows,compact_candidate_packet


def row(identity,source='S',version='V',group=1):
    return {'id':identity,'kind':'CHILD','source_id':source,'source_version':version,'source_table_row_id':'row-1','field_group_index':group,'field_group_count':2,'parent_chunk_id':'parent','source_location':{'sheet_name':'业务明细表'},'source_cells':[{'column':'A','cell_reference':"'业务明细表'!A8"}]}


def test_same_row_expansion_cannot_cross_source_or_version():
    seed=row('a');sibling=row('b',group=2);other=row('c',source='OTHER',group=2);old=row('d',version='OLD',group=2)
    packet=hydrate_candidate_packet([seed],[seed,sibling,other,old],{'parent':{'source_id':'S','source_version':'V'}})
    assert packet['linked_row_ids']==['a','b'] and packet['missing_row_groups']==[]
    assert not packet['business_answer_authorized']


def test_invalid_parent_version_fails_closed():
    with pytest.raises(ValueError):hydrate_candidate_packet([row('a')],[row('a')],{'parent':{'source_id':'S','source_version':'OLD'}})


def test_explicit_sheet_and_range_use_native_coordinates():
    record=row('a');other=row('b');other['source_cells']=[{'cell_reference':"'业务明细表'!D9"}]
    allowed,_=explicit_table_scope('业务明细表A8:B8表区的原文',[record,other],['业务明细表'])
    assert allowed=={'a'}


def test_duplicate_native_field_requires_column_scope():
    record=dict(row('a'),table_id='T')
    tables={'T':{'requires_column_scope':True,'original_header':['单方造价','单方造价']}}
    assert ambiguous_native_field('单方造价是多少',[record],tables)
    assert ambiguous_native_field('Q列单方造价是多少',[record],tables) is None


def test_explicit_row_identity_beats_unrelated_similarity_without_using_free_text():
    record=row('a');record['source_cells']=[{'header':'项目名称','value':'其中内部分包部分合计'}]
    unrelated=row('b');unrelated['source_cells']=[{'header':'备注','value':'内部分包部分合计'}]
    other=row('c');other['source_cells']=[{'header':'项目名称','value':'充电桩'}]
    assert literal_row_matches('内部分包部分合计的中标价是多少',[record,unrelated,other])=={'a'}
    assert literal_row_matches('未指明分项的中标价是多少',[record,other])==set()


def test_parallel_named_rows_are_both_preserved():
    rows=[dict(row(str(i)),source_cells=[{'header':'项目名称','value':name}]) for i,name in enumerate(['土石方工程','桩基工程'])]
    assert literal_row_matches('土石方工程和桩基工程的预算价是多少',rows)=={'0','1'}


def test_budget_fields_cannot_support_settlement_amount():
    record=dict(row('a'),source_cells=[{'header':'合同金额 > 金额'},{'header':'预算成本价（万元）'}])
    assert missing_amount_basis('最终结算价是多少',[record])['missing_bases']==['结算']
    assert missing_amount_basis('合同金额和预算价分别是多少',[record]) is None
    assert missing_amount_basis('历史计费说明有哪些',[record]) is None


def test_held_siblings_are_not_hydrated_and_held_seed_fails_closed():
    seed=row('a');held=dict(row('b',group=2),index_status='QUARANTINED')
    parents={'parent':{'source_id':'S','source_version':'V'}}
    packet=hydrate_candidate_packet([seed],[seed,held],parents)
    assert packet['linked_row_ids']==['a'] and packet['missing_row_groups']==['row-1']
    with pytest.raises(ValueError,match='Ineligible'):hydrate_candidate_packet([held],[held],parents)


def test_field_text_is_not_a_sheet_selection_without_a_table_hint():
    a=row('a');a['source_location']={'sheet_name':'限额划分金额'}
    b=row('b');b['source_location']={'sheet_name':'相关附件'}
    allowed,_=explicit_table_scope('室外工程的限额划分金额及预留金比例是多少',[a,b],['限额划分金额','相关附件'])
    assert allowed=={'a','b'}
    allowed,_=explicit_table_scope('限额划分金额表中的原文',[a,b],['限额划分金额','相关附件'])
    assert allowed=={'a'}


def test_table_stem_and_reordered_budget_phrase_select_native_sheet():
    a=row('a');a['source_location']={'sheet_name':'快速预算与概算对比表'}
    b=row('b');b['source_location']={'sheet_name':'概算划分汇总表'}
    assert explicit_table_scope('快速预算对比概算时的收入',[a,b],['快速预算与概算对比表','概算划分汇总表'])[0]=={'a'}


def test_literal_project_scope_rejects_unknown_and_does_not_trust_paths():
    a=dict(row('a'),file_name='原表.xlsx',raw_text='表名：东城场馆项目概预算对比表')
    b=dict(row('b',source='OTHER'),file_name='西城医院项目.xlsx',raw_text='表名：其他业务',source_path='D:/东城场馆项目/其他.xlsx')
    assert explicit_project_scope('请问东城场馆项目，土方工程预算多少',[a,b])==({'a'},None)
    ids,boundary=explicit_project_scope('北城项目，土方工程预算多少',[a,b])
    assert not ids and boundary['status']=='PROJECT_SCOPE_UNRESOLVED'


def test_parallel_question_cannot_silently_drop_an_unknown_subject():
    a=dict(row('a'),source_cells=[{'header':'分项工程','value':'土方工程'}])
    assert missing_parallel_rows('土方工程和水工隧洞工程的限额是多少',[a])['missing_subjects']==['水工隧洞工程']
    b=dict(row('b'),source_cells=[{'header':'分项工程','value':'水工隧洞工程'}])
    assert missing_parallel_rows('土方工程和水工隧洞工程的限额是多少',[a,b]) is None


def test_approval_qualifier_is_not_supported_by_a_generic_investment_field():
    a=dict(row('a'),source_cells=[{'header':'总投资（万元）'}])
    assert missing_amount_basis('可研批复投资总金额是多少万元',[a])['status']=='REQUESTED_QUALIFIER_NOT_SUPPORTED'


def test_building_identifier_is_a_native_row_label():
    a=dict(row('a'),source_cells=[{'header':'楼栋','value':'1#五星'}])
    b=dict(row('b'),source_cells=[{'header':'楼栋','value':'2#四星'}])
    assert literal_row_matches('1#五星、2#四星的建筑面积',[a,b])=={'a','b'}


def compact_fixture(cells):
    record=dict(row('a'),file_name='原表.xlsx',source_path='D:/原表.xlsx',source_cells=cells)
    return record,{'primary_ids':['a'],'linked_row_ids':[],'context_ids':[]}


def test_compaction_keeps_zero_native_unit_and_full_qualifier():
    record,packet=compact_fixture([{'header':'中标价（万元）','value':0,'origin_coordinate':'D59'},{'header':'备注','value':'无内部分包','origin_coordinate':'P59'},{'header':'建筑面积（㎡）','value':999,'origin_coordinate':'K59'}])
    record['row_context']='图纸未出，预算价及成本为预估'
    compact=compact_candidate_packet('中标金额是多少，备注是什么',packet,{'a':record},{})
    assert [x['coordinate'] for x in compact['fields']]==['D59','P59']
    assert compact['fields'][0]['raw_value']==0 and '万元' in compact['fields'][0]['header']
    assert any(item['text']==record['row_context'] for item in compact['contexts']) and compact['boundary'] is None


def test_compaction_cannot_choose_between_tax_excluded_and_total_cost():
    record,packet=compact_fixture([{'header':'成本不含税（万元）','value':100,'origin_coordinate':'N7'},{'header':'预算成本测算金额','value':145,'origin_coordinate':'Q7'}])
    compact=compact_candidate_packet('成本是多少',packet,{'a':record},{})
    assert compact['boundary']['status']=='AMBIGUOUS_REQUESTED_FIELD'
    compact=compact_candidate_packet('预算成本是多少',packet,{'a':record},{})
    assert compact['boundary'] is None and len(compact['fields'])==1


def test_compaction_keeps_the_explicit_discount_stage_and_detects_missing_fields():
    record,packet=compact_fixture([{'header':'施工图预算价（下浮前）','value':900,'origin_coordinate':'F4'},{'header':'施工图预算价（下浮后）','value':800,'origin_coordinate':'G4'}])
    compact=compact_candidate_packet('下浮后的施工图预算是多少',packet,{'a':record},{})
    assert [x['coordinate'] for x in compact['fields']]==['G4']
    compact=compact_candidate_packet('施工图预算下浮前后分别是多少',packet,{'a':record},{})
    assert len(compact['fields'])==2 and compact['boundary'] is None
    assert compact_candidate_packet('预算成本与备注是什么',packet,{'a':record},{})['boundary']['status']=='FIELD_SELECTION_INCOMPLETE'


def test_context_only_question_retains_verbatim_note_without_authorizing_answers():
    record,packet=compact_fixture([]);packet['context_ids']=['p']
    parent={'source_id':'S','source_version':'V','file_name':'原表.xlsx','source_path':'D:/原表.xlsx','sheet_name':'业务明细表','cells':[{'origin_coordinate':'A58','value_status':'NATIVE_VALUE','value':'历史说明，超过200亿元时按原表说明处理。'}]}
    compact=compact_candidate_packet('历史计费说明是什么',packet,{'a':record},{'p':parent})
    assert compact['status']=='REVIEW_ONLY' and not compact['business_answer_authorized']
    assert compact['contexts'][0]['coordinate']=='A58' and compact['contexts'][0]['text']==parent['cells'][0]['value']


def test_derived_difference_is_not_the_requested_operand():
    record,packet=compact_fixture([{'header':'中标价（万元）','value':10,'origin_coordinate':'D4'},{'header':'差额（中标价-预算成本价）','value':3,'origin_coordinate':'I4'}])
    compact=compact_candidate_packet('中标价是多少',packet,{'a':record},{})
    assert compact['boundary'] is None and [x['coordinate'] for x in compact['fields']]==['D4']


def test_native_row_notes_keep_coordinates_but_not_parser_metadata_as_prose():
    record,packet=compact_fixture([{'header':'预算成本价','value':10,'origin_coordinate':'H4'}])
    record['row_context']=[{'sheet_name':'业务明细表','origin_coordinate':'Q3','value_status':'NATIVE_VALUE','value':'暂估，图纸未出','formula':'暂估，图纸未出'}]
    compact=compact_candidate_packet('预算成本价是多少',packet,{'a':record},{})
    assert compact['contexts'][0]['coordinate']=='Q3' and compact['contexts'][0]['text']=='暂估，图纸未出'


def test_same_label_different_values_cannot_be_silently_merged():
    record,packet=compact_fixture([{'header':'预算成本价','value':10,'origin_coordinate':'H4'},{'header':'预算成本价','value':12,'origin_coordinate':'H8'}])
    assert compact_candidate_packet('预算成本价是多少',packet,{'a':record},{})['boundary']['status']=='CONFLICTING_NATIVE_VALUES'


def test_budget_price_and_cost_are_two_requested_fields():
    record,packet=compact_fixture([{'header':'施工图预算价（下浮后）','value':800,'origin_coordinate':'G4'},{'header':'预算成本价（万元）','value':600,'origin_coordinate':'H4'}])
    compact=compact_candidate_packet('下浮后的预算价和预算成本分别是多少',packet,{'a':record},{})
    assert compact['boundary'] is None and {x['coordinate'] for x in compact['fields']}=={'G4','H4'}


def test_explicit_original_and_new_scheme_incomes_are_not_ambiguous():
    record,packet=compact_fixture([{'header':'原方案测算收入（万元）A','value':80,'origin_coordinate':'N75'},{'header':'新方案测算收入（万元）D','value':90,'origin_coordinate':'Q75'}])
    compact=compact_candidate_packet('原方案测算收入和新方案测算收入分别是多少',packet,{'a':record},{})
    assert compact['boundary'] is None and len(compact['fields'])==2
