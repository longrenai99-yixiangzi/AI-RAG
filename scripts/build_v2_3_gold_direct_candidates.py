from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl"
ROWS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "table_rows.jsonl"
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"

CASES = [
    ("c38e35bd-c77a-550a-a31a-040c26b771c4", "督办清单第4行（序号=1）的具体事宜、需完成时间、分公司责任部门/人和项目责任人分别是什么？", "Sheet1", 4, "序号", "1"),
    ("7ab3b5e7-2f42-5aca-b47f-aeeea8765d36", "“溧阳长山新天地合作开发项目”这一行的设计单位、项目设计总监、设计经理、主体工程设计进展和超概风险分别是什么？", "二公司设计阶段EPC项目清单", 4, "项目名称", "溧阳长山新天地合作开发项目"),
    ("8ace032b-fe91-51f2-a424-7bbcc9a68bdd", "排名=1的项目名称、分公司和综合得分分别是什么？", "一、项目设计管理检查情况 > 具体排名", 2, "排名", "1"),
    ("99c85c49-6e6e-52c3-a352-065732aff65f", "工程概况表中“名称=项目名称”这一行的内容是什么？", "第一章 项目概况 > 1.1 工程概况", 2, "名称", "项目名称"),
    ("d8569497-50f1-5444-8d96-08f6259bb262", "“报批报建阶段=可研”这一行的办事部门和主要事项是什么？", "第七章 报批报建管理 > 7.2报批报建主要事项", 2, "报批报建阶段", "可研"),
    ("cd5be857-c87f-57c4-ad46-e31a99c2a64d", "“报批报建指标=海绵城市”这一行的经济指标策划思路是什么？", "第七章 报批报建管理 > 7.3报批报建经济指标策划", 2, "报批报建指标", "海绵城市"),
    ("c89537fc-b132-5696-ab4e-721e09e117ef", "“事项=提前介入监督手续办理”这一行的关注重点是什么？", "第七章 报批报建管理 > 7.4报批报建管理", 2, "事项", "提前介入监督手续办理"),
    ("a3db66ea-8221-55ab-827b-5016018c9e8a", "“指标名称=景观工程”这一行的指标类型和控制目标是什么？", "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.1 主要建设标准", 2, "指标名称", "景观工程"),
    ("d88b1eec-ba10-5c43-ba3d-590a4d4f38c3", "“序号=1”这一行的专业类别、比选项目、比选结果和比选阶段分别是什么？", "Sheet1", 4, "序号", "1"),
    ("c4742ef4-cb0a-59e1-8a2f-0dfeda0de9d0", "含量指标要求表第2行“复核内容=结构 指标”的适用指标、单位和指标范围是什么？", "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.2 含量指标要求", 2, "复核内容", "结构 指标"),
]


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    docs = {str(row.get("document_id")): row for row in read(DOCS)}
    rows = read(ROWS)
    existing = [row for row in (read(GOLD) if GOLD.exists() else []) if not str(row.get("question_id", "")).startswith("V23-D")]
    candidates = []
    for index, (table_id, question, section, row_number, key_header, key_value) in enumerate(CASES, start=1):
        table_rows = [row for row in rows if str(row.get("table_id")) == table_id]
        source_row = next((row for row in table_rows if int(row.get("row_number") or 0) == row_number), None)
        if source_row is None:
            raise ValueError(f"missing row {table_id}:{row_number}")
        doc = docs[str(source_row.get("document_id"))]
        fields = []
        for cell in source_row.get("cells") or []:
            header = str(cell.get("header") or "").strip()
            if header and header not in fields:
                fields.append(header)
        snippet = " | ".join(f"{cell.get('header')}：{cell.get('value')}" for cell in source_row.get("cells") or [] if str(cell.get("header") or "").strip())[:1600]
        candidates.append({
            "question_id": f"V23-D{index:03d}",
            "question": f"《{doc.get('file_name')}》在“{section}”中，{question}",
            "acceptable_sources": [],
            "acceptable_sections": [],
            "unacceptable_sources": [],
            "candidate_source": {
                "files": [doc.get("file_name")],
                "path": doc.get("source_path"),
                "section": section,
                "table": {"table_id": table_id, "row": row_number, "row_key": {"header": key_header, "value": key_value}, "fields": fields},
                "source": "DIRECT_ROW_FACT_CANDIDATE",
            },
            "review_candidates": [{"chunk_id": None, "file_name": doc.get("file_name"), "section_path": section, "snippet": snippet}],
            "business_domain": "设计管理",
            "question_type": "DIRECT_ROW_FACT",
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
