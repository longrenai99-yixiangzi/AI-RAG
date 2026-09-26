from app.knowledge_engineering.structured_v2 import build_structured_layer, chunk_units, quality_for, retrieval_text
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.document_intelligence.v2 import DocumentIntelligenceV2Builder, document_id


def test_semantic_chunk_keeps_unit_and_context():
    chunks = chunk_units(["第一项：" + "甲" * 580, "第二项：" + "乙" * 100])
    assert len(chunks) == 2
    assert "第二项" in chunks[1]
    assert "[章节]" in retrieval_text(domain="设计管理", document_title="制度", section_path="第一章", raw_text="正文")
    assert quality_for("表名：台账\n表头：项目\n行：" + "甲" * 40, has_context=True, is_table=True)[0] == 100


def test_pdf_page_labels_and_values_stay_in_one_chunk_when_page_fits():
    chunks = chunk_units([
        "前页内容：" + "甲" * 350,
        "--- Page 5 ---",
        "占地面积",
        "9.7万m²",
        "总建筑面积",
        "31.66万m²",
        "北塔（3792㎡/F）154.5m",
        "南塔（3289㎡/F）87.8m",
    ])

    page = next(chunk for chunk in chunks if "--- Page 5 ---" in chunk)
    assert "占地面积\n9.7万m²" in page
    assert "总建筑面积\n31.66万m²" in page
    assert "北塔（3792㎡/F）154.5m" in page


def test_txt_and_html_are_parsed_without_source_rewrite(tmp_path):
    txt = tmp_path / "说明.txt"
    txt.write_text("第一行\n第二行", encoding="utf-8")
    html = tmp_path / "说明.html"
    html.write_text("<h1>章节</h1><p>正文</p>", encoding="utf-8")
    builder = DocumentIntelligenceV2Builder(tmp_path)
    assert builder._parse_txt(txt, document_id(txt))["parse_status"] == "parsed"
    assert len(builder._parse_html(html, document_id(html))["paragraphs"]) == 1


def test_xlsx_semantic_row_links_to_atomic_evidence_from_its_sheet(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "多工作表台账.xlsx"
    workbook = Workbook()
    first = workbook.active
    first.title = "数据选取表格"
    first.append(["参数", "值"])
    first.append(["无关配置", "首张表"])
    target = workbook.create_sheet("项目台账")
    target.append(["序号", "专业类别", "策划点"])
    target.append([1, "结构", "目标行：地下室梁板强度统一为C35并已入图"])
    workbook.save(path)
    workbook.close()

    atomic = build_atomic_evidence(path, tmp_path)["records"]
    parsed = DocumentIntelligenceV2Builder(tmp_path).build([path], atomic)
    source = parsed["documents"][0]
    registry = {str(path).casefold(): {"source_id": "test-source", "current_hash": source["content_hash"], "body_status": "APPROVED_DEV_REMEDIATION"}}
    layer = build_structured_layer(parsed["documents"], parsed["sections"], parsed["paragraphs"], parsed["tables"], parsed["table_rows"], parsed["atomic_evidence"], registry)

    target_table = next(table for table in parsed["tables"] if table["sheet_name"] == "项目台账")
    target_evidence = next(item for item in parsed["atomic_evidence"] if item["location"].get("sheet_name") == "项目台账" and item["location"].get("row_start") == 2)
    target_chunk = next(chunk for chunk in layer["semantic_chunks"] if chunk["table_id"] == target_table["table_id"] and "目标行" in chunk["raw_text"])
    assert target_evidence["table_id"] == target_table["table_id"]
    assert target_chunk["atomic_evidence_ids"] == [target_evidence["evidence_id"]]
