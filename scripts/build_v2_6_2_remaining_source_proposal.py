from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_search import query_terms
from app.retrieval.query_planner_v1 import plan_query


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
QUEUE = V26 / "v2_6_2_source_gap_queue.json"
REPLAY = V26 / "v2_6_2_compatibility_replay.json"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
OUT = V26 / "v2_6_2_remaining_source_proposal.json"
SUPPORTED = {".md", ".markdown", ".pdf", ".docx", ".xlsx", ".pptx", ".txt"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_file_url(value: str) -> Path | None:
    decoded = unquote(value).replace("%5C", "\\").replace("/", "\\")
    if re.match(r"^[A-Za-z]:\\", decoded):
        return Path(decoded)
    return None


def main() -> int:
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    questions = [row for row in replay["records"] if row.get("current_bundle_status") == "INSUFFICIENT_EVIDENCE"]
    discovered: set[Path] = set()
    for item in queue.get("queue") or []:
        for source in item.get("sources") or []:
            path = Path(str(source.get("source_path") or ""))
            if path.is_file() and path.suffix.casefold() in SUPPORTED:
                discovered.add(path.resolve())
            if path.is_file() and path.suffix.casefold() in {".md", ".markdown"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for url in re.findall(r"file:///([^\s)\]]+)", text):
                    linked = normalize_file_url(url)
                    if linked and linked.is_file() and linked.suffix.casefold() in SUPPORTED:
                        discovered.add(linked.resolve())
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current_paths = {str(Path(str(source.get("source_path") or "")).resolve()).casefold() for source in current.get("sources") or []}
    discovered = {path for path in discovered if str(path).casefold() not in current_paths}
    if not discovered:
        payload = {"schema_version": "knowledge_os_v2_6_2.remaining_source_proposal", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "candidate_hash": current.get("candidate_hash"), "current_insufficient_question_count": len(questions), "source_count": 0, "approval_status": "NO_NEW_PHYSICAL_SOURCE_DISCOVERED", "records": [], "formal_8000_touched": False}
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"source_count": 0, "question_count": len(questions), "out": str(OUT)}, ensure_ascii=False, indent=2))
        return 0
    roots = sorted({path.parent for path in discovered}, key=str)
    bundles = []
    for root in roots:
        paths = [path for path in discovered if path.parent == root]
        bundles.append(DocumentIntelligenceV2Builder(root).build(paths))
    docs = {}
    records = []
    for bundle in bundles:
        docs.update({row["document_id"]: row for row in bundle["documents"]})
        records.extend({"document_id": row["document_id"], "kind": "paragraph", "evidence_id": row.get("paragraph_id"), "text": str(row.get("text") or ""), "location": {"paragraph_id": row.get("paragraph_id"), "section_id": row.get("section_id")}} for row in bundle["paragraphs"])
        for row in bundle["table_rows"]:
            values = row.get("values") or row.get("cells") or []
            records.append({"document_id": row["document_id"], "kind": "table_row", "evidence_id": row.get("table_row_id") or row.get("row_id"), "text": " | ".join(str(value.get("value") if isinstance(value, dict) else value) for value in values), "location": {"table_id": row.get("table_id"), "row_number": row.get("row_number")}})
    grouped: dict[str, dict] = {}
    for question in questions:
        terms = [term.casefold() for term in query_terms(question["question"]) if len(term) >= 2 and term not in {"项目", "多少", "累计", "分别", "各", "台账", "统计", "设计", "价值", "创造", "策划点", "条", "项", "共列", "几个", "专业", "一共", "合计", "情况", "阶段", "的", "中", "和", "方面"}]
        hits = []
        for record in records:
            compact = re.sub(r"\s+", "", record["text"]).casefold()
            score = sum(term in compact for term in terms)
            if score >= max(4, min(6, len(terms))) and re.search(r"\d", compact):
                hits.append((score, record))
        for score, record in sorted(hits, key=lambda item: (-item[0], len(item[1]["text"])))[:5]:
            document = docs[record["document_id"]]
            path = Path(str(document["source_path"])).resolve()
            item = grouped.setdefault(str(path).casefold(), {"file_name": document["file_name"], "source_path": str(path), "sha256": sha256(path), "physical_exists": path.is_file(), "question_hashes": set(), "evidence": []})
            item["question_hashes"].add(str(question["question_hash"]))
            item["evidence"].append({"question": question["question"], "score": score, "kind": record["kind"], "evidence_id": record["evidence_id"], "location": record["location"], "excerpt": record["text"][:700]})
    for path in sorted(discovered, key=str):
        key = str(path).casefold()
        if key in grouped:
            continue
        grouped[key] = {"file_name": path.name, "source_path": str(path), "sha256": sha256(path), "physical_exists": path.is_file(), "question_hashes": set(), "evidence": [], "note": "Physical source discovered from a current gap reference; no safe question-to-body match was asserted."}
    output = []
    for item in sorted(grouped.values(), key=lambda value: (-len(value["question_hashes"]), value["file_name"])):
        item["question_hashes"] = sorted(item["question_hashes"])
        item["question_count"] = len(item["question_hashes"])
        item["approval_status"] = "PENDING_OWNER_APPROVAL"
        item["approval_scope"] = "V2.6.2 missing-content source remediation only"
        output.append(item)
    payload = {"schema_version": "knowledge_os_v2_6_2.remaining_source_proposal", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "candidate_hash": current.get("candidate_hash"), "current_insufficient_question_count": len(questions), "discovered_physical_source_count": len(discovered), "source_count": len(output), "approval_status": "PENDING_OWNER_APPROVAL", "records": output, "formal_8000_touched": False, "8010_switch_authorized": False, "note": "Read-only discovery and parse from current source-gap queue; no candidate/runtime write performed."}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_count": len(output), "discovered_physical_source_count": len(discovered), "question_count": len(questions), "out": str(OUT), "formal_8000_touched": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
