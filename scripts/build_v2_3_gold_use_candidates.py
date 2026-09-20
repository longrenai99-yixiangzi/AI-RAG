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
    "d88b1eec-ba10-5c43-ba3d-590a4d4f38c3",
    "c4742ef4-cb0a-59e1-8a2f-0dfeda0de9d0",
    "a3db66ea-8221-55ab-827b-5016018c9e8a",
    "4b86e3b4-bbf9-549e-955b-041bb915d281",
    "c664d308-730f-5be9-b059-fb1562c2da79",
    "cf1c8a3a-b7c0-5fc8-a362-64f6b50635ba",
    "f2e05970-b38f-5e02-838b-e15f418aaaa6",
    "28bf8845-4b5b-50dc-ab49-f53e33218a56",
    "1fef9d4a-1349-50bc-911a-85a9d71d43a0",
    "2d528e60-7641-5d1d-a68b-7a1e5bcf1f55",
]

SECTION_OVERRIDES = {
    "d88b1eec-ba10-5c43-ba3d-590a4d4f38c3": "设计方案比选提示清单7.23.xlsx > Sheet1",
    "c4742ef4-cb0a-59e1-8a2f-0dfeda0de9d0": "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.2 含量指标要求",
    "a3db66ea-8221-55ab-827b-5016018c9e8a": "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.1 主要建设标准",
    "4b86e3b4-bbf9-549e-955b-041bb915d281": "4、二季度EPC项目设计管理检查情况通报.pptx > 检查组织",
    "c664d308-730f-5be9-b059-fb1562c2da79": "公司体育场馆产品线设计创效案例汇编模板 > 案例对比",
    "cf1c8a3a-b7c0-5fc8-a362-64f6b50635ba": "公司体育场馆产品线设计创效案例汇编模板 > 钢筋用量对比",
    "f2e05970-b38f-5e02-838b-e15f418aaaa6": "公司学校产品线设计创效案例汇编模板 > 材料方案对比",
    "28bf8845-4b5b-50dc-ab49-f53e33218a56": "公司体育场馆产品线设计创效案例汇编模板 > 管材方案对比",
    "1fef9d4a-1349-50bc-911a-85a9d71d43a0": "公司体育场馆产品线设计创效案例汇编模板 > 回填材料分析",
    "2d528e60-7641-5d1d-a68b-7a1e5bcf1f55": "公司体育场馆产品线设计创效案例汇编模板 > 罐体方案对比",
}

QUESTION_TEMPLATES = {
    "d88b1eec-ba10-5c43-ba3d-590a4d4f38c3": "这张方案比选提示清单如何用字段记录专业、比选对象、实施性、经济性、结果和阶段，从而支撑方案比选复核？",
    "c4742ef4-cb0a-59e1-8a2f-0dfeda0de9d0": "这张含量指标要求表如何用字段把复核内容、适用指标、单位和指标范围串起来，支撑指标复核？",
    "a3db66ea-8221-55ab-827b-5016018c9e8a": "这张主要建设标准表中的指标名称、指标类型和控制目标分别承担什么管理作用？",
    "4b86e3b4-bbf9-549e-955b-041bb915d281": "这张检查组织表如何用检查人员、分公司、项目数和检查形式记录检查覆盖情况？",
    "c664d308-730f-5be9-b059-fb1562c2da79": "这张创效案例表中的原方案和现方案分别用于记录什么，如何支撑前后方案对比？",
    "cf1c8a3a-b7c0-5fc8-a362-64f6b50635ba": "这张钢筋用量对比表中的场馆、方案用量和节约量字段分别用于什么判断，如何支撑创效核算？",
    "f2e05970-b38f-5e02-838b-e15f418aaaa6": "这张材料方案对比表如何用材料名称及各方案字段记录比选对象，支撑创效案例复核？",
    "28bf8845-4b5b-50dc-ab49-f53e33218a56": "这张管材方案对比表如何用字段记录不同材料方案，支撑方案替代关系核对？",
    "1fef9d4a-1349-50bc-911a-85a9d71d43a0": "这张回填材料分析表中的材料、综合单价和综合分析分别用于什么管理判断？",
    "2d528e60-7641-5d1d-a68b-7a1e5bcf1f55": "这张罐体方案对比表如何用字段记录两种方案，支撑方案比选结果复核？",
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
    existing = [row for row in (read(GOLD) if GOLD.exists() else []) if not str(row.get("question_id", "")).startswith("V23-U")]
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
        candidates.append({
            "question_id": f"V23-U{index:03d}",
            "question": f"《{doc.get('file_name')}》在“{section}”中，{QUESTION_TEMPLATES[table_id]}",
            "acceptable_sources": [],
            "acceptable_sections": [],
            "unacceptable_sources": [],
            "candidate_source": {
                "files": [doc.get("file_name")],
                "path": doc.get("source_path"),
                "section": section,
                "table": {"table_id": table_id, "source_location": table.get("source_location") or {}, "fields": fields},
                "source": "TABLE_USE_CANDIDATE",
            },
            "review_candidates": [{"chunk_id": None, "file_name": doc.get("file_name"), "section_path": section, "snippet": f"字段：{' | '.join(fields)}\n样例行：{sample}"}],
            "business_domain": "设计管理",
            "question_type": "TABLE_USE",
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
