import pymupdf

from app.parsers import parse_file


def test_pdf_parser_keeps_page_location(tmp_path) -> None:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "设计策划应形成项目设计管理文件。" * 8)
    document.save(path)
    document.close()

    parsed = parse_file(path, 10)

    assert parsed.parse_status == "parsed"
    assert parsed.blocks[0].location["page"] == 1


def test_image_only_pdf_is_reported_for_ocr(tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    parsed = parse_file(path, 10)

    assert parsed.parse_status == "needs_ocr"
    assert parsed.needs_ocr is True
    assert parsed.blocks == []
