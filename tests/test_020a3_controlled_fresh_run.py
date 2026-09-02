from scripts.run_020a3_controlled_fresh_run import _is_old_ba010_fact, _location_matches


def test_ba010_old_runtime_fact_is_detected_for_boundary_audit():
    assert _is_old_ba010_fact({"fact_aggregation": {"total_rows": 80, "increase_effect_count": 37, "undetermined_profit_count": 43}})


def test_location_matching_handles_pdf_page_and_exact_xlsx_row():
    assert _location_matches({"page": 17, "text_length": 120}, [{"page": 17, "section": "目标章节"}])
    assert not _location_matches({"sheet_name": "Sheet1", "row_start": 1, "row_end": 362}, [{"sheet_name": "Sheet1", "row_start": 89, "row_end": 89}])
