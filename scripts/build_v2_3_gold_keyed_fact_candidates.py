from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl"
SECTIONS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "sections.jsonl"
TABLE_ROWS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "table_rows.jsonl"
TABLES = ROOT / "data" / "shadow" / "document_intelligence_v2" / "tables.jsonl"
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    docs = {str(row.get("document_id")): row for row in read(DOCS)}
    sections = {str(row.get("section_id")): row for row in read(SECTIONS)}
    table_indexes = {str(row.get("table_id")): int((row.get("source_location") or {}).get("table") or 0) for row in read(TABLES)}
    existing = read(GOLD) if GOLD.exists() else []
    existing_ids = {str(row.get("question_id")) for row in existing}
    blocked = ("经验", "复盘", "技术管理", "科技管理", "深化设计", "BIM", "项目经验")
    key_headers = ("项目名称", "项目", "单位", "专业", "序号", "工作任务")
    target_headers = ("责任人", "完成时限", "工作任务", "专业", "数量", "金额", "设计阶段", "监督人")
    candidates: list[dict] = []
    seen: set[tuple[str, str, int, str]] = set()
    for row in read(TABLE_ROWS):
        doc = docs.get(str(row.get("document_id")), {})
        section = sections.get(str(row.get("section_id")), {})
        path = str(doc.get("source_path") or "")
        heading = str(section.get("section_path") or section.get("heading") or "")
        table_index = table_indexes.get(str(row.get("table_id")), 0)
        if file_name := str(doc.get("file_name") or ""):
            if file_name == "扬州十里外滩项目设计策划书2024.6.16(1).docx" and table_index == 5:
                heading = "第二章 设计策划目标 > 2.1设计进度目标 > 2.1.3设计里程碑节点"
        if any(term.casefold() in f"{path} {heading}".casefold() for term in blocked):
            continue
        cells = [cell for cell in (row.get("cells") or []) if str(cell.get("value") or "").strip()]
        identity = next((cell for cell in cells if str(cell.get("header") or "") in key_headers), None)
        target = next((cell for cell in cells if str(cell.get("header") or "") in target_headers and cell is not identity), None)
        if not identity or not target:
            continue
        if str(identity.get("value") or "").strip() == str(identity.get("header") or "").strip():
            continue
        file_name = str(doc.get("file_name") or "")
        row_number = int(row.get("row_number") or 0)
        target_header = str(target.get("header") or "")
        key = (file_name.casefold(), heading.casefold(), row_number, target_header.casefold())
        if key in seen:
            continue
        seen.add(key)
        qid = f"V23-G{len(candidates) + 1:03d}"
        row_text = " | ".join(f"{cell.get('header')}：{cell.get('value')}" for cell in cells)
        candidates.append({"question_id": qid, "question": f"《{file_name}》在“{heading}”表格第{row_number}行（{identity.get('header')}={identity.get('value')}）的“{target_header}”字段值是什么？", "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"files": [file_name], "path": path, "section": heading, "row": row_number, "row_key": {"header": identity.get("header"), "value": identity.get("value")}, "target_field": target_header, "source": "KEYED_TABLE_FACT_CANDIDATE"}, "review_candidates": [{"chunk_id": None, "file_name": file_name, "section_path": heading, "snippet": row_text[:800]}], "business_domain": "设计管理", "question_type": "KEYED_TABLE_FACT", "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None, "created_at": datetime.now(timezone.utc).astimezone().isoformat()})
        if len(candidates) >= 16:
            break
    existing_ids.update(str(row.get("question_id")) for row in candidates)
    combined = existing + candidates
    GOLD.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined), encoding="utf-8")
    print(json.dumps({"new_count": len(candidates), "new_ids": [row["question_id"] for row in candidates], "total": len(combined)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
