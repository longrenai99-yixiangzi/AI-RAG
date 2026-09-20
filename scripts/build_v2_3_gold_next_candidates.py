from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def question_for(heading: str) -> str | None:
    if any(term in heading for term in ("职责", "责任", "组织结构")):
        return f"“{heading}”的责任边界是什么？"
    if "接口" in heading:
        return f"“{heading}”规定的接口对象和交付边界是什么？"
    if any(term in heading for term in ("流程", "审批", "归档", "版本")):
        return f"“{heading}”规定的关键流程节点是什么？"
    if any(term in heading for term in ("字段", "清单", "台账", "表单")):
        return f"“{heading}”要求记录哪些字段或事项？"
    if any(term in heading for term in ("交付", "成果", "检查点")):
        return f"“{heading}”的交付或检查要求是什么？"
    return None


def main() -> int:
    docs = {str(row.get("document_id")): row for row in rows(STAGING / "documents.jsonl")}
    sections = rows(STAGING / "sections.jsonl")
    chunks = rows(STAGING / "semantic_chunks.jsonl")
    existing = rows(GOLD) if GOLD.exists() else []
    existing_ids = {str(row.get("question_id")) for row in existing}
    candidates: list[dict] = []
    excluded = ("项目经验", "经验总结", "复盘", "BIM", "技术管理", "科技管理", "深化设计")
    allowed = ("00_AI系统", "raw\\设计管理体系", "raw\\设计支持", "wiki\\concepts", "02_正式知识", "04_规则库", "05_模板库", "templates")
    seen_questions: set[str] = set()
    for section in sorted(sections, key=lambda row: (str(row.get("section_path") or ""), str(row.get("section_id") or ""))):
        doc = docs.get(str(section.get("document_id")), {})
        source_path = str(doc.get("source_path") or "")
        heading = str(section.get("section_path") or "")
        if not heading or heading in {"Document Body", "关联内容"} or any(term in source_path or term in heading for term in excluded):
            continue
        if allowed and not any(term.casefold() in source_path.casefold() for term in allowed):
            continue
        question = question_for(heading)
        if not question or question in seen_questions:
            continue
        seen_questions.add(question)
        section_id = str(section.get("section_id"))
        snippets = [{"chunk_id": chunk.get("chunk_id"), "file_name": doc.get("file_name"), "section_path": chunk.get("section_path"), "snippet": str(chunk.get("raw_text") or "")[:800]} for chunk in chunks if str(chunk.get("section_id")) == section_id][:3]
        candidate_id = f"V23-R{len(candidates) + 1:03d}"
        candidates.append({"question_id": candidate_id, "question": question, "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"files": [doc.get("file_name")], "path": source_path, "section": heading, "topic": "制度/模板/设计支持概念", "source": "STRUCTURED_SECTION_CANDIDATE"}, "review_candidates": snippets, "business_domain": "设计管理", "question_type": "SECTION_SPECIFIC_FACT", "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None, "created_at": datetime.now(timezone.utc).astimezone().isoformat()})
        if len(candidates) >= 23:
            break
    combined = existing + [row for row in candidates if row["question_id"] not in existing_ids]
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in combined), encoding="utf-8")
    print(json.dumps({"new_count": len(candidates), "new_ids": [row["question_id"] for row in candidates], "total_replacement_candidates": len(combined), "output": str(GOLD)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
