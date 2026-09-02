from pathlib import Path

from app.ingestion.loaders.pdf_loader import PDFLoader


FIXTURES = Path(__file__).parent / "fixtures" / "pdf"
LOADER = PDFLoader()


def test_normal_pdf_emits_page_source_block_and_quality_metrics() -> None:
    result = LOADER.load(FIXTURES / "normal.pdf", "normal")

    assert result.status == "parsed"
    assert result.quality is not None
    assert result.quality.total_pages == 1
    assert result.quality.text_pages == 1
    assert result.quality.image_page_ratio == 0
    assert len(result.blocks) == 1
    assert result.blocks[0].location == {"page": 1, "text_length": len(result.blocks[0].text)}
    assert "Table text:" in result.blocks[0].text
    assert "Field | Value" in result.blocks[0].text


def test_empty_pdf_returns_empty_status_without_ocr() -> None:
    result = LOADER.load(FIXTURES / "empty.pdf", "empty")

    assert result.status == "empty"
    assert result.quality is not None
    assert result.quality.total_pages == 1
    assert result.quality.text_chars == 0
    assert result.quality.image_pages == 0
    assert result.quality.suspected_scanned is False
    assert len(result.blocks) == 1
    assert result.blocks[0].text == ""


def test_scanned_feature_pdf_is_marked_needs_ocr_without_running_ocr() -> None:
    result = LOADER.load(FIXTURES / "scanned_feature.pdf", "scanned")

    assert result.status == "needs_ocr"
    assert result.quality is not None
    assert result.quality.total_pages == 2
    assert result.quality.image_pages == 2
    assert result.quality.image_page_ratio == 1
    assert result.quality.suspected_scanned is True
    assert len(result.blocks) == 2
    assert [block.location["page"] for block in result.blocks] == [1, 2]


def test_broken_pdf_returns_read_error_without_raising() -> None:
    result = LOADER.load(FIXTURES / "broken.pdf", "broken")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.quality is None
    assert result.error
