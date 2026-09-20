from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_search import query_terms
from app.retrieval.query_planner_v1 import plan_query


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REPLAY = V26 / "v2_6_2_compatibility_replay.json"
REVIEW_ROOT = Path("D:/") / "工作" / "二公司技术部" / "2026" / "设计复盘"
OUT = V26 / "v2_6_2_missing_content_source_proposal.json"
TARGET_NAMES = {
    "公司复盘EPC项目管理台账.xlsx",
    "EPC设计管理复盘总结（光谷能源站).docx",
    "EPC设计管理经验总结(华师南湖训练馆).docx",
    "EPC设计管理经验总结(常熟药机厂项目).docx",
    "EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx",
    "EPC设计管理经验总结(河北科技师范学院项目) .docx",
    "EPC设计管理经验总结(泸州垃圾焚烧发电厂项目)20260309.docx",
    "EPC设计管理经验总结(涟水第三水厂建设项目3.17).docx",
    "EPC设计管理经验总结(葛店新华中学项目).docx",
    "EPC设计管理经验总结（光谷实验中学）.docx",
    "EPC设计管理经验总结（高平二期）(5).docx",
    "河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    questions = [row for row in replay["records"] if row.get("current_bundle_status") == "INSUFFICIENT_EVIDENCE"]
    paths = [path for path in REVIEW_ROOT.iterdir() if path.suffix.casefold() in {".docx", ".pptx", ".xlsx", ".pdf"}]
    built = DocumentIntelligenceV2Builder(REVIEW_ROOT).build(paths)
    docs = {str(row["document_id"]): row for row in built["documents"]}
    records: list[dict] = []
    for row in built["paragraphs"]:
        records.append({"document_id": row["document_id"], "kind": "paragraph", "evidence_id": row.get("paragraph_id"), "text": str(row.get("text") or ""), "location": {"paragraph_id": row.get("paragraph_id"), "section_id": row.get("section_id")}})
    for row in built["table_rows"]:
        values = row.get("values") or row.get("cells") or []
        text = " | ".join(str(value.get("value") if isinstance(value, dict) else value) for value in values)
        records.append({"document_id": row["document_id"], "kind": "table_row", "evidence_id": row.get("table_row_id") or row.get("row_id"), "text": text, "location": {"table_id": row.get("table_id"), "row_number": row.get("row_number")}})
    matched: dict[str, dict] = {}
    for question in questions:
        terms = [term.casefold() for term in query_terms(question["question"]) if len(term) >= 2 and term not in {"项目", "多少", "累计", "分别", "各", "台账", "统计", "设计", "价值", "创造", "策划点", "条", "项", "共列", "几个", "专业", "一共", "合计", "情况", "阶段", "的", "中", "和", "方面"}]
        project_values = [str(value) for value in plan_query(question["question"]).project if str(value).strip() and not any(marker in str(value) for marker in ("哪", "多少", "又名", "又称", "未编制"))]
        project_terms = [term.casefold() for term in query_terms(" ".join(project_values)) if len(term) >= 2 and term not in {"项目", "多少", "分别", "各", "哪几个", "哪几家"}]
        hits = []
        for record in records:
            compact = re.sub(r"\s+", "", record["text"]).casefold()
            score = sum(term in compact for term in terms)
            project_score = sum(term in compact for term in project_terms)
            if project_terms and project_score < min(2, len(project_terms)):
                continue
            if score < max(4, min(6, len(terms))) or not re.search(r"\d", compact):
                continue
            hits.append((score, record))
        for score, record in sorted(hits, key=lambda item: (-item[0], len(item[1]["text"])))[:4]:
            document = docs[record["document_id"]]
            path = str(document["source_path"])
            item = matched.setdefault(path, {"file_name": document["file_name"], "source_path": path, "sha256": sha256(Path(path)), "physical_exists": Path(path).is_file(), "question_hashes": set(), "evidence": []})
            item["question_hashes"].add(str(question["question_hash"]))
            item["evidence"].append({"question": question["question"], "score": score, "kind": record["kind"], "evidence_id": record["evidence_id"], "location": record["location"], "excerpt": record["text"][:700]})
    relevant_markers = ("策划项", "创效", "图纸审查意见", "完整度", "概算复核", "对标项目", "设计院")
    for document in docs.values():
        path = str(document["source_path"])
        if path in matched or document["file_name"] not in TARGET_NAMES:
            continue
        evidence = [record for record in records if record["document_id"] == document["document_id"] and len(record["text"]) >= 40 and any(marker in record["text"] for marker in relevant_markers)]
        if not evidence:
            continue
        matched[path] = {"file_name": document["file_name"], "source_path": path, "sha256": sha256(Path(path)), "physical_exists": Path(path).is_file(), "question_hashes": set(), "evidence": [{"question": "未绑定题目；待来源准入后重跑全量映射", "score": 0, "kind": record["kind"], "evidence_id": record["evidence_id"], "location": record["location"], "excerpt": record["text"][:700]} for record in evidence[:4]]}
    output_records = []
    for item in sorted(matched.values(), key=lambda value: (-len(value["question_hashes"]), value["file_name"])):
        item["question_hashes"] = sorted(item["question_hashes"])
        item["question_count"] = len(item["question_hashes"])
        item["approval_status"] = "PENDING_OWNER_APPROVAL"
        item["approval_scope"] = "V2.6.2 missing-content source remediation only"
        output_records.append(item)
    payload = {
        "schema_version": "knowledge_os_v2_6_2.missing_content_source_proposal",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": json.loads((V26 / "remediation_candidate_v2_6_2.json").read_text(encoding="utf-8"))["candidate_hash"],
        "current_insufficient_question_count": len(questions),
        "source_count": len(output_records),
        "approval_status": "PENDING_OWNER_APPROVAL",
        "records": output_records,
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "note": "Read-only parse of physical design-review files; no source or runtime write performed.",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_count": len(output_records), "question_count": len(questions), "out": str(OUT), "formal_8000_touched": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
