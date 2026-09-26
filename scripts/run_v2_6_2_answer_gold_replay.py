from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
GOLD = V26 / "v2_6_2_answer_gold_confirmation.json"
MODEL = ROOT / "models" / "bge-m3"
GOLD_MARKERS = {
    "V262-LSR-002": ("7项", "6.1", "6.15"),
    "V262-LSR-003": ("背景介绍", "设计管理基本动作与要素", "关键动作实施要点", "全专业设计技术管控要点", "问题与建议"),
    "V262-LSR-004": ("12.2亿元", "110005万元"),
    "V262-LSR-006": ("项目41个", "13个项目", "100万㎡", "3GW"),
    "V262-LSR-009": ("62个", "含物资"),
    "V262-LSR-017": ("3个月", "6个月", "集电线路的具体路径图"),
    "V262-LSR-018": ("10.19亿", "19.8万㎡", "上海联创设计集团股份有限公司"),
    "V262-LSR-019": ("物理文件总数", "可解析文档", "压缩包"),
    "V262-LSR-021": ("投标建安工程费下浮6%",),
}
RUNTIME_CODE_FILES = (
    "app/trial/live_shadow_v25.py",
    "app/retrieval/query_planner_v1.py",
    "app/verified_answer_engine_v2.py",
    "app/ingestion/normalization/markdown_normalizer.py",
    "scripts/build_verified_evidence_bundle_v1.py",
    "scripts/run_verified_answer_engine_v2.py",
    "scripts/run_v2_6_2_answer_gold_replay.py",
)


def compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("。", "").replace("，", ",")


def _code_sha256() -> str:
    digest = hashlib.sha256()
    for relative in RUNTIME_CODE_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_fingerprints(*, code_sha256: str, candidate_hash: str, candidate_revision: str, question_id: str, question: str, answer: str, citations: list[dict]) -> dict[str, str]:
    citation_fields = ("citation_id", "evidence_id", "source_id", "source_version", "source_path", "location")
    citation_identity = [{key: citation.get(key) for key in citation_fields} for citation in citations]
    answer_citation = json.dumps({"answer": answer, "citations": citation_identity}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    answer_citation_sha256 = hashlib.sha256(answer_citation.encode("utf-8")).hexdigest()
    run_identity = json.dumps({"code_sha256": code_sha256, "candidate_hash": candidate_hash, "candidate_revision": candidate_revision, "question_id": question_id, "question": question, "answer_citation_sha256": answer_citation_sha256}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"answer_citation_sha256": answer_citation_sha256, "run_fingerprint": hashlib.sha256(run_identity.encode("utf-8")).hexdigest()}


def _current_manual_review(prior: dict, run_fingerprint: str) -> dict:
    decision = prior.get("manual_decision")
    if not decision:
        return {"manual_decision": None, "reviewer": None, "reviewed_at": None, "review_status": "PENDING_OWNER_RUNTIME_REVIEW"}
    if prior.get("run_fingerprint") == run_fingerprint:
        return {"manual_decision": decision, "reviewer": prior.get("reviewer"), "reviewed_at": prior.get("reviewed_at"), "review_status": "OWNER_REVIEWED"}
    previous_review = {key: prior.get(key) for key in ("manual_decision", "reviewer", "reviewed_at", "run_fingerprint")}
    previous_review["carry_status"] = "STALE_FINGERPRINT_MISSING" if not prior.get("run_fingerprint") else "FINGERPRINT_CHANGED"
    return {"manual_decision": None, "reviewer": None, "reviewed_at": None, "review_status": "PENDING_OWNER_RUNTIME_REVIEW", "previous_review": previous_review}


def main() -> int:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    output = V26 / "v2_6_2_answer_gold_replay.json"
    previous = {}
    if output.exists():
        previous = {row.get("question_id"): row for row in json.loads(output.read_text(encoding="utf-8")).get("records", [])}
    code_sha256 = _code_sha256()
    engine = V25LiveShadow()
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_answer_gold_replay", use_fp16=False, batch_size=1)
    records = []
    try:
        for item in gold["records"]:
            question = str(item["question"])
            result = engine.run(question, {"answer_status": "UNKNOWN", "citations": []}, query_vector=provider.embed_query(question))
            answer = str(result.get("v2_answer") or "")
            expected = compact(item["answer"])
            actual = compact(answer)
            markers = GOLD_MARKERS.get(item["question_id"], ())
            marker_hits = [marker for marker in markers if compact(marker) in actual]
            record = {
                "question_id": item["question_id"],
                "question": question,
                "gold_answer": item["answer"],
                "candidate_answer": answer,
                "candidate_status": result.get("v2_status"),
                "bundle_status": result.get("v2_bundle_status"),
                "citations": result.get("v2_citations") or [],
                "candidate_revision": result.get("candidate_revision"),
                "candidate_hash": result.get("candidate_hash"),
                "gold_answer_exact_match": expected in actual,
                "gold_marker_hits": marker_hits,
                "gold_marker_coverage": round(len(marker_hits) / len(markers), 4) if markers else None,
                "validation": result.get("validation"),
                "code_sha256": code_sha256,
            }
            prior = previous.get(item["question_id"], {})
            record.update(_run_fingerprints(code_sha256=code_sha256, candidate_hash=str(result.get("candidate_hash") or ""), candidate_revision=str(result.get("candidate_revision") or ""), question_id=str(item["question_id"]), question=question, answer=answer, citations=record["citations"]))
            record.update(_current_manual_review(prior, record["run_fingerprint"]))
            records.append(record)
    finally:
        provider.close()
    captured_at = datetime.now(timezone.utc).astimezone().isoformat()
    payload = {
        "schema_version": "knowledge_os_v2_6_2.answer_gold_replay",
        "captured_at": captured_at,
        "status": "REPLAY_COMPLETE_NOT_RELEASE_GATE",
        "candidate_revision": engine.candidate_revision,
        "candidate_hash": engine.candidate_hash,
        "code_sha256": code_sha256,
        "gold_source": str(GOLD),
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "records": records,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.2 Answer Gold 候选重放", "", "> 重放已确认的 10 条 Answer Gold；不计入 Live Shadow，不解除发布闸门。", ""]
    for row in records:
        lines += [
            f"## {row['question_id']}",
            "",
            f"- 问题：{row['question']}",
            f"- 候选状态：`{row['candidate_status']}`；证据包：`{row['bundle_status']}`；Gold 关键事实覆盖：`{row['gold_marker_coverage']}`。",
            f"- 候选答案：{row['candidate_answer']}",
            f"- 引用数：`{len(row['citations'])}`；人工核验：`{row['review_status']}`；历史审核：`{(row.get('previous_review') or {}).get('carry_status', 'NONE')}。",
            "",
        ]
    (ROOT / "docs" / "V2_6_2_ANSWER_GOLD_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "record_count": len(records), "answer_exact_matches": sum(row["gold_answer_exact_match"] for row in records), "full_marker_matches": sum(row["gold_marker_coverage"] == 1 for row in records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
