from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl"
TABLES = ROOT / "data" / "shadow" / "document_intelligence_v2" / "tables.jsonl"
ROWS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "table_rows.jsonl"
OUT = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "answer_gold_candidates.jsonl"
SHEET = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "answer_gold_review_sheet.md"

CASES = [
    ("99c85c49-6e6e-52c3-a352-065732aff65f", 2, "名称=项目名称这一行的内容是什么？", ["名称", "内容"], "第一章 项目概况 > 1.1 工程概况"),
    ("99c85c49-6e6e-52c3-a352-065732aff65f", 3, "名称=建设地点这一行的内容是什么？", ["名称", "内容"], "第一章 项目概况 > 1.1 工程概况"),
    ("99c85c49-6e6e-52c3-a352-065732aff65f", 4, "名称=工程总承包模式这一行的内容是什么？", ["名称", "内容"], "第一章 项目概况 > 1.1 工程概况"),
    ("99c85c49-6e6e-52c3-a352-065732aff65f", 5, "名称=建设单位这一行的内容是什么？", ["名称", "内容"], "第一章 项目概况 > 1.1 工程概况"),
    ("fa01092e-f9ed-5282-aaed-4c39b84b375c", 2, "需求方=建设单位这一行的需求要点分析是什么？", ["需求方", "需求要点分析"], "第一章 项目概况 > 1.2需求分析"),
    ("bf791961-10bf-52c5-a380-5c18bfa22e16", 2, "类别=可研报告这一行的进展是什么？", ["类别", "进展"], "第一章 项目概况 > 1.3 设计现状"),
    ("bc1dcf17-42b5-50ac-9b6f-e4e30a3be0c2", 2, "序号=1这一行的设计阶段、工作名称和预计完成时间是什么？", ["序号", "设计阶段", "工作名称", "预计完成时间"], "第二章 设计策划目标 > 2.1设计进度目标 > 2.1.3设计里程碑节点"),
    ("bc1dcf17-42b5-50ac-9b6f-e4e30a3be0c2", 6, "序号=5这一行的设计阶段、工作名称和预计完成时间是什么？", ["序号", "设计阶段", "工作名称", "预计完成时间"], "第二章 设计策划目标 > 2.1设计进度目标 > 2.1.3设计里程碑节点"),
    ("bc1dcf17-42b5-50ac-9b6f-e4e30a3be0c2", 10, "序号=9这一行的设计阶段、工作名称和预计完成时间是什么？", ["序号", "设计阶段", "工作名称", "预计完成时间"], "第二章 设计策划目标 > 2.1设计进度目标 > 2.1.3设计里程碑节点"),
    ("2d9c5e68-b783-52d6-88c5-6b0638e64c7b", 2, "阶段=设计管理策划这一行的工作事项、工作界面和成果文件是什么？", ["阶段", "工作事项", "工作界面", "成果文件"], "第三章 设计组织策划 > 3.2 设计管理相关方权责分配"),
    ("abb5afc0-e3c8-5189-8189-810f67464cae", 2, "序号=1这一行的设计合约包、合约范围和招采方式是什么？", ["序号", "设计合约包", "合约范围", "招采方式"], "第四章 设计合约规划"),
    ("d8569497-50f1-5444-8d96-08f6259bb262", 2, "报批报建阶段=可研这一行的办事部门和主要事项是什么？", ["报批报建阶段", "办事部门", "主要事项"], "第七章 报批报建管理 > 7.2报批报建主要事项"),
    ("d8569497-50f1-5444-8d96-08f6259bb262", 7, "报批报建阶段=初步设计这一行的办事部门和主要事项是什么？", ["报批报建阶段", "办事部门", "主要事项"], "第七章 报批报建管理 > 7.2报批报建主要事项"),
    ("cd5be857-c87f-57c4-ad46-e31a99c2a64d", 2, "报批报建指标=海绵城市这一行的经济指标策划思路是什么？", ["报批报建指标", "经济指标策划思路"], "第七章 报批报建管理 > 7.3报批报建经济指标策划"),
    ("c89537fc-b132-5696-ab4e-721e09e117ef", 2, "事项=提前介入监督手续办理这一行的关注重点是什么？", ["事项", "关注重点"], "第七章 报批报建管理 > 7.4报批报建管理"),
    ("a3db66ea-8221-55ab-827b-5016018c9e8a", 2, "指标名称=景观工程这一行的指标类型和控制目标是什么？", ["指标名称", "指标类型", "控制目标"], "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.1 主要建设标准"),
    ("c4742ef4-cb0a-59e1-8a2f-0dfeda0de9d0", 2, "复核内容=结构 指标这一行的适用指标、单位和指标范围是什么？", ["复核内容", "适用指标", "单位", "指标范围 （依据对标项标准提取）"], "第二章 设计策划目标 > 2.4设计限额目标 > 2.4.2 含量指标要求"),
    ("c38e35bd-c77a-550a-a31a-040c26b771c4", 4, "序号=1这一行的具体事宜、需完成时间、分公司责任部门/人和项目责任人是什么？", ["序号", "具体事宜", "需完成时间", "分公司责任部门/人", "项目责任人"], "Sheet1"),
    ("c38e35bd-c77a-550a-a31a-040c26b771c4", 5, "序号=2这一行的具体事宜、需完成时间、分公司责任部门/人和项目责任人是什么？", ["序号", "具体事宜", "需完成时间", "分公司责任部门/人", "项目责任人"], "Sheet1"),
    ("8ace032b-fe91-51f2-a424-7bbcc9a68bdd", 2, "排名=1这一行的项目名称、分公司和综合得分是什么？", ["排名", "项目名称", "分公司", "综合得分"], "一、项目设计管理检查情况 > 具体排名"),
    ("d88b1eec-ba10-5c43-ba3d-590a4d4f38c3", 4, "序号=1这一行的专业类别、比选项目、比选结果和比选阶段是什么？", ["序号", "专业类别", "比选项目", "比选结果", "比选阶段"], "Sheet1"),
    ("d88b1eec-ba10-5c43-ba3d-590a4d4f38c3", 5, "序号=2这一行的专业类别、比选项目、比选结果和比选阶段是什么？", ["序号", "专业类别", "比选项目", "比选结果", "比选阶段"], "Sheet1"),
]


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    docs = {str(row.get("document_id")): row for row in read(DOCS)}
    tables = {str(row.get("table_id")): row for row in read(TABLES)}
    rows = read(ROWS)
    existing = [row for row in (read(OUT) if OUT.exists() else []) if not str(row.get("question_id", "")).startswith("V23-A")]
    candidates = []
    sheet_lines = ["# Answer Gold 审核清单", "", "> 这些是候选，不代表已确认。请逐条核对问题、答案和证据位置。", ""]
    for index, (table_id, row_number, question, claim_headers, section) in enumerate(CASES, start=1):
        source_row = next((row for row in rows if str(row.get("table_id")) == table_id and int(row.get("row_number") or 0) == row_number), None)
        if source_row is None:
            raise ValueError(f"missing source row: {table_id}:{row_number}")
        doc = docs[str(source_row.get("document_id"))]
        table = tables.get(table_id, {})
        cells = {str(cell.get("header") or ""): cell.get("value") for cell in source_row.get("cells") or []}
        claims = [f"{header}：{cells.get(header, '')}" for header in claim_headers]
        evidence_text = " | ".join(f"{cell.get('header')}：{cell.get('value')}" for cell in source_row.get("cells") or [] if str(cell.get("header") or "").strip())
        qid = f"V23-A{index:03d}"
        candidate = {
            "question_id": qid,
            "question": f"《{doc.get('file_name')}》在“{section}”中，{question}",
            "expected_claims": claims,
            "required_evidence": [{"source_path": doc.get("source_path"), "file_name": doc.get("file_name"), "section": section, "table_id": table_id, "row": row_number, "source_location": table.get("source_location") or {}}],
            "acceptable_answer_boundary": "仅限该表该行原文字段及其可直接对应的内容，不扩展推断",
            "candidate_evidence": evidence_text[:1800],
            "verification_status": "PENDING_HUMAN_CONFIRM",
            "verified_by": None,
            "verified_at": None,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }
        candidates.append(candidate)
        sheet_lines.extend([f"## {qid}", f"**问题**：{candidate['question']}", f"**候选答案字段**：{'；'.join(claims)}", f"**证据位置**：{doc.get('source_path')} · {section} · 第{row_number}行", ""])
    combined = existing + candidates
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined), encoding="utf-8")
    SHEET.write_text("\n".join(sheet_lines) + "\n", encoding="utf-8")
    print(json.dumps({"new_count": len(candidates), "new_ids": [row["question_id"] for row in candidates], "existing_confirmed_target": 8, "answer_target": 30, "review_sheet": str(SHEET)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
