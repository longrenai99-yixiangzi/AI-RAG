from app.knowledge_engineering.structured_v2 import chunk_units, quality_for, retrieval_text
from app.document_intelligence.v2 import DocumentIntelligenceV2Builder, document_id


def test_semantic_chunk_keeps_unit_and_context():
    chunks = chunk_units(["第一项：" + "甲" * 580, "第二项：" + "乙" * 100])
    assert len(chunks) == 2
    assert "第二项" in chunks[1]
    assert "[章节]" in retrieval_text(domain="设计管理", document_title="制度", section_path="第一章", raw_text="正文")
    assert quality_for("表名：台账\n表头：项目\n行：" + "甲" * 40, has_context=True, is_table=True)[0] == 100


def test_txt_and_html_are_parsed_without_source_rewrite(tmp_path):
    txt = tmp_path / "说明.txt"
    txt.write_text("第一行\n第二行", encoding="utf-8")
    html = tmp_path / "说明.html"
    html.write_text("<h1>章节</h1><p>正文</p>", encoding="utf-8")
    builder = DocumentIntelligenceV2Builder(tmp_path)
    assert builder._parse_txt(txt, document_id(txt))["parse_status"] == "parsed"
    assert len(builder._parse_html(html, document_id(html))["paragraphs"]) == 1
