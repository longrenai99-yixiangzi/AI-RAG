from pathlib import Path

from app.ingestion.pipeline import run_document_pipeline


FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_pipeline_validates_all_five_loader_formats() -> None:
    files = [
        FIXTURE_ROOT / "markdown" / "normal.md",
        FIXTURE_ROOT / "ppt" / "normal.pptx",
        FIXTURE_ROOT / "pdf" / "normal.pdf",
        FIXTURE_ROOT / "docx" / "normal.docx",
        FIXTURE_ROOT / "xlsx" / "normal.xlsx",
    ]

    result = run_document_pipeline(FIXTURE_ROOT, files=files)

    assert result.scanned_files == 5
    assert result.status_counts() == {"parsed": 5}
    assert set(result.file_type_counts()) == {".md", ".pptx", ".pdf", ".docx", ".xlsx"}
    assert result.source_block_count > 0
    assert result.chunk_count > 0
    assert result.metadata_complete_chunk_count() == result.chunk_count
    assert result.location_valid_chunk_count() == result.chunk_count
    assert all(
        document.metadata["file_type"] == document.file_type
        and document.metadata["file_name"] == document.path.name
        for document in result.documents
    )


def test_pipeline_preserves_empty_and_read_error_states() -> None:
    files = [
        FIXTURE_ROOT / "ppt" / "empty.pptx",
        FIXTURE_ROOT / "pdf" / "empty.pdf",
        FIXTURE_ROOT / "docx" / "empty.docx",
        FIXTURE_ROOT / "xlsx" / "empty.xlsx",
        FIXTURE_ROOT / "pdf" / "broken.pdf",
        FIXTURE_ROOT / "docx" / "broken.docx",
        FIXTURE_ROOT / "xlsx" / "broken.xlsx",
    ]

    result = run_document_pipeline(FIXTURE_ROOT, files=files)

    assert result.status_counts() == {"empty": 4, "read_error": 3}
    assert all(document.chunks == [] for document in result.documents)
    assert all(document.error for document in result.documents if document.status == "read_error")


def test_pipeline_metadata_allows_missing_optional_enterprise_labels() -> None:
    path = FIXTURE_ROOT / "markdown" / "normal.md"

    result = run_document_pipeline(FIXTURE_ROOT, files=[path])
    metadata = result.documents[0].metadata

    assert metadata["file_type"] == ".md"
    assert metadata["file_name"] == "normal.md"
    assert metadata["source_path"].endswith("normal.md")
    assert metadata["board"] == "设计管理"
    assert metadata["knowledge_type"] is None
    assert metadata["discipline"] is None


def test_pipeline_limit_per_type_keeps_one_sample_per_format() -> None:
    result = run_document_pipeline(FIXTURE_ROOT, limit_per_type=1)

    assert result.scanned_files == 5
    assert set(result.file_type_counts()) == {".md", ".pptx", ".pdf", ".docx", ".xlsx"}
