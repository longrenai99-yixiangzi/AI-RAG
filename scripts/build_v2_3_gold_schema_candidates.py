from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl"
SECTIONS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "sections.jsonl"
TABLES = ROOT / "data" / "shadow" / "document_intelligence_v2" / "tables.jsonl"
ROWS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "table_rows.jsonl"
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"

SELECTED = [
    "c38e35bd-c77a-550a-a31a-040c26b771c4",
    "7ab3b5e7-2f42-5aca-b47f-aeeea8765d36",
    "c21f9538-1298-518b-a5d1-62ddbf92671f",
    "b97c99e2-af4c-5626-81ed-f7854ba59a68",
    "7d9a7f2c-bd40-5095-9d07-4157864af277",
    "ca66dc8d-7067-5fd1-913c-a977419f8fe8",
    "8ace032b-fe91-51f2-a424-7bbcc9a68bdd",
    "99c85c49-6e6e-52c3-a352-065732aff65f",
    "d8569497-50f1-5444-8d96-08f6259bb262",
    "cd5be857-c87f-57c4-ad46-e31a99c2a64d",
    "abb5afc0-e3c8-5189-8189-810f67464cae",
    "fa01092e-f9ed-5282-aaed-4c39b84b375c",
    "bf791961-10bf-52c5-a380-5c18bfa22e16",
    "c89537fc-b132-5696-ab4e-721e09e117ef",
    "2d9c5e68-b783-52d6-88c5-6b0638e64c7b",
    "bc1dcf17-42b5-50ac-9b6f-e4e30a3be0c2",
]

SECTION_OVERRIDES = {
    "bc1dcf17-42b5-50ac-9b6f-e4e30a3be0c2": "第二章 设计策划目标 > 2.1设计进度目标 > 2.1.3设计里程碑节点",
    "99c85c49-6e6e-52c3-a352-065732aff65f": "第一章 项目概况 > 1.1 工程概况",
    "fa01092e-f9ed-5282-aaed-4c39b84b375c": "第一章 项目概况 > 1.2需求分析",
    "bf791961-10bf-52c5-a380-5c18bfa22e16": "第一章 项目概况 > 1.3 设计现状",
    "2d9c5e68-b783-52d6-88c5-6b0638e64c7b": "第三章 设计组织策划 > 3.2 设计管理相关方权责分配",
    "abb5afc0-e3c8-5189-8189-810f67464cae": "第四章 设计合约规划",
    "d8569497-50f1-5444-8d96-08f6259bb262": "第七章 报批报建管理 > 7.2报批报建主要事项",
    "cd5be857-c87f-57c4-ad46-e31a99c2a64d": "第七章 报批报建管理 > 7.3报批报建经济指标策划",
    "c89537fc-b132-5696-ab4e-721e09e117ef": "第七章 报批报建管理 > 7.4报批报建管理",
    "8ace032b-fe91-51f2-a424-7bbcc9a68bdd": "一、项目设计管理检查情况 > 具体排名",
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def row_is_header(row: dict) -> bool:
    cells = [cell for cell in row.get("cells") or [] if str(cell.get("header") or "").strip()]
    return bool(cells) and all(str(cell.get("value") or "").strip() == str(cell.get("header") or "").strip() for cell in cells)


def main() -> int:
    docs = {str(row.get("document_id")): row for row in read(DOCS)}
    sections = {str(row.get("section_id")): row for row in read(SECTIONS)}
    tables = {str(row.get("table_id")): row for row in read(TABLES)}
    rows = read(ROWS)
    existing = [row for row in (read(GOLD) if GOLD.exists() else []) if not str(row.get("question_id", "")).startswith("V23-S")]
    candidates = []
    for index, table_id in enumerate(SELECTED, start=1):
        table_rows = [row for row in rows if str(row.get("table_id")) == table_id]
        if not table_rows:
            raise ValueError(f"missing table rows: {table_id}")
        first = table_rows[0]
        doc = docs[str(first.get("document_id"))]
        table = tables.get(table_id, {})
        section = SECTION_OVERRIDES.get(table_id) or str((sections.get(str(first.get("section_id"))) or {}).get("heading_path") or "")
        data_row = next((row for row in table_rows if not row_is_header(row)), first)
        fields = []
        for cell in first.get("cells") or []:
            header = str(cell.get("header") or "").strip()
            if header and header not in fields:
                fields.append(header)
        sample = " | ".join(f"{cell.get('header')}：{cell.get('value')}" for cell in data_row.get("cells") or [] if str(cell.get("header") or "").strip())[:1200]
        location = table.get("source_location") or {}
        locator = {"table_id": table_id, "source_location": location, "fields": fields}
        candidates.append({
            "question_id": f"V23-S{index:03d}",
            "question": f"《{doc.get('file_name')}》在“{section}”的表格中，每行包含哪些字段？这些字段分别用于记录什么管理信息？",
            "acceptable_sources": [],
            "acceptable_sections": [],
            "unacceptable_sources": [],
            "candidate_source": {
                "files": [doc.get("file_name")],
                "path": doc.get("source_path"),
                "section": section,
                "table": locator,
                "source": "TABLE_SCHEMA_PURPOSE_CANDIDATE",
            },
            "review_candidates": [{"chunk_id": None, "file_name": doc.get("file_name"), "section_path": section, "snippet": f"字段：{' | '.join(fields)}\n样例行：{sample}"}],
            "business_domain": "设计管理",
            "question_type": "TABLE_SCHEMA_PURPOSE",
            "verification_status": "PENDING_HUMAN_CONFIRM",
            "verified_by": None,
            "verified_at": None,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        })
    combined = existing + candidates
    GOLD.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined), encoding="utf-8")
    print(json.dumps({"new_count": len(candidates), "new_ids": [row["question_id"] for row in candidates], "total": len(combined)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
