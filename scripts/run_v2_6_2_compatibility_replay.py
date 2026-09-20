from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"
EXCLUSIONS = V26 / "v2_6_2_owner_exclusions.json"
MODEL = ROOT / "models" / "bge-m3"


def _load_history() -> tuple[list[dict], dict[str, list[dict]]]:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()]
    excluded = set()
    if EXCLUSIONS.exists():
        excluded = {str(item.get("question_hash")) for item in (json.loads(EXCLUSIONS.read_text(encoding="utf-8")).get("records") or [])}
    by_question: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        question = str(row.get("question") or "").strip()
        if not question:
            continue
        if str(row.get("question_hash") or question) in excluded:
            continue
        by_question[str(row.get("question_hash") or question)].append(row)
    latest = [sorted(items, key=lambda item: str(item.get("timestamp") or ""))[-1] for items in by_question.values()]
    latest.sort(key=lambda item: str(item.get("timestamp") or ""))
    return latest, by_question


def main() -> int:
    historical, history_by_question = _load_history()
    engine = V25LiveShadow()
    try:
        import torch
        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_compatibility_replay", use_fp16=cuda_available, batch_size=64 if cuda_available else 32)
    records: list[dict] = []
    try:
        vectors = provider.embed_documents([str(row["question"]) for row in historical])
        for row, vector in zip(historical, vectors, strict=True):
            primary_citations = row.get("v1_citation") or []
            if isinstance(primary_citations, dict):
                primary_citations = [primary_citations]
            result = engine.run(
                str(row["question"]),
                {"answer_status": row.get("v1_status"), "citations": primary_citations},
                query_vector=vector,
            )
            history = history_by_question[str(row.get("question_hash") or row["question"])]
            records.append({
                "question_hash": row.get("question_hash"),
                "question": row["question"],
                "historical_candidate_hashes": sorted({str(item.get("candidate_hash") or "UNKNOWN") for item in history}),
                "historical_latest_status": row.get("v2_status"),
                "historical_latest_bundle_status": row.get("v2_bundle_status"),
                "current_candidate_hash": result.get("candidate_hash"),
                "current_status": result.get("v2_status"),
                "current_bundle_status": result.get("v2_bundle_status"),
                "current_answer": result.get("v2_answer"),
                "current_citations": result.get("v2_citations") or [],
                "current_validation": result.get("validation"),
                "current_new_hit": result.get("new_hit_candidate"),
                "current_lost_hit": result.get("lost_hit_candidate"),
            })
    finally:
        provider.close()

    transitions = Counter((str(row["historical_latest_status"]), str(row["current_status"])) for row in records)
    payload = {
        "schema_version": "knowledge_os_v2_6_2.compatibility_replay",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "CONDITIONAL_COMPATIBILITY_ONLY_NOT_RELEASE_GATE",
        "basis": "Previously recorded real questions, deduplicated by question_hash and excluding Owner-invalid questions listed in v2_6_2_owner_exclusions.json; current answers are offline replay, not Live Shadow.",
        "current_candidate_hash": engine.candidate_hash,
        "historical_question_count": len(records),
        "transition_counts": {f"{old} -> {new}": count for (old, new), count in sorted(transitions.items())},
        "current_status_counts": dict(Counter(str(row["current_status"]) for row in records)),
        "current_bundle_counts": dict(Counter(str(row["current_bundle_status"]) for row in records)),
        "records": records,
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "release_gate": "NOT_CLEARED",
    }
    path = V26 / "v2_6_2_compatibility_replay.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ROOT / "docs" / "V2_6_2_COMPATIBILITY_REPORT.md"
    report.write_text("\n".join([
        "# V2.6.2 跨候选兼容性报告",
        "",
        "> 条件性诊断报告：使用已记录的真实问题做离线重放，不计入当前候选 Live Shadow，不构成 Release Gate 通过。",
        "",
        f"- 历史去重问题：`{payload['historical_question_count']}`",
        f"- 当前候选哈希：`{payload['current_candidate_hash']}`",
        f"- 当前状态：`{payload['status']}`",
        f"- 当前答案状态：`{payload['current_status_counts']}`",
        f"- 状态转移：`{payload['transition_counts']}`",
        "",
        "## 结论",
        "",
        "1. 该报告可用于比较候选版本的状态变化和发现回归候选；",
        "2. 离线重放不能替代当前候选的 Live Shadow；",
        "3. 不授权 8010 切换，不写入 8000；",
        "4. 正式发布前仍需当前候选哈希下的真实 Live Shadow、Rollback Drill 和人工复核。",
        "",
    ]), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "historical_question_count": payload["historical_question_count"],
        "current_candidate_hash": payload["current_candidate_hash"],
        "current_status_counts": payload["current_status_counts"],
        "transition_counts": payload["transition_counts"],
        "path": str(path),
        "report": str(report),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
