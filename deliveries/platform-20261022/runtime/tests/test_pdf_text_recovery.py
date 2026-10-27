from copy import deepcopy
import hashlib
from pathlib import Path

import pymupdf
import pytest

from app.ingestion.pdf_text_recovery import PROFILES, page_answer_span, recover_pdf_citations, without_watermarks,clean_source_records
from app.trial.platform_existing import source_extract


def test_watermark_matching_keeps_business_names_dates_and_unproven_fragments():
    stamp = 'Example Company 2024-12-30 16:03'
    body = 'Example负责设计管理，2024-12-30完成审核。'
    assert without_watermarks(body+'\n'+stamp+'\n'+stamp[:22], [stamp]) == body
    assert without_watermarks('Example\n2024-12-30', [stamp]) == 'Example\n2024-12-30'
    assert without_watermarks(stamp[:22]+'\n业务正文。', [stamp]) == stamp[:22]+'\n业务正文。'
    assert without_watermarks('ExampleReviewer\n'+stamp, ['ExampleReviewer',stamp], '审核人ExampleReviewer负责复核。') == 'ExampleReviewer'
    assert without_watermarks(stamp, [stamp], stamp) == stamp
    assert without_watermarks(stamp[:22], [stamp], '登记：'+stamp[:22]) == stamp[:22]


LEVELS = '一级协调计划：总节点完成。\n二级协调计划：由一级分解，若涉及专项，需外审合格。\n三级协调计划：完成细项核定。\n2）其他编制要求。'


def test_complete_level_selection_retains_conditions_and_rejects_partial_sequence():
    start, end, method = page_answer_span(LEVELS, '一、二、三级计划分别包括哪些节点？')
    assert LEVELS[start:end].strip() == LEVELS.split('2）')[0].strip()
    assert method == 'NATIVE_COMPLETE_LEVEL_BLOCKS'
    assert page_answer_span(LEVELS.replace('二级协调计划：', '四级协调计划：'), '一二三级计划包括什么？') is None
    assert page_answer_span(LEVELS.replace('。\n2）', '\n2）'), '一二三级计划包括什么？') is None
    assert page_answer_span(LEVELS, '2025年一二三级计划节点？') is None
    assert page_answer_span(LEVELS, '一二三级计划与其他计划比较？') is None
    assert page_answer_span(LEVELS, '一二三级审查包括哪些内容？') is None


def test_definition_selection_is_literal_complete_and_not_a_formula_guesser():
    text = '9.1\n收益定义\n1）收益率定义：收益率=金额÷产值×100%。\n金额：经审核确认的数额；\n产值：合同约定范围的产值。\n10\n附则'
    start, end, method = page_answer_span(text, '收益率定义和计算公式是什么？')
    assert '合同约定范围' in text[start:end] and '附则' not in text[start:end]
    assert method == 'NATIVE_DEFINITION_BLOCK'
    assert page_answer_span(text, '净收益率定义是什么？') is None
    assert page_answer_span(text, '收益率定义及合同履约要求是什么？') is None
    assert page_answer_span(text, '根据《演示手册》收益率定义和计算公式是什么？') == (start, end, method)
    assert page_answer_span(text.split('\n10')[0], '收益率定义是什么？') is None


@pytest.fixture
def native_pdf(tmp_path, monkeypatch):
    path = tmp_path/'manual.pdf'
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_text((80, 70), 'Business owner Example: checked on 2024-12-30.')
    page.insert_text((80, 110), 'Example Company 2024-12-30 16:03', fontsize=16, fill_opacity=.2,
                     morph=(pymupdf.Point(80, 110), pymupdf.Matrix(45)))
    doc.save(path); doc.close()
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    with pymupdf.open(path) as doc:
        line = next(l for b in doc[0].get_text('dict')['blocks'] for l in b.get('lines', []) if abs(l['dir'][1])>.01)
        span = line['spans'][0]
        monkeypatch.setitem(PROFILES, version, {'font':span['font'], 'size':span['size'], 'alpha':span['alpha'], 'direction':line['dir']})
        text = doc[0].get_text()
    return {'citation_id':'S1', 'evidence_id':'original-chunk', 'source_id':'SRC_test', 'source_path':str(path),
            'file_name':path.name, 'source_version':version, 'location':{'section':'Page 1'},
            'excerpt':text, 'answer_usage':'PRIMARY'}


def test_real_native_geometry_removes_only_the_profiled_watermark(native_pdf):
    before = deepcopy(native_pdf)
    result = source_extract({'answer_status':'SOURCES_ONLY', 'citations':[native_pdf]}, 'Who checked?')
    assert 'Example Company' not in result['answer']
    assert 'Business owner Example: checked on 2024-12-30.' in result['answer']
    assert 'Example Company' not in result['citations'][0]['excerpt']
    assert result['citations'][0]['pdf_text_audit']['removed_chars'] > 0
    assert native_pdf == before


def test_changed_unprofiled_and_wrong_page_sources_are_not_cleaned(native_pdf):
    for override in [{'source_version':'a'*64}, {'location':{'section':'Page 99'}}]:
        card = {**native_pdf, **override}
        assert recover_pdf_citations([card], '') == [card]
    Path(native_pdf['source_path']).write_bytes(b'changed')
    assert recover_pdf_citations([native_pdf], '') == [native_pdf]


def test_parser_filters_known_watermarks_before_any_chunk_or_vector_is_created(native_pdf):
    from app.parsers import parse_file
    parsed=parse_file(Path(native_pdf['source_path']),25)
    assert parsed.parse_status=='parsed'
    assert all('Example Company' not in block.text for block in parsed.blocks)
    assert 'Business owner Example: checked on 2024-12-30.' in parsed.blocks[0].text
    assert parsed.sha256==native_pdf['source_version']
    from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
    from app.ingestion.loaders.pdf_loader import load_pdf
    p=Path(native_pdf['source_path'])
    assert 'Example Company' not in DocumentIntelligenceV2Builder(p.parent)._parse_pdf(p,'test')['text']
    assert all('Example Company' not in b.text for b in load_pdf(p,'test').blocks)


def test_same_cleanup_covers_numeric_pages_and_expanded_section_citations(native_pdf):
    for location in [{'page':1},{'section':'Page 1 > 附件说明'}]:
        result=recover_pdf_citations([{**native_pdf,'location':location}], '')[0]
        assert 'Example Company' not in result['excerpt']
        assert '2024-12-30' in result['excerpt']


def test_markdown_export_and_future_import_use_verified_native_watermarks(native_pdf,tmp_path,monkeypatch):
    path=tmp_path/'converted.md';path.write_text('# 转换稿\n'+native_pdf['excerpt'],encoding='utf-8')
    raw=path.read_bytes();version=hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(PROFILES,version,{'original_path':native_pdf['source_path'],'original_version':native_pdf['source_version']})
    row={'text':native_pdf['excerpt'],'source_path':str(path),'source_version':version,'location':{'line_start':2}}
    result=clean_source_records([row])[0]
    assert 'Example Company' not in result['text'] and '2024-12-30' in result['text']
    assert result['location']==row['location'] and result['text_cleanup']['native_original_version']==native_pdf['source_version']
    from app.parsers import parse_file
    parsed=parse_file(path,25)
    assert parsed.parse_status=='parsed' and all('Example Company' not in b.text for b in parsed.blocks)
    assert parsed.blocks[0].location['line_start']==1 and path.read_bytes()==raw
    from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
    from app.ingestion.loaders.markdown_loader import MarkdownLoader
    assert all('Example Company' not in b.text for b in MarkdownLoader().load(path,'test').blocks)
    v2=DocumentIntelligenceV2Builder(path.parent)._parse_md(path,'test')
    assert 'Example Company' not in v2['text']
    assert all(p['location']['line_start']<=len(raw.decode().splitlines()) for p in v2['paragraphs'])
    Path(native_pdf['source_path']).write_bytes(b'changed original')
    assert clean_source_records([row])[0]['text']==row['text']
