from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.trial.live_shadow_v25 import V25LiveShadow
from app.trial.v2 import V2TrialEngine


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    runs = [row for row in read_jsonl(RUNS) if row.get("execution_mode") == "LIVE_REQUEST_BACKGROUND_V2_5_SHADOW"]
    latest = {}
    for row in runs:
        latest.setdefault(row.get("question_hash"), row)
    candidates = [row for row in latest.values() if row.get("new_hit_candidate") or row.get("lost_hit_candidate")]
    candidates.sort(key=lambda row: (0 if row.get("new_hit_candidate") else 1, str(row.get("timestamp") or "")))
    primary_engine = V2TrialEngine()
    shadow_engine = V25LiveShadow()
    now = datetime.now(timezone.utc).astimezone().isoformat()
    reviews = []
    for index, source in enumerate(candidates, start=1):
        question = str(source.get("question") or "")
        try:
            primary = primary_engine.answer(question, detect_growth=False)
            vector = primary_engine.dense.embed_query(question)
            shadow = shadow_engine.run(question, primary, query_vector=vector)
            review = {"review_id": f"LSR-{index:03d}", "candidate_type": "NEW_HIT" if source.get("new_hit_candidate") else "LOST_HIT", "question": question, "historical": {"shadow_run_id": source.get("shadow_run_id"), "query_run_id": source.get("query_run_id"), "v1_status_at_request": source.get("v1_status"), "v2_status_at_request": source.get("v2_status"), "v1_top_source_at_request": source.get("v1_top_source"), "v2_top_source_at_request": source.get("v2_top_source"), "new_hit_candidate": source.get("new_hit_candidate"), "lost_hit_candidate": source.get("lost_hit_candidate")}, "replayed_primary": {"status": primary.get("answer_status"), "answer": primary.get("answer"), "citations": primary.get("citations") or [], "latency_ms": (primary.get("latency") or {}).get("total_ms")}, "replayed_v2_5": {"status": shadow.get("v2_status"), "bundle_status": shadow.get("v2_bundle_status"), "answer": shadow.get("v2_answer"), "citations": shadow.get("v2_citations") or [], "latency_ms": shadow.get("latency_ms"), "validation": shadow.get("validation")}, "manual_decision": None, "reviewer": None, "reviewed_at": None, "review_note": "请核对两份答案的事实、项目/年份范围、来源定位与 Citation 是否支持；不得仅按状态判断。", "replay_mode": "READ_ONLY_CURRENT_PRIMARY_AND_V2_5_REPLAY", "captured_at": now}
        except Exception as error:
            review = {"review_id": f"LSR-{index:03d}", "candidate_type": "NEW_HIT" if source.get("new_hit_candidate") else "LOST_HIT", "question": question, "historical": {"shadow_run_id": source.get("shadow_run_id"), "query_run_id": source.get("query_run_id"), "v1_status_at_request": source.get("v1_status"), "v2_status_at_request": source.get("v2_status")}, "replayed_primary": None, "replayed_v2_5": None, "manual_decision": None, "reviewer": None, "reviewed_at": None, "review_note": "重放失败，不能据此判定 New/Lost Hit。", "replay_error": f"{type(error).__name__}: {error}", "replay_mode": "READ_ONLY_CURRENT_PRIMARY_AND_V2_5_REPLAY", "captured_at": now}
        reviews.append(review)
        print(f"manual_replay={index}/{len(candidates)} status={(review.get('replayed_v2_5') or {}).get('status', 'ERROR')}", flush=True)
    payload = {"schema_version": "knowledge_os_v2_6.live_shadow_manual_review", "captured_at": now, "review_count": len(reviews), "new_hit_count": sum(row["candidate_type"] == "NEW_HIT" for row in reviews), "lost_hit_count": sum(row["candidate_type"] == "LOST_HIT" for row in reviews), "replayed_ok": sum(row.get("replayed_v2_5") is not None for row in reviews), "replayed_errors": sum(row.get("replayed_v2_5") is None for row in reviews), "manual_decision_status": "PENDING_OWNER_REVIEW", "warning": "重放使用当前 Primary/V2.5 代码，不修改原始 Live Shadow 记录，也不将重放结果自动计为 Gate PASS。", "records_path": str(V26 / "live_shadow_manual_review.jsonl"), "records": reviews}
    (V26 / "live_shadow_manual_review.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in reviews), encoding="utf-8")
    (V26 / "live_shadow_manual_review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("review_count", "new_hit_count", "lost_hit_count", "replayed_ok", "replayed_errors", "manual_decision_status")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
