import copy
from pathlib import Path

import pytest

from app.retrieval.complete_lists import build_catalog,list_bundle,render_list,enforce_complete_list
from app.trial.assisted_chat import assemble
from app.retrieval.unified_candidate import file_sha
from test_daily_answers import daily,approve

QUESTION='依据《工作手册》附件2“验收文件示范文本”，应包含哪些章节和内容？'


def evidence(tmp_path):
    parts=[(10,'附件2：验收文件示范文本'),(11,'第一章 基本信息\n1.1 项目说明\n示例数量99'),
           (12,'1.2 相关方\n第二章 验收记录\n2.1 记录范围'),(13,'第三章 交付清单\n专业\n责任人'),
           (14,'- 14 -\n附件3：移交文件参考文本\n第一章 不得混入')]
    path=tmp_path/'工作手册.pdf';path.write_text('\n'.join(s for _,s in parts),encoding='utf-8');sha=file_sha(path)
    return [{'source_path':str(path),'source_version':sha,'file_name':path.name,'source_id':'SRC_outline','document_id':'doc',
             'evidence_id':'row'+str(i),'text':text,'heading_path':'Page '+str(page),'location':{'section':'Page '+str(page)}} for i,(page,text) in enumerate(parts)]


def get_result(rows,question=QUESTION,eligible=None):
    bundle=list_bundle(question,build_catalog(rows),eligible if eligible is not None else {r['evidence_id'] for r in rows})
    _,cards=assemble(bundle,question,include_background=True)
    return bundle,cards


def test_outline_is_bounded_and_contents_question_stays_partial(tmp_path):
    rows=evidence(tmp_path);bundle,cards=get_result(rows)
    result=render_list(bundle['complete_list_audit'],cards,QUESTION)
    assert result['answer_completeness']=='PARTIAL' and result['coverage_gaps']
    assert len(bundle['complete_list_audit']['chapters'])==3
    assert bundle['complete_list_audit']['end_page']==13
    assert all(s in result['answer'] for s in ['基本信息','1.2 相关方','交付清单'])
    assert '不得混入' not in result['answer'] and '示例数量99' not in result['answer']
    assert result['generation_mode']=='VERIFIED_COMPLETE_LIST_NO_MODEL'


@pytest.mark.parametrize('change',['boundary','page_gap','chapter_gap','duplicate_chapter','eligible','version','title'])
def test_incomplete_conflicting_or_changed_outline_is_not_a_verified_answer(tmp_path,change):
    rows=evidence(tmp_path);question=QUESTION;eligible=None
    if change=='boundary':rows.pop()
    if change=='page_gap':rows[2]['heading_path']='Page 99'
    if change=='chapter_gap':rows[2]['text']=rows[2]['text'].replace('第二章','第五章')
    if change=='duplicate_chapter':rows[2]['text']=rows[2]['text'].replace('第二章','第一章')
    if change=='eligible':eligible={r['evidence_id'] for r in rows[:-1]}
    if change=='version':Path(rows[0]['source_path']).write_text('changed',encoding='utf-8')
    if change=='title':question=question.replace('验收文件示范文本','错误模板示范文本')
    bundle,cards=get_result(rows,question,eligible)
    assert render_list(bundle['complete_list_audit'],cards,question) is None
    assert enforce_complete_list(question,{'complete_list_audit':bundle['complete_list_audit'],'citations':cards})['answer_status']=='LIST_COVERAGE_REQUIRED'


def test_replay_requires_current_question_excerpt_and_primary_citation(tmp_path):
    rows=evidence(tmp_path);bundle,cards=get_result(rows);audit=bundle['complete_list_audit']
    assert render_list(audit,cards,'另一题') is None
    wrong=copy.deepcopy(cards);wrong[0]['excerpt']='虚构章节'
    assert render_list(audit,wrong,QUESTION) is None
    changed=copy.deepcopy(audit);changed['chapters'][0]['title']='伪造章节'
    assert render_list(changed,cards,QUESTION) is None
    wrong=copy.deepcopy(cards);wrong[0]['answer_usage']='BACKGROUND'
    assert render_list(audit,wrong,QUESTION) is None


def test_outline_is_not_a_fallback_for_responsibilities_or_unnamed_sources(tmp_path):
    rows=evidence(tmp_path);q=QUESTION+'各章由谁负责？';bundle,cards=get_result(rows,q)
    assert render_list(bundle['complete_list_audit'],cards,q) is None
    from app.retrieval.appendix_outline import appendix_request
    assert appendix_request('附件2包含哪些章节？') is None


def test_multiple_source_outlines_require_disambiguation(tmp_path):
    rows=evidence(tmp_path)
    extra=[{**r,'source_path':r['source_path']+'.other','evidence_id':r['evidence_id']+'other'} for r in rows]
    bundle,cards=get_result(rows+extra)
    assert not cards and bundle['complete_list_audit']['status']=='APPENDIX_OUTLINE_NOT_UNIQUE'


def test_partial_outline_stays_local_and_old_preview_cannot_pay_to_fill_details(daily,tmp_path):
    service,flow,store,_,_,_,calls,_,prices,run=daily;approve(daily)
    key=run();preview=flow.prepare(key,'CONCISE_V1')
    bundle,cards=get_result(evidence(tmp_path));native=render_list(bundle['complete_list_audit'],cards,QUESTION)
    def change(state):
        state['query_runs'][key].update(question=QUESTION,result=native)
        state['generations'][preview['preview_id']].update(question=QUESTION,citations=cards,complete_list_audit=bundle['complete_list_audit'])
    store._mutate(change);flow.source_current=lambda c:True;before=len(prices)
    assert service.apply(key)['result']['daily_model']['route']=='LOCAL_DIRECT'
    assert service.store.query_run(key)['result']['answer_completeness']=='PARTIAL'
    with pytest.raises(ValueError,match='附件章节'):flow.prepare(key,'CONCISE_V1')
    with pytest.raises(ValueError,match='附件章节'):flow.run(preview['preview_id'],preview['packet_sha256'],'test')
    assert not calls and len(prices)==before and service.status()['used_requests']==0
