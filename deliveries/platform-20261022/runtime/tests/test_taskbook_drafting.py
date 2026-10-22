import copy
import hashlib
import pytest
from app.taskbook_drafting import source_units, build_taskbook_draft, render_taskbook_draft, render_source_evidence

VERSION = 'a' * 64
PATH = 'D:/资料/甲项目施工图设计任务书.docx'

def parsed():
    return {'documents': [{'document_id': 'd1', 'source_path': PATH, 'file_name': '甲项目施工图设计任务书.docx', 'content_hash': VERSION, 'parse_status': 'parsed', 'document_profile': {'project': {'value': ['甲项目']}}}],
            'sections': [{'section_id': 's1', 'document_id': 'd1', 'heading_path': '第二章 设计工作范围 > 2.3 设计提交成果'}],
            'paragraphs': [{'paragraph_id': 'p1', 'document_id': 'd1', 'section_id': 's1', 'text': '全专业蓝图8套；计算书按合同明确。', 'location': {'paragraph_start': 4}}],
            'tables': [], 'table_rows': []}

def units():
    return source_units(parsed(), project='甲项目', stage='施工图设计', source_path=PATH, source_version=VERSION, source_sha256=VERSION)

def test_source_reference_is_not_current_requirement_or_approval():
    draft = build_taskbook_draft(project='甲项目', stage='施工图设计', units=units())
    row = next(row for row in draft['fields'] if row['field'] == 'deliverables')
    assert '蓝图8套' in row['current_text'] and row['current_status'] == 'SOURCE_DERIVED_DRAFT_PENDING_REVIEW'
    assert '蓝图8套' in row['source_evidence'][0]['text']
    assert not draft['owner_approved'] and not draft['ready_for_issue'] and not draft['knowledge_published']

@pytest.mark.parametrize('change', ['project', 'stage', 'source_version', 'text'])
def test_cross_project_stage_or_tampered_reference_rejected(change):
    rows = units(); project = '甲项目'; stage = '施工图设计'
    if change == 'project': project = '乙项目'
    if change == 'stage': stage = '初步设计'
    if change == 'source_version': rows[0]['source_version'] = 'unverified'
    if change == 'text': rows[0]['text'] = '改为20套'
    with pytest.raises(ValueError): build_taskbook_draft(project=project, stage=stage, units=rows)

@pytest.mark.parametrize('change', ['source_hash', 'parsed_hash', 'project', 'stage'])
def test_source_selection_validation(change):
    data = parsed(); kwargs = {'project': '甲项目', 'stage': '施工图设计', 'source_path': PATH, 'source_version': VERSION, 'source_sha256': VERSION}
    if change == 'source_hash': kwargs['source_sha256'] = 'b' * 64
    if change == 'parsed_hash': data['documents'][0]['content_hash'] = 'b' * 64
    if change == 'project': kwargs['project'] = '乙项目'
    if change == 'stage': kwargs['stage'] = '初步设计'
    with pytest.raises(ValueError): source_units(data, **kwargs)

def test_multi_document_parse_does_not_mix_source_records():
    data = parsed()
    data['paragraphs'].append({'paragraph_id': 'other', 'document_id': 'd2', 'section_id': 'other', 'text': '乙项目预算900万元', 'location': {}})
    result = source_units(data, project='甲项目', stage='施工图设计', source_path=PATH, source_version=VERSION, source_sha256=VERSION)
    assert len(result) == 1 and '乙项目' not in result[0]['text']

def test_missing_source_keeps_ten_fields_without_case_facts():
    draft = build_taskbook_draft(project='新项目', stage='方案设计', units=[])
    assert len(draft['missing_current_fields']) == 10
    assert not draft['source_inventory']
    assert '8套' not in render_taskbook_draft(draft, '依据.md')

def test_user_input_stays_pending_review_and_does_not_mutate_source():
    rows = units(); before = copy.deepcopy(rows)
    draft = build_taskbook_draft(project='甲项目', stage='施工图设计', units=rows, current_inputs={'deliverables': '拟提交蓝图6套，待核合同'})
    row = next(row for row in draft['fields'] if row['field'] == 'deliverables')
    assert row['current_status'] == 'USER_INPUT_PENDING_REVIEW' and '6套' in row['current_text']
    assert '蓝图8套' in row['current_text'] and '未自动替换' in row['current_text']
    assert rows == before and not draft['ready_for_issue']

def test_unknown_field_and_fake_note_reference_rejected():
    with pytest.raises(ValueError): build_taskbook_draft(project='甲项目', stage='施工图设计', units=units(), current_inputs={'approved': '是'})
    with pytest.raises(ValueError): build_taskbook_draft(project='甲项目', stage='施工图设计', units=units(), review_notes=[{'unit_ids': ['old-version']}])

def test_duplicate_evidence_is_not_double_counted():
    rows = units()
    with pytest.raises(ValueError): build_taskbook_draft(project='甲项目', stage='施工图设计', units=rows + rows)

def test_complete_paragraph_and_source_location_preserved():
    rows = units(); text = '起始。' + '完整条文；' * 250 + '末尾条件仍须核对。'
    rows[0]['text'] = text; rows[0]['text_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    draft = build_taskbook_draft(project='甲项目', stage='施工图设计', units=rows)
    output = render_taskbook_draft(draft, '依据.md')
    assert text in output and rows[0]['location'] == {'paragraph_start': 4}

def test_downloaded_evidence_has_file_version_and_human_location():
    draft = build_taskbook_draft(project='甲项目', stage='施工图设计', units=units())
    text = render_source_evidence(draft)
    assert '甲项目施工图设计任务书.docx' in text and VERSION in text
    assert '原件第4段' in text and '蓝图8套' in text
