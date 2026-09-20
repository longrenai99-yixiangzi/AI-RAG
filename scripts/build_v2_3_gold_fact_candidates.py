from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    docs = {str(row.get("document_id")): row for row in read(STAGING / "documents.jsonl")}
    sections = {str(row.get("section_id")): row for row in read(STAGING / "sections.jsonl")}
    existing = read(GOLD) if GOLD.exists() else []
    used = {str(row.get("question_id")) for row in existing}
    blocked = ("经验", "复盘", "技术管理", "科技管理", "深化设计", "BIM", "项目经验")
    fields = ("项目", "项目名称", "单位", "责任人", "专业", "完成时限", "数量", "金额", "工作任务", "设计阶段")
    candidates = []
    seen_table_fields: set[tuple[str, str, str]] = set()
    for row in read(ROOT / "data" / "shadow" / "document_intelligence_v2" / "table_rows.jsonl"):
        doc = docs.get(str(row.get("document_id")), {})
        source_path = str(doc.get("source_path") or "")
        file_name = str(doc.get("file_name") or "")
        section = sections.get(str(row.get("section_id")), {})
        section_path = str(section.get("section_path") or section.get("heading") or "")
        if any(term.casefold() in f"{source_path} {section_path}".casefold() for term in blocked):
            continue
        cells = row.get("cells") or []
        useful = [cell for cell in cells if str(cell.get("value") or "").strip()]
        if len(useful) < 2:
            continue
        header = next((str(cell.get("header") or "") for cell in useful if any(term in str(cell.get("header") or "") for term in fields)), "")
        if not header:
            continue
        table_key = (file_name.casefold(), section_path.casefold(), header.casefold())
        if table_key in seen_table_fields:
            continue
        seen_table_fields.add(table_key)
        value = next((str(cell.get("value") or "") for cell in useful if str(cell.get("header") or "") == header), "")
        if not value:
            continue
        candidate_id = f"V23-T{len(candidates) + 1:03d}"
        candidates.append({"question_id": candidate_id, "question": f"《{file_name}》在“{section_path}”表格第{row.get('row_number')}行的“{header}”字段值是什么？", "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"files": [file_name], "path": source_path, "section": section_path, "row": row.get("row_number"), "topic": "STRUCTURED_FACT", "source": "TABLE_ROW_REPLACEMENT_CANDIDATE"}, "review_candidates": [{"chunk_id": None, "file_name": file_name, "section_path": section_path, "snippet": " | ".join(f"{cell.get('header')}：{cell.get('value')}" for cell in useful)[:800]}], "business_domain": "设计管理", "question_type": "STRUCTURED_FACT", "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None, "created_at": datetime.now(timezone.utc).astimezone().isoformat()})
        if len(candidates) >= 16:
            break
    existing_ids = {str(row.get("question_id")) for row in existing}
    combined = existing + [row for row in candidates if row["question_id"] not in existing_ids and row["question_id"] not in used]
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined), encoding="utf-8")
    print(json.dumps({"new_count": len(candidates), "new_ids": [row["question_id"] for row in candidates], "total": len(combined), "output": str(GOLD)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
