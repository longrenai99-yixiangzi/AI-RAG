"""Build review drafts from version-bound, project-matched source excerpts."""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any


FIELDS = [
    ('overview', '第一章 项目概况', '工程概况、定位和建设条件', '1', '核准本次工程名称、建设单位、地点、实施范围及各类指标口径。'),
    ('scope', '第二章 设计工作范围', '设计范围及界面', '2.1', '按本次合同明确委托范围、排除项，以及各设计单位的接口和提资责任。'),
    ('other_work', '第二章 设计工作范围', '配合工作', '2.2', '明确报批、审图、深化配合、竣工图及交档等本次委托事项。'),
    ('deliverables', '第二章 设计工作范围', '提交成果', '2.3', '逐项核准成果名称、格式、份数、深度、计算书和模型的交付要求。'),
    ('basis', '第三章 设计工作要求', '设计依据和输入资料', '3.1', '列明实际收到的合同、批准文件、图纸、勘察及接口资料和版本；要求提供不等于已经收到。'),
    ('schedule', '第三章 设计工作要求', '进度要求', '3.2', '核准本次起止节点、前置资料、内部审核及外部审批时间；不直接沿用旧日期。'),
    ('limits', '第三章 设计工作要求', '技术及经济限额', '3.3', '分别核准指标对象、单位、面积口径、分项限额和合计；不跨项目套值。'),
    ('coordination', '第三章 设计工作要求', '设计和施工配合', '3.4', '明确提资、反馈、会审、变更、现场配合及回复时限；含糊字句先核实。'),
    ('technical', '第四章 各专业设计技术要点', '各专业要点', '4', '根据本项目实际专业和工艺逐项编写；来源中已列要点不等于全部专业均已覆盖。'),
    ('other_terms', '第五章 其它要求', '保密、知识产权及分包约束', '5', '与本次合同核对后再采用，不把旧项目条款直接定稿。'),
]
STAGES = {'方案设计', '初步设计', '施工图设计'}


def _number(heading: str) -> str:
    match = re.search(r'(?:^| > )(\d+(?:\.\d+)*)(?:\s|[^\d.])', heading)
    return match[1] if match else ''


def _matches(heading: str, prefix: str) -> bool:
    number = _number(heading)
    return number == prefix or number.startswith(prefix + '.')


def source_units(parsed: dict[str, Any], *, project: str, stage: str,
                 source_path: str, source_version: str,
                 source_sha256: str) -> list[dict[str, Any]]:
    if stage not in STAGES or not project.strip():
        raise ValueError('请明确项目及方案、初步设计或施工图设计阶段。')
    if not re.fullmatch(r'[a-f0-9]{64}', source_version) or source_sha256 != source_version:
        raise ValueError('原件版本未核对，不能编入草稿。')
    document = next((doc for doc in parsed['documents'] if doc['source_path'].casefold() == source_path.casefold()), None)
    if not document:
        raise ValueError('解析内容与所选原件不一致。')
    if document.get('content_hash') != source_version or document.get('parse_status') != 'parsed':
        raise ValueError('解析版本与原件不一致，或原件未成功解析。')
    names = ((document.get('document_profile') or {}).get('project') or {}).get('value') or []
    if project not in names:
        raise ValueError('来源不属于所选项目，不能混用。')
    if stage not in document['file_name']:
        raise ValueError('来源与本次设计阶段不一致，不能直接沿用。')
    did = document['document_id']
    sections = {row['section_id']: row for row in parsed['sections'] if row['document_id'] == did}
    tables = {row['table_id']: row for row in parsed['tables'] if row['document_id'] == did}
    units = []
    for section in sections.values():
        if section.get('heading_id'):
            units.append({'unit_id': section['heading_id'], 'heading': section['heading_path'],
                          'text': section['heading'], 'location': section['location_start'], 'kind': 'HEADING',
                          'section_order': section['section_order'], 'position': -1, 'row_order': 0})
    for paragraph in parsed['paragraphs']:
        if paragraph['document_id'] != did:
            continue
        units.append({'unit_id': paragraph['paragraph_id'], 'heading': sections[paragraph['section_id']]['heading_path'],
                      'text': paragraph['text'], 'location': paragraph['location'], 'kind': 'PARAGRAPH',
                      'section_order': sections[paragraph['section_id']].get('section_order', 0),
                      'position': paragraph['location'].get('body_order', paragraph.get('order', 0)), 'row_order': 0})
    for row in parsed['table_rows']:
        if row['document_id'] != did:
            continue
        table = tables[row['table_id']]
        units.append({'unit_id': row['table_row_id'], 'heading': sections[row['section_id']]['heading_path'],
                      'text': ' | '.join(str(value) for value in row['values']), 'location': row['source_location'],
                      'kind': 'TABLE_ROW', 'values': copy.deepcopy(row['values']), 'table_title': table['table_title'],
                      'section_order': sections[row['section_id']].get('section_order', 0),
                      'position': row['source_location'].get('body_order', 0), 'row_order': row['row_number']})
    for unit in units:
        unit.update(source_path=source_path, source_version=source_version, bound_project=project, bound_stage=stage,
                    text_sha256=hashlib.sha256(unit['text'].encode('utf-8')).hexdigest(),
                    status='SOURCE_RECORD_NOT_APPROVED_FOR_CURRENT_ISSUE')
    return sorted(units, key=lambda unit: (unit['section_order'], unit['position'], unit['row_order']))


def build_taskbook_draft(*, project: str, stage: str, units: list[dict[str, Any]],
                         current_inputs: dict[str, str] | None = None,
                         review_notes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not project.strip() or stage not in STAGES:
        raise ValueError('请明确项目和设计阶段。')
    for unit in units:
        if unit.get('bound_project') != project or unit.get('bound_stage') != stage:
            raise ValueError('资料与本次项目或阶段不符。')
        if not re.fullmatch(r'[a-f0-9]{64}', unit.get('source_version', '')) or hashlib.sha256(unit['text'].encode('utf-8')).hexdigest() != unit.get('text_sha256'):
            raise ValueError('引用内容或版本校验未通过。')
    if len({unit['unit_id'] for unit in units}) != len(units):
        raise ValueError('来源记录重复，需先核对或去重。')
    current_inputs = current_inputs or {}
    allowed = {row[0] for row in FIELDS}
    if set(current_inputs) - allowed or any(not isinstance(value, str) or not value.strip() for value in current_inputs.values()):
        raise ValueError('本次输入字段不正确或为空。')
    field_rows = []
    for key, chapter, label, prefix, guidance in FIELDS:
        evidence = [copy.deepcopy(unit) for unit in units if _matches(unit['heading'], prefix)]
        text = current_inputs.get(key)
        status = 'USER_INPUT_PENDING_REVIEW'
        if text is None:
            text = '\n\n'.join(unit['text'] for unit in evidence) if evidence else '[待补资料、待填写]'
            status = 'SOURCE_DERIVED_DRAFT_PENDING_REVIEW' if evidence else 'MISSING_CURRENT_INPUT'
        elif evidence:
            original = '\n\n'.join(unit['text'] for unit in evidence)
            text = '原资料转写（未确认本次沿用）：\n' + original + '\n\n本次补充（待核准，未自动替换以上原要求）：\n' + text
        field_rows.append({'field': key, 'chapter': chapter, 'label': label, 'guidance': guidance,
                           'current_text': text, 'current_status': status,
                           'source_evidence': evidence})
    by_id = {unit['unit_id']: unit for unit in units}
    notes = []
    for note in review_notes or []:
        ids = note.get('unit_ids') or []
        if not ids or any(unit_id not in by_id for unit_id in ids):
            raise ValueError('待核事项必须绑定当前草稿的同版原文位置。')
        notes.append({**copy.deepcopy(note), 'status': 'NEEDS_OWNER_REVIEW',
                      'sources': [{'source_path': by_id[i]['source_path'], 'source_version': by_id[i]['source_version'],
                                   'location': by_id[i]['location']} for i in ids]})
    return {'project': project, 'stage': stage, 'status': 'DRAFT_PENDING_REVIEW',
            'purpose': '资料回放和编制准备；不作为本次已批准、已下发任务书',
            'fields': field_rows, 'review_notes': notes,
            'source_inventory': copy.deepcopy(units),
            'missing_current_fields': [row['field'] for row in field_rows if row['current_status'] == 'MISSING_CURRENT_INPUT'],
            'review_required_fields': [row['field'] for row in field_rows],
            'owner_approved': False, 'ready_for_issue': False, 'knowledge_published': False}


def render_taskbook_draft(draft: dict[str, Any], evidence_file: str) -> str:
    lines = [f"# {draft['project']} · {draft['stage']}任务书编制草稿", '',
             '**状态：待核对、未审签、未下发。** 本稿用于验证资料到工作文件的链路；旧资料记载没有自动成为本次要求。', '',
             f'完整来源及专业条文见[来源核对表]({evidence_file})。', '']
    chapter = ''
    for row in draft['fields']:
        if row['chapter'] != chapter:
            chapter = row['chapter']; lines.extend(['## ' + chapter, ''])
        label = '原资料派生草稿，未确认本次沿用' if row['current_status'] == 'SOURCE_DERIVED_DRAFT_PENDING_REVIEW' else '本次补充草稿，尚待审核' if row['current_status'] == 'USER_INPUT_PENDING_REVIEW' else '待补内容'
        lines.extend(['### ' + row['label'], '', '**状态：** ' + label, '',
                      '**编制提示：** ' + row['guidance'], '', row['current_text'], ''])
        evidence = row['source_evidence']
        if row['field'] == 'technical':
            headings = list(dict.fromkeys(unit['heading'] for unit in evidence))
            lines.extend(['**已定位的专业目录：**', '', *['- ' + heading for heading in headings], '',
                          f'完整原文共{len(evidence)}条记录，保留在来源核对表；此处未将旧要求转写为本次已采用条款。', ''])
        elif evidence:
            lines.extend([f'本项依据{len(evidence)}条同版原文及标题记录，逐条位置和原文见来源核对表。', ''])
        else: lines.extend(['未取得该项的同项目原文，保留待补；没有用其他项目替代。', ''])
    lines.extend(['## 待确认事项', ''])
    for note in draft['review_notes']:
        lines.extend(['- **' + note['title'] + '：** ' + note['reason'],
                      '  核对位置：' + '、'.join(note['unit_ids']), ''])
    lines.extend(['## 下发前必须补齐', '',
                  '- 确认当前有效合同、图纸、批准文件、委托范围和版本。',
                  '- 核准本次日期、份数、指标、专业接口以及责任人。',
                  '- 处理待确认事项，完成实际审核审批后才能另行定稿。', ''])
    return '\n'.join(lines)


def render_source_evidence(draft: dict[str, Any]) -> str:
    lines = [f"# {draft['project']} · 原文与草稿核对表", '', '以下均为所选版本的原文记载，不表示已确认本次沿用。', '']
    for path, version in sorted({(unit['source_path'], unit['source_version']) for unit in draft['source_inventory']}):
        lines.extend(['原件：' + path.replace('\\', '/').rsplit('/', 1)[-1], '来源版本标识（核对用）：' + version, ''])
    for unit in draft['source_inventory']:
        location = unit['location']
        label = f"原件第{location['table']}表第{location.get('row', '?')}行" if location.get('table') else f"原件第{location.get('paragraph_start', location.get('paragraph', '?'))}段"
        lines.extend(['## ' + unit['heading'], '', label, '', unit['text'], ''])
    return '\n'.join(lines)
