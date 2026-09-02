from pathlib import Path

from app.ingestion.metadata.classifier import MetadataClassifier
from app.ingestion.metadata.validator import validate_metadata
from app.ingestion.pipeline import run_document_pipeline


CLASSIFIER = MetadataClassifier()


def test_automatic_classification_uses_configured_rules(tmp_path: Path) -> None:
    path = tmp_path / "设计管理" / "制度" / "建筑制度.md"
    path.parent.mkdir(parents=True)
    path.write_text("制度正文", encoding="utf-8")

    metadata = CLASSIFIER.classify(path, tmp_path, parse_status="parsed").to_dict()

    assert metadata["board"] == "设计管理"
    assert metadata["knowledge_type"] == "制度"
    assert metadata["discipline"] == "建筑"
    assert metadata["metadata_source"]["board"] == "path"
    assert metadata["metadata_source"]["knowledge_type"] in {"path", "file_name"}
    assert metadata["metadata_source"]["discipline"] in {"path", "file_name"}
    assert metadata["metadata_review_status"] == "AUTO"
    assert validate_metadata(metadata).valid is True


def test_unknown_classification_is_allowed_but_requires_review(tmp_path: Path) -> None:
    path = tmp_path / "misc" / "unknown.md"
    path.parent.mkdir(parents=True)
    path.write_text("没有分类关键词", encoding="utf-8")

    metadata = CLASSIFIER.classify(path, tmp_path, parse_status="parsed").to_dict()
    validation = validate_metadata(metadata)

    assert metadata["board"] is None
    assert metadata["knowledge_type"] is None
    assert metadata["discipline"] is None
    assert metadata["metadata_review_status"] == "NEEDS_REVIEW"
    assert validation.valid is True
    assert len(validation.warnings) == 3


def test_low_confidence_match_is_marked_for_review(tmp_path: Path) -> None:
    path = tmp_path / "misc" / "unknown.md"
    path.parent.mkdir(parents=True)
    path.write_text("EPC", encoding="utf-8")

    metadata = CLASSIFIER.classify(
        path,
        tmp_path,
        parse_status="parsed",
        headers=["EPC"],
    ).to_dict()

    assert metadata["discipline"] == "EPC"
    assert metadata["metadata_source"]["discipline"] == "headers"
    assert metadata["metadata_confidence"]["discipline"] == 0.76
    assert metadata["metadata_review_status"] == "NEEDS_REVIEW"


def test_obsidian_front_matter_has_priority_and_full_confidence(tmp_path: Path) -> None:
    path = tmp_path / "unknown" / "note.md"
    path.parent.mkdir(parents=True)
    path.write_text("正文", encoding="utf-8")

    metadata = CLASSIFIER.classify(
        path,
        tmp_path,
        parse_status="parsed",
        front_matter={
            "board": "技术管理",
            "knowledge_type": "培训资料",
            "discipline": "BIM",
        },
    ).to_dict()

    assert metadata["board"] == "技术管理"
    assert metadata["knowledge_type"] == "培训资料"
    assert metadata["discipline"] == "BIM"
    assert set(metadata["metadata_source"].values()) == {"front_matter"}
    assert metadata["metadata_review_status"] == "AUTO"


def test_missing_optional_metadata_is_valid_but_missing_base_field_is_not(tmp_path: Path) -> None:
    path = tmp_path / "normal.md"
    path.write_text("正文", encoding="utf-8")
    metadata = CLASSIFIER.classify(path, tmp_path, parse_status="parsed").to_dict()

    metadata.pop("board")
    optional_result = validate_metadata(metadata)
    assert optional_result.valid is True

    metadata.pop("sha256")
    required_result = validate_metadata(metadata)
    assert required_result.valid is False
    assert any("sha256" in error for error in required_result.errors)


def test_schema_rejects_unknown_enum_and_invalid_confidence(tmp_path: Path) -> None:
    path = tmp_path / "normal.md"
    path.write_text("正文", encoding="utf-8")
    metadata = CLASSIFIER.classify(path, tmp_path, parse_status="parsed").to_dict()
    metadata["board"] = "未知板块"
    metadata["metadata_confidence"]["board"] = 1.2

    result = validate_metadata(metadata)

    assert result.valid is False
    assert any("board" in error for error in result.errors)
    assert any("confidence" in error for error in result.errors)


def test_pipeline_exposes_json_compatible_staging_record() -> None:
    path = Path(__file__).parent / "fixtures" / "markdown" / "normal.md"
    result = run_document_pipeline(path.parent.parent, files=[path])
    record = result.documents[0].staging_json()

    assert record["schema_version"] == "staging.v1"
    assert record["status"] == "parsed"
    assert record["source_blocks"]
    assert record["chunks"]
    assert record["chunks"][0]["metadata"]["file_type"] == ".md"
