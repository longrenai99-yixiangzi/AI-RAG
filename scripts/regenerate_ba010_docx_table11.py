from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_SOURCE = Path(r"D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\设计管理策划书-星谷科创中心项目.docx")
OUT = ROOT / "data" / "shadow" / "document_intelligence_v2" / "authorized_source_updates" / "ba010_docx_table11"
TABLE_RECORDS = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "table_index" / "records.jsonl"


def main() -> int:
    if not AUTHORIZED_SOURCE.is_file():
        raise FileNotFoundError(AUTHORIZED_SOURCE)
    table_record = _table_record()
    document = Document(AUTHORIZED_SOURCE)
    table = document.tables[10]
    raw_rows = [[cell.text for cell in row.cells] for row in table.rows]
    header_index = _header_index(raw_rows)
    headers = [_normalize(value) for value in raw_rows[header_index]]
    rows, cells = _rows_and_cells(raw_rows, headers, header_index, table_record)
    evidence = [_structured_evidence(row) for row in rows if row["is_business_row"]]
    audit = {
        "authorized_source_path": str(AUTHORIZED_SOURCE),
        "authorized_read_scope": "DOCX Table11 only",
        "authorization_type": "ONE_TIME_READ_ONLY_EXACT_SOURCE",
        "files_opened": [str(AUTHORIZED_SOURCE)],
        "root002_files_read": 1,
        "table_index": 11,
        "source_sha256": _sha256(AUTHORIZED_SOURCE),
        "source_document_id": table_record["document_id"],
        "table_id": table_record["table_id"],
        "section_id": table_record["section_id"],
        "previous_artifact_status": "DOCX_STRUCTURED_ARTIFACT_INCOMPLETE",
        "new_artifact_status": "AUTHORIZED_DOCX_TABLE11_STRUCTURED",
        "physical_rows": len(raw_rows),
        "header_row_number": header_index + 1,
        "business_rows": sum(row["is_business_row"] for row in rows),
        "rows_added": len(rows),
        "cells_added": len(cells),
        "evidence_added": len(evidence),
        "gold_used_for_runtime": False,
        "root002_refresh": 0,
        "root003_scan": 0,
    }
    _write_jsonl(OUT / "docx_table11_rows.jsonl", rows)
    _write_jsonl(OUT / "docx_table11_cells.jsonl", cells)
    _write_jsonl(OUT / "docx_table11_structured_evidence.jsonl", evidence)
    _write_json(OUT / "authorized_read_audit.json", audit)
    assert audit["root002_files_read"] == 1
    assert audit["files_opened"] == [str(AUTHORIZED_SOURCE)]
    print(json.dumps({"business_rows": audit["business_rows"], "cells": audit["cells_added"], "files_opened": 1}, ensure_ascii=False))
    return 0


def _table_record() -> dict[str, Any]:
    for record in _read_jsonl(TABLE_RECORDS):
        location = record.get("source_location") or {}
        if record.get("source_path") == str(AUTHORIZED_SOURCE) and location.get("table") == 11:
            return record
    raise RuntimeError("Table11 record not found in frozen Shadow table index")


def _header_index(rows: list[list[str]]) -> int:
    for index, values in enumerate(rows):
        normalized = "|".join(_normalize(value) for value in values)
        if "专业" in normalized and "价值创造" in normalized:
            return index
    raise RuntimeError("DOCX Table11 header row not identified")


def _rows_and_cells(raw_rows: list[list[str]], headers: list[str], header_index: int, table_record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    inherited_professional = ""
    for index, values in enumerate(raw_rows, start=1):
        row_id = _stable_id("row", table_record["table_id"], index)
        is_header = index == header_index + 1
        professional_raw = values[0] if values else ""
        professional_normalized = _normalize(professional_raw)
        inherited = False
        if index > header_index + 1 and not professional_normalized:
            professional_normalized = inherited_professional
            inherited = bool(inherited_professional)
        if professional_normalized:
            inherited_professional = professional_normalized
        business_value = values[1] if len(values) > 1 else ""
        is_business_row = index > header_index + 1 and bool(_normalize(business_value))
        location = {"table": 11, "row_start": index, "row_end": index, "column_count": len(values), "header_row": header_index + 1}
        row = {
            "document_id": table_record["document_id"], "table_id": table_record["table_id"], "row_id": row_id, "row_number": index,
            "section_id": table_record["section_id"], "source_path": str(AUTHORIZED_SOURCE), "file_name": AUTHORIZED_SOURCE.name,
            "cells": [], "professional_raw": professional_raw, "professional_normalized": professional_normalized,
            "professional_inherited": inherited, "is_header": is_header, "is_business_row": is_business_row,
            "source_location": location, "lineage_status": "LINEAGE_PARTIAL", "profit_numeric": None,
        }
        for column_number, raw_value in enumerate(values, start=1):
            header = headers[column_number - 1] if column_number - 1 < len(headers) else ""
            cell_id = _stable_id("cell", row_id, column_number)
            cell = {
                "cell_id": cell_id, "row_id": row_id, "column_id": f"C{column_number}", "column_name": header or f"未识别列{column_number}",
                "normalized_column_name": header or None, "raw_value": raw_value, "normalized_value": _normalize(raw_value),
                "row_number": index, "column_number": column_number, "source_location": location,
                "merged_cell_state": "INHERITED_VALUE" if column_number == 1 and inherited else "RAW",
            }
            row["cells"].append(cell)
            cells.append(cell)
        rows.append(row)
    return rows, cells


def _structured_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "structured_evidence_id": _stable_id("evidence", row["row_id"]), "document_id": row["document_id"], "table_id": row["table_id"],
        "row_id": row["row_id"], "cell_ids": [cell["cell_id"] for cell in row["cells"]], "evidence_type": "STRUCTURED_TABLE_ROW",
        "text_representation": " | ".join(f"{cell['column_name']}：{cell['normalized_value']}" for cell in row["cells"] if cell["normalized_value"]),
        "structured_payload": {"professional": row["professional_normalized"], "cells": row["cells"]}, "source_location": row["source_location"],
        "source_path": row["source_path"], "file_name": row["file_name"], "section_id": row["section_id"], "lineage_status": "LINEAGE_PARTIAL",
    }


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _stable_id(*parts: Any) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).hexdigest()[:24]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
