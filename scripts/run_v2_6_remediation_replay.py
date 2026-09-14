from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.retrieval.query_planner_v1 import plan_query
from app.trial.live_shadow_v25 import V25LiveShadow
from app.verified_answer_engine_v2 import render, validate
from scripts.run_verified_answer_engine_v2 import _runtime_bundle


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REMEDIATION = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _question(review_id: str) -> str:
    review = json.loads((V26 / "live_shadow_manual_review.json").read_text(encoding="utf-8"))
    return next(row["question"] for row in review["records"] if row["review_id"] == review_id)


def _lsr014() -> dict:
    docs = {str(row["document_id"]): row for row in _read_jsonl(REMEDIATION / "documents.jsonl")}
    chunks = _read_jsonl(REMEDIATION / "semantic_chunks.jsonl")
    terms = ("\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a", "2035\u603b\u4f53\u884c\u52a8\u89c4\u5212", "\u4f9d\u62588\u4e2aBIM", "\u5149\u8c37\u5143\u8457")
    rows = []
    for chunk in chunks:
        if not any(term in str(chunk.get("raw_text") or "") for term in terms):
            continue
        document = docs[str(chunk["document_id"])]
        section = str(chunk.get("section_path") or "")
        rows.append({
            "evidence_id": chunk["chunk_id"], "document_id": chunk["document_id"], "source_path": document.get("source_path"), "file_name": document.get("file_name"),
            "heading_path": section, "location": {"page": int(section.split()[-1])} if section.startswith("Page ") else {}, "text": chunk.get("raw_text") or "", "raw_text": chunk.get("raw_text") or "", "rank": len(rows) + 1, "lineage_status": "LINEAGE_CONFIRMED",
        })
    question = _question("LSR-014")
    bundle = _runtime_bundle(question, plan_query(question).to_dict(), {"atomic_candidates": rows}, docs, {str(row["chunk_id"]): row for row in chunks}, [])
    answer = render(bundle)
    check = validate(answer, bundle)
    assert answer["answer_status"] == "ANSWERED" and check["valid"]
    return {"review_id": "LSR-014", "selection_mode": "EXACT_NAMED_SOURCE_DIRECT_EVIDENCE_PROBE", "status": answer["answer_status"], "bundle_status": bundle["bundle_status"], "answer": answer["answer_text"], "citations": answer["citations"], "validation": check, "embedding_status": "PENDING_NEW_CANDIDATE_EMBEDDING"}


def _lsr017() -> dict:
    question = _question("LSR-017")
    engine = V25LiveShadow()
    primary = {"answer_status": "ANSWERED", "citations": [{"file_name": "2025\u5e74\u534a\u5e74\u603b\u7ed3.md"}]}
    result = engine.run(question, primary, query_vector=np.zeros(engine.vectors.shape[1], dtype=np.float32))
    assert result["v2_status"] == "ANSWERED" and result["validation"]["valid"]
    return {"review_id": "LSR-017", "selection_mode": "PERIOD_SCOPE_RESCUE_ON_FROZEN_V2_5_DATA", "status": result["v2_status"], "bundle_status": result["v2_bundle_status"], "answer": result["v2_answer"], "citations": result["v2_citations"], "validation": result["validation"], "candidate_revision": result["candidate_revision"], "period_scope_rescue": result["period_scope_rescue"]}


def main() -> int:
    records = [_lsr014(), _lsr017()]
    payload = {
        "schema_version": "knowledge_os_v2_6_1.remediation_replay",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "COMPONENT_REPAIR_PASS_NOT_RELEASE_EVIDENCE",
        "release_boundary": "Read-only replay; not counted as Live Shadow, not a Release Gate pass, 8000 and 8010 are unchanged by this script.",
        "records": records,
    }
    (V26 / "remediation_replay_v2_6_1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 开发修复重放", "", "> 仅验证修复组件；不计入 Live Shadow，不解除发布闸门。", ""]
    for row in records:
        lines += [f"## {row['review_id']}", "", f"- 状态：`{row['status']}`；证据包：`{row['bundle_status']}`。", f"- 方式：`{row['selection_mode']}`。", f"- 答案：{row['answer']}", ""]
    (ROOT / "docs" / "V2_6_1_REMEDIATION_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "records": [{"review_id": row["review_id"], "status": row["status"]} for row in records]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
