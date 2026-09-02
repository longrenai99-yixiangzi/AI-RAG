from scripts.run_verified_answer_engine_v2 import _load_structured_rows, _matched_structured_rows


def test_frozen_structured_artifact_maps_row_and_cell_provenance():
    rows, audit = _load_structured_rows()

    assert audit["status"] == "STRUCTURED_SOURCE_ARTIFACT_COMPLETE"
    assert len(rows) == audit["structured_rows_mapped"] == 80
    assert audit["structured_cells_mapped"] == 1120
    assert all({"document_id", "table_id", "section_id", "row_id", "row_number", "cells", "source_location"} <= row.keys() for row in rows)
    assert all(len(row["cells"]) == 14 for row in rows)


def test_structured_rows_do_not_cross_document_boundary():
    rows, _ = _load_structured_rows()
    candidates = [{"source_path": "D:\\unrelated.docx", "location": {"table": 11}}]

    assert _matched_structured_rows(candidates, rows) == []
