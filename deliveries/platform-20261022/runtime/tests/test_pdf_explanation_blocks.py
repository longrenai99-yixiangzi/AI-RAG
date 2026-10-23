import hashlib
from pathlib import Path

import pytest

from app.retrieval.anchored_sections import pdf_explanation_blocks,expand_candidates
from app.retrieval.focused_candidate import FocusedCandidate,explicit_topic_coverage
from app.trial.assisted_chat import assemble
from app.trial.platform_existing import source_extract
from test_focused_candidate import Reranker,Titles

TEXT='原表残余\n99\n《采购交接清单》说明：\n1）明确交付范围和成果。\n2）若存在联合协作，仍需列出各方职责。\n3）明确计划移交时间。\n第二章 风险检查\n无关数量888'


def record(tmp_path,text=TEXT,suffix='.pdf'):
    path=tmp_path/('工作手册'+suffix);path.write_text(text,encoding='utf-8')
    return {'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'document_id':'doc',
            'source_id':'SRC_test','evidence_id':'native-row','text':text,'file_name':path.name,'heading_path':'Page 8','location':{'section':'Page 8'},'role':'DIRECT'}


def test_explicit_note_keeps_all_items_and_restrictions_without_adjacent_table(tmp_path):
    row=record(tmp_path);notes=pdf_explanation_blocks(row)
    assert len(notes)==1;note=notes[0]
    assert note['text']==row['text'][note['location']['char_start']:note['location']['char_end']].strip()
    assert '仍需' in note['text'] and '计划移交时间' in note['text']
    assert all(t not in note['text'] for t in ['原表残余','风险检查','888'])
    assert note['retrieved_child_ids']==['native-row'] and note['source_version']==row['source_version']
    assert note['explanation_block']['item_count']==3
    expanded=expand_candidates([row],[])
    assert expanded[-1]==row and expanded[0]['evidence_id'].startswith('pdf-note-')


@pytest.mark.parametrize('text,suffix',[
    (TEXT,'.md'),(TEXT.replace('说明：','备注'),'.pdf'),
    (TEXT.split('第二章')[0],'.pdf'),
    (TEXT.replace('2）','5）'),'.pdf'),
    (TEXT.replace('2）','1）'),'.pdf'),
    (TEXT.replace('移交时间。','移交时间'),'.pdf'),
    (TEXT.replace('1）明确','无编号前言\n1）明确'),'.pdf'),
])
def test_ambiguous_truncated_or_non_native_blocks_are_not_promoted(tmp_path,text,suffix):
    row=record(tmp_path,text,suffix)
    assert not pdf_explanation_blocks(row)
    assert expand_candidates([row],[])==[row]


def test_heading_recovery_passes_topic_guard_without_weakening_incidental_mentions(tmp_path):
    row=record(tmp_path);question='采购交接需要明确哪些内容？'
    assert explicit_topic_coverage(question,row)['status']=='RELATED_MENTION_ONLY'
    result=FocusedCandidate([],Titles(),Reranker()).rank(question,[row])
    first=result['candidate_evidence'][0]
    assert first['answer_usage']=='PRIMARY' and first['explanation_block']['title']=='采购交接清单'
    assert first['topic_coverage']['status']=='TOPIC_PRESENT'
    _,cards=assemble(result,question,True)
    assert cards[0]['explanation_block']['item_count']==3
    result=source_extract({'answer_status':'SOURCES_ONLY','citations':cards},question)
    assert '仍需' in result['answer'] and '表格全部字段' in result['notice']


def test_same_page_other_topic_and_named_source_constraints_survive(tmp_path):
    row=record(tmp_path);doc={**row,'file_name':Path(row['source_path']).name}
    candidate=FocusedCandidate([],Titles(),Reranker(),documents={'doc':doc})
    result=candidate.rank('外部审计需要明确哪些内容？',[row])
    assert all(c['answer_usage']=='BACKGROUND' for c in result['candidate_evidence'])
    assert not candidate.rank('《其他手册.pdf》采购交接需要明确哪些内容？',[row])['candidate_evidence']


def test_changed_original_bytes_are_rejected_before_citation(tmp_path):
    row=record(tmp_path);note=pdf_explanation_blocks(row)[0];note['answer_usage']='PRIMARY'
    Path(row['source_path']).write_text('changed',encoding='utf-8')
    assert not assemble({'candidate_evidence':[note]})[0].items


def test_note_is_not_promoted_as_table_column_definitions(tmp_path):
    note=pdf_explanation_blocks(record(tmp_path))[0]
    result=FocusedCandidate([],Titles(),Reranker()).rank('采购交接需要明确哪些表头字段？',[note])
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert all(c['answer_usage']=='BACKGROUND' for c in result['candidate_evidence'])
