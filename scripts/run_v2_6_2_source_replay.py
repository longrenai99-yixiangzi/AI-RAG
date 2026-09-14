from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
MODEL = ROOT / "models" / "bge-m3"
TARGETS = {"V261-LSR-005": "Q51", "V261-LSR-006": "Q70", "V261-LSR-007": "Q77", "V261-LSR-011": "Q40", "V261-LSR-012": "Q58", "V261-LSR-020": "Q130"}


def main() -> int:
    review = json.loads((V26 / "live_shadow_v2_6_1_manual_review.json").read_text(encoding="utf-8"))
    benchmark = {row["question_id"]: row for row in (json.loads(line) for line in (ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl").read_text(encoding="utf-8").splitlines())}
    engine = V25LiveShadow()
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_source_replay", use_fp16=False, batch_size=1)
    records = []
    try:
        for review_id, qid in TARGETS.items():
            source = next(row for row in review["records"] if row["review_id"] == review_id)
            question = source["question"]
            primary = source.get("v1") or {"status": "ANSWERED", "citations": []}
            result = engine.run(question, {"answer_status": primary.get("status"), "citations": primary.get("citations") or []}, query_vector=provider.embed_query(question))
            expected = benchmark.get(qid, {})
            answer = str(result.get("v2_answer") or "")
            keywords = [str(value) for value in expected.get("expected_keywords") or []]
            compact_answer = re.sub(r"\s+", "", answer)
            hits = [value for value in keywords if re.sub(r"\s+", "", value) in compact_answer]
            records.append({"review_id": review_id, "question_id": qid, "question": question, "status": result.get("v2_status"), "bundle_status": result.get("v2_bundle_status"), "answer": answer, "citations": result.get("v2_citations") or [], "candidate_revision": result.get("candidate_revision"), "rescues": {"approved_gold_source": result.get("approved_gold_source_rescue"), "period_scope": result.get("period_scope_rescue")}, "gold_keywords": keywords, "gold_keyword_hits": hits, "gold_keyword_coverage": round(len(hits) / len(keywords), 4) if keywords else None, "validation": result.get("validation")})
    finally:
        provider.close()
    payload = {"schema_version": "knowledge_os_v2_6_2.source_replay", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "SOURCE_REPLAY_COMPLETE_NOT_RELEASE_GATE", "candidate_revision": engine.candidate_revision, "candidate_hash": engine.candidate_hash, "records": records}
    result_path = V26 / "source_replay_v2_6_2.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = V26 / "remediation_candidate_v2_6_2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_replay"] = {"status": "COMPLETE", "recorded_at": payload["captured_at"], "result_path": str(result_path), "record_count": len(records)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.2 来源补齐重放", "", "> 仅验证已批准来源能否被检索和定位；不直接解除发布闸门。", ""]
    for row in records:
        lines += [f"## {row['review_id']}（{row['question_id']}）", "", f"- 状态：`{row['status']}`；证据包：`{row['bundle_status']}`；Gold 关键词覆盖：`{row['gold_keyword_coverage']}`。", f"- 补回：`{row['rescues']}`。", f"- 答案：{row['answer']}", ""]
    (ROOT / "docs" / "V2_6_2_SOURCE_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "records": [{"review_id": row["review_id"], "status": row["status"], "keyword_coverage": row["gold_keyword_coverage"]} for row in records]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
