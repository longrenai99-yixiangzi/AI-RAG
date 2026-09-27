from scripts.run_verified_answer_engine_v2 import _load_structured_rows, _matched_structured_rows


def test_missing_private_structured_artifact_is_explicit_and_safe():
    rows, audit = _load_structured_rows()

    assert rows == []
    assert audit["status"] == "STRUCTURED_SOURCE_ARTIFACT_INCOMPLETE"
    assert audit["reason"] == "Frozen structured source artifact or table index is missing."


def test_structured_rows_do_not_cross_document_boundary():
    rows, _ = _load_structured_rows()
    candidates = [{"source_path": "synthetic/private/source.xlsx", "location": {"table": 11}}]

    assert _matched_structured_rows(candidates, rows) == []
