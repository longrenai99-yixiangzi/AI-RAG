from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
MODEL = ROOT / "models" / "bge-m3"
TRIAL_AUDIT = ROOT / "logs" / "trial" / "trial_audit.jsonl"
FEEDBACK = ROOT / "data" / "trial_feedback" / "feedback.jsonl"
SOURCE_CLOSURE = ROOT / "data" / "shadow" / "trial_cycle_01" / "source_closure_register.jsonl"
EVAL_AUDIT = ROOT / "evaluation" / "v2_8010_trial" / "trial_audit.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compact(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.casefold())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    eval_rows = read_jsonl(EVAL_AUDIT)
    dated = [row for row in eval_rows if str(row.get("timestamp") or "")]
    latest_day = max((str(row.get("timestamp") or "")[:10] for row in dated), default="")
    latest_day_rows = [row for row in dated if str(row.get("timestamp") or "").startswith(latest_day)]
    latest_unique = {}
    for row in latest_day_rows:
        question = str(row.get("question") or "").strip()
        key = compact(question)
        if len(key) >= 4 and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", question):
            latest_unique.setdefault(key, {**row, "question": question})
    # Prefer the current day's actual /ai submissions when they provide the
    # required sample; fall back to the older real-trial sources otherwise.
    logs = list(latest_unique.values()) if len(latest_unique) >= 30 else read_jsonl(TRIAL_AUDIT) + read_jsonl(FEEDBACK) + read_jsonl(SOURCE_CLOSURE)
    latest: dict[str, dict] = {}
    for row in logs:
        question = str(row.get("question") or "").strip()
        key = compact(question)
        if len(key) < 4 or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", question):
            continue
        if key not in latest or str(row.get("timestamp") or "") > str(latest[key].get("timestamp") or ""):
            latest[key] = {**row, "question": question}
    real_rows = list(latest.values())
    sample_basis = "evaluation/v2_8010_trial/trial_audit.jsonl latest day unique /ai submissions" if len(latest_unique) >= 30 else "historical real trial and feedback logs"
    assert len(real_rows) == len({compact(str(row["question"])) for row in real_rows})
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    for chunk in chunks:
        document = docs.get(str(chunk.get("document_id")), {})
        chunk["file_name"] = chunk.get("file_name") or document.get("file_name")
        chunk["source_path"] = chunk.get("source_path") or document.get("source_path")
    vectors = np.load(STAGING / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    texts = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in texts])
    now = datetime.now(timezone.utc).astimezone().isoformat()
    records = []
    for row in real_rows:
        bm = np.asarray(bm25.get_scores(tokenize(row["question"]) or ["_empty_"]), dtype=np.float32)
        top = np.argsort(-bm).tolist()[:5]
        v2_top = chunks[top[0]] if top else {}
        v1_evidence = (row.get("selected_evidence") or row.get("citation") or [{}])[0] if isinstance(row.get("selected_evidence") or row.get("citation") or [{}], list) else {}
        v1_status = str(row.get("answer_status") or row.get("final_status") or row.get("answer_state") or "UNKNOWN")
        v1_answer_status = v1_status if v1_status in {"ANSWERED", "INSUFFICIENT_EVIDENCE", "PARTIAL_ANSWER"} else ("ANSWERED" if v1_status in {"GENERATED", "FACT_RESULT"} else "INSUFFICIENT_EVIDENCE")
        v1_citation = v1_evidence or {"evidence_ids": row.get("evidence_ids") or [], "citation_ids": row.get("citation_ids") or [], "document_ids": row.get("document_ids") or []}
        source_known = bool(v1_evidence.get("file_name"))
        records.append({"shadow_run_id": "LS26-" + digest(row["question"] + str(row.get("timestamp") or ""))[:20], "timestamp": now, "source_record_timestamp": row.get("timestamp"), "session_id_hash": digest(str(row.get("trial_user") or "") + str(row.get("conversation_id") or "")), "question_hash": digest(row["question"]), "question": row["question"], "v1_status": v1_status, "v1_answer_status": v1_answer_status, "v1_top_source": v1_evidence.get("file_name"), "v1_top_section": v1_evidence.get("location_display") or v1_evidence.get("location"), "v1_citation": v1_citation, "v2_status": "RETRIEVAL_PREVIEW_BM25_ONLY", "v2_answer_status": None, "v2_top_source": v2_top.get("file_name"), "v2_top_section": v2_top.get("section_path"), "v2_citation": {"file_name": v2_top.get("file_name"), "source_version": v2_top.get("source_version"), "section_path": v2_top.get("section_path"), "chunk_id": v2_top.get("chunk_id")}, "source_agreement": (v1_evidence.get("file_name") == v2_top.get("file_name")) if source_known else None, "section_agreement": None, "new_hit_candidate": None, "lost_hit_candidate": None, "new_hit_verification": "REVIEW_REQUIRED", "lost_hit_verification": "REVIEW_REQUIRED", "v1_latency_ms": (row.get("latency") or {}).get("total_ms"), "v2_latency_ms": None, "v1_error": None, "v2_error": "V2_5_DENSE_AND_ANSWER_ENGINE_NOT_RUN_IN_LIVE_RUNTIME", "execution_mode": "REPLAY_EXISTING_REAL_TRIAL_LOG"})
    comparable_sources = [row for row in records if row["source_agreement"] is not None]
    source_agreement = sum(bool(row["source_agreement"]) for row in comparable_sources)
    errors = sum(bool(row["v1_error"]) for row in records)
    branch_not_run = len(records)
    sample_gate = "SHADOW_INSUFFICIENT_SAMPLE" if len(records) < 30 else "PASS"
    shadow_gate = "SHADOW_INSUFFICIENT_SAMPLE" if len(records) < 30 else "LIVE_BRANCH_NOT_READY"
    stop_reason = "真实唯一问题样本少于30，且本次未重复刷题。" if len(records) < 30 else "样本数已达到30，但 V2.5 答案分支尚未接入8010；当前仅有 BM25 诊断预览，不能冒充 Live Shadow。"
    report = {"schema_version": "knowledge_os_v2_6.live_shadow_report", "captured_at": now, "execution_mode": "REPLAY_EXISTING_REAL_TRIAL_LOG_WITH_BM25_PREVIEW_ONLY", "live_runtime_branching": False, "sample_size": len(records), "sample_basis": sample_basis, "sample_target": 100, "minimum_effective_sample": 30, "sample_gate": sample_gate, "query_encoder_device": "NOT_RUN_GPU_HEADROOM_PROTECTION", "v2_candidate_execution": "BM25_ONLY_DIAGNOSTIC_PREVIEW; NOT_LIVE_V2_5_ANSWER_ENGINE", "agreement": {"source_comparable_count": len(comparable_sources), "source_agreement_count": source_agreement, "source_agreement_rate": round(source_agreement / len(comparable_sources), 4) if comparable_sources else None, "section_agreement_count": 0, "section_agreement_rate": None}, "new_hits": {"candidate_count": 0, "verified_count": 0, "verification": "REVIEW_REQUIRED"}, "lost_hits": {"candidate_count": 0, "verified_count": 0, "verification": "REVIEW_REQUIRED"}, "critical_failures": "NOT_ASSESSED_WITHOUT_V2_5_ANSWER_ENGINE", "latency": {"v1_p50_ms": None, "v1_p95_ms": None, "v2_p50_ms": None, "v2_p95_ms": None}, "errors": {"v1_error_count": errors, "v2_runtime_error_count": 0, "v2_branch_not_run_count": branch_not_run, "v2_error_rate": None}, "shadow_gate": shadow_gate, "stop_reason": stop_reason, "formal_8000_touched": False, "records_path": str(V26 / "live_shadow_runs.jsonl")}
    (V26 / "live_shadow_runs.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")
    (V26 / "live_shadow_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6 Live Shadow Report", "", f"- 样本数：{report['sample_size']}（目标 100；最低有效样本 30）", f"- 执行方式：{report['execution_mode']}", f"- Shadow Gate：`{report['shadow_gate']}`", "", "## 结果", "", f"- 来源 Agreement：{report['agreement']['source_agreement_count']}/{report['sample_size']}", "- Verified New Hit：0（未判定，需业务审核）", "- Verified Lost Hit：0（未判定，需业务审核）", "- V2.5 答案引擎：未接入 8010，只有检索层回放", "- V1/V2 延迟：未形成可比数据", "", "## 停止原因", "", report["stop_reason"], "", "本报告不把离线回放、Holdout 或重复刷题结果冒充 Live Shadow。样本达到 30 且 V2.5 分支接入真实请求后，才能继续形成 Live Shadow Gate。"]
    (ROOT / "docs" / "LIVE_SHADOW_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"sample_size": report["sample_size"], "sample_gate": report["sample_gate"], "shadow_gate": report["shadow_gate"], "v2_answer_engine": "NOT_RUN", "next": "BLOCKED_UNTIL_V2_5_LIVE_BRANCH_IS_WIRED"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
