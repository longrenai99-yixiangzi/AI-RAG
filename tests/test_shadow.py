from pathlib import Path

from app.ingestion.shadow.report import render_shadow_markdown
from app.ingestion.shadow.shadow_runner import run_shadow_pipeline


FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _normal_files() -> list[Path]:
    return [
        FIXTURE_ROOT / "markdown" / "normal.md",
        FIXTURE_ROOT / "ppt" / "normal.pptx",
        FIXTURE_ROOT / "pdf" / "normal.pdf",
        FIXTURE_ROOT / "docx" / "normal.docx",
        FIXTURE_ROOT / "xlsx" / "normal.xlsx",
    ]


def test_shadow_compares_all_five_formats_without_formal_index_write() -> None:
    shadow = run_shadow_pipeline(FIXTURE_ROOT, files=_normal_files())
    comparison = shadow.comparison

    assert comparison.new_document_count == 5
    assert comparison.legacy_document_count == 5
    assert comparison.new_chunk_count > 0
    assert comparison.legacy_chunk_count > 0
    assert comparison.source_path_document_match_rate == 1
    assert comparison.source_path_match_rate == 1
    assert comparison.new_metadata_coverage_rate == 1
    assert comparison.new_exception_file_count == 0
    assert comparison.adapter_chunk_count == comparison.new_chunk_count
    assert comparison.adapter_bm25_record_count == comparison.new_chunk_count
    assert comparison.adapter_qdrant_payload_count == comparison.new_chunk_count

    report = render_shadow_markdown(comparison)
    assert "chunk_id 稳定率" in report
    assert "Metadata 覆盖率" in report


def test_shadow_reports_exception_consistently() -> None:
    path = FIXTURE_ROOT / "pdf" / "broken.pdf"

    shadow = run_shadow_pipeline(FIXTURE_ROOT, files=[path])

    assert shadow.comparison.new_exception_file_count == 1
    assert shadow.comparison.legacy_exception_file_count == 1
    assert shadow.comparison.new_chunk_count == 0
    assert shadow.comparison.adapter_chunk_count == 0
