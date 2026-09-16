from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REVIEW = V26 / "v2_6_2_live_shadow_manual_review.jsonl"
BENCHMARK = ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl"
MODEL = ROOT / "models" / "bge-m3"
RETAINED = {"V262-LSR-001", "V262-LSR-005", "V262-LSR-007", "V262-LSR-008", "V262-LSR-010", "V262-LSR-011", "V262-LSR-012", "V262-LSR-013", "V262-LSR-014", "V262-LSR-015", "V262-LSR-016", "V262-LSR-020"}
OWNER_NEW_CONFIRMATIONS = {
    "V262-LSR-001", "V262-LSR-005", "V262-LSR-007", "V262-LSR-008", "V262-LSR-010",
    "V262-LSR-011", "V262-LSR-012", "V262-LSR-014", "V262-LSR-015", "V262-LSR-020",
}


def main() -> int:
    reviewed = {json.loads(line)["review_id"]: json.loads(line) for line in REVIEW.read_text(encoding="utf-8").splitlines() if line.strip()}
    benchmark = {row["question"]: row for row in (json.loads(line) for line in BENCHMARK.read_text(encoding="utf-8").splitlines())}
    engine = V25LiveShadow()
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_retained_review_replay", use_fp16=False, batch_size=1)
    records = []
    try:
        for review_id in sorted(RETAINED, key=lambda value: int(value.rsplit("-", 1)[-1])):
            item = reviewed[review_id]
            expected = benchmark.get(item["question"], {})
            result = engine.run(item["question"], {"answer_status": "UNKNOWN", "citations": []}, query_vector=provider.embed_query(item["question"]))
            records.append({
                "review_id": review_id,
                "question": item["question"],
                "prior_decision": item["manual_decision"],
                "expected_answer": expected.get("expected_answer"),
                "expected_source": expected.get("expected_source"),
                "candidate_answer": result.get("v2_answer"),
                "candidate_status": result.get("v2_status"),
                "bundle_status": result.get("v2_bundle_status"),
                "citations": result.get("v2_citations") or [],
                "candidate_hash": result.get("candidate_hash"),
                "candidate_revision": result.get("candidate_revision"),
                "validation": result.get("validation"),
            })
    finally:
        provider.close()
    revalidated_at = datetime.now(timezone.utc).astimezone().isoformat()
    for review_id in OWNER_NEW_CONFIRMATIONS:
        reviewed[review_id].update({
            "manual_decision": "ANSWER_GOLD_MATCH",
            "reviewer": "USER_CONFIRMED",
            "reviewed_at": revalidated_at,
            "review_note": "用户确认当前候选答案与来源定位正确。",
        })
    for record in records:
        item = reviewed[record["review_id"]]
        item.update({
            "revalidated_candidate_hash": record["candidate_hash"],
            "revalidated_at": revalidated_at,
            "revalidated_status": f"{record['candidate_status']}/{record['bundle_status']}",
        })
    REVIEW.write_text("\n".join(json.dumps(reviewed[key], ensure_ascii=False, separators=(",", ":")) for key in sorted(reviewed, key=lambda value: int(value.rsplit("-", 1)[-1]))) + "\n", encoding="utf-8")
    summary_path = V26 / "v2_6_2_manual_review_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    decisions = [item["manual_decision"] for item in reviewed.values()]
    summary.update({
        "captured_at": revalidated_at,
        "current_candidate_hash": engine.candidate_hash,
        "manual_review_total": len(decisions),
        "decision_counts": {
            "ANSWER_GOLD_MATCH": decisions.count("ANSWER_GOLD_MATCH"),
            "NOT_VERIFIED": decisions.count("NOT_VERIFIED"),
        },
    })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "schema_version": "knowledge_os_v2_6_2.retained_review_replay",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "REPLAY_COMPLETE_NOT_RELEASE_GATE",
        "sample_basis": "Diagnostic replay of the 12 retained review questions against the current V2.6.2 candidate; not Live Shadow.",
        "current_candidate_hash": engine.candidate_hash,
        "records": records,
    }
    output = V26 / "v2_6_2_retained_review_replay.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "record_count": len(records), "candidate_hash": engine.candidate_hash}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
