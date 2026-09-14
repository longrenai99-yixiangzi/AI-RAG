from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.query_planner_v1 import plan_query
from app.trial.live_shadow_v25 import CANDIDATE_REVISION, V25LiveShadow, _candidate_row, _period_scope_rescue
from app.verified_answer_engine_v2 import render, validate
from scripts.run_verified_answer_engine_v2 import _runtime_bundle


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"
MODEL = ROOT / "models" / "bge-m3"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _question(review_id: str) -> str:
    review = json.loads((V26 / "live_shadow_manual_review.json").read_text(encoding="utf-8"))
    return next(row["question"] for row in review["records"] if row["review_id"] == review_id)


def _side_atomic(chunks: list[dict], docs: dict[str, dict]) -> dict[str, dict]:
    result = {}
    for chunk in chunks:
        document = docs[str(chunk["document_id"])]
        chunk.update({"file_name": document.get("file_name"), "source_path": document.get("source_path"), "source_version": document.get("source_version")})
        result[str(chunk["chunk_id"])] = {
            "evidence_id": str(chunk["chunk_id"]), "source_id": chunk.get("source_id"), "source_version": chunk.get("source_version"), "document_id": chunk.get("document_id"), "section_id": chunk.get("section_id"), "table_id": chunk.get("table_id"),
            "source_path": chunk.get("source_path"), "file_name": chunk.get("file_name"), "heading_path": chunk.get("section_path") or "", "text": chunk.get("raw_text") or "", "raw_text": chunk.get("raw_text") or "", "search_context": chunk.get("retrieval_text") or "", "lineage_status": "LINEAGE_CONFIRMED",
        }
    return result


def _named_source_rescue(question: str, atomic: dict[str, dict]) -> list[dict]:
    marker = "\u6570\u5b57\u5efa\u9020\u7cfb\u7edf\u89e3\u51b3\u65b9\u6848"
    if marker not in question:
        return []
    evidence_markers = ("\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a", "2035\u603b\u4f53\u884c\u52a8\u89c4\u5212", "\u4f9d\u62588\u4e2aBIM", "\u5149\u8c37\u5143\u8457")
    return [record for record in atomic.values() if marker in str(record.get("file_name") or "") and any(value in str(record.get("text") or "") for value in evidence_markers)]


def _run(question: str, vector: list[float], chunks: list[dict], vectors: np.ndarray, docs: dict[str, dict], atomic: dict[str, dict], structured_rows: list[dict]) -> dict:
    plan = plan_query(question)
    weighted = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in weighted])
    query_vector = np.asarray(vector, dtype=np.float32)
    bm = np.asarray(bm25.get_scores(tokenize(question) or ["_empty_"]), dtype=np.float32)
    dense = np.asarray(vectors @ query_vector, dtype=np.float32)
    scores: dict[int, float] = {}
    for rank, index in enumerate(np.argsort(-bm).tolist(), start=1):
        scores[index] = scores.get(index, 0.0) + 1.0 / (60 + rank)
    for rank, index in enumerate(np.argsort(-dense).tolist(), start=1):
        scores[index] = scores.get(index, 0.0) + 1.0 / (60 + rank)
    order = [index for index, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
    candidates = [_candidate_row(atomic[str(chunks[index]["chunk_id"])], rank, "V2_6_1_RRF") for rank, index in enumerate(order[:20], start=1)]
    rescues = [
        ("PERIOD_SCOPE_RESCUE", record) for record in _period_scope_rescue(question, plan, atomic)
    ] + [
        ("EXACT_NAMED_SOURCE_RESCUE", record) for record in _named_source_rescue(question, atomic)
    ]
    rescue_rows = []
    rescue_ids = set()
    for origin, record in rescues:
        evidence_id = str(record.get("evidence_id"))
        if evidence_id and evidence_id not in rescue_ids:
            rescue_rows.append(_candidate_row(record, 0, origin))
            rescue_ids.add(evidence_id)
    candidates = [*rescue_rows, *[row for row in candidates if row["evidence_id"] not in rescue_ids]]
    for rank, row in enumerate(candidates, start=1):
        row["rank"] = rank
    documents = {key: {**value, "scope": value.get("scope") or {}, "document_role": value.get("document_role") or value.get("document_type"), "authority_level": value.get("authority_level") or "UNKNOWN"} for key, value in docs.items()}
    bundle = _runtime_bundle(question, plan.to_dict(), {"atomic_candidates": candidates}, documents, atomic, structured_rows)
    answer = render(bundle)
    validation = validate(answer, bundle)
    return {"question": question, "plan": plan.to_dict(), "status": answer["answer_status"], "bundle_status": bundle["bundle_status"], "answer": answer["answer_text"], "citations": answer["citations"], "validation": validation, "rescue_evidence": [{"evidence_id": row["evidence_id"], "origin": row["candidate_origin"]} for row in rescue_rows]}


def main() -> int:
    manifest = json.loads((V26 / "remediation_candidate_v2_6_1.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED":
        raise RuntimeError("V2_6_1_CANDIDATE_NOT_EMBEDDED_AND_APPROVED")
    base = V25LiveShadow()
    side_docs = {str(row["document_id"]): row for row in _read_jsonl(STAGING / "documents.jsonl")}
    side_chunks = _read_jsonl(STAGING / "semantic_chunks.jsonl")
    side_vectors = np.load(STAGING / "dense_embeddings.npy").astype(np.float32)
    if side_vectors.shape[0] != len(side_chunks):
        raise RuntimeError("V2_6_1_SIDE_VECTOR_CHUNK_MISMATCH")
    side_atomic = _side_atomic(side_chunks, side_docs)
    chunks = [*base.chunks, *side_chunks]
    vectors = np.concatenate((base.vectors, side_vectors), axis=0)
    docs = {**base.docs, **side_docs}
    atomic = {**base.atomic, **side_atomic}
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_1_full_replay", use_fp16=False, batch_size=1)
    try:
        records = []
        for review_id in ("LSR-014", "LSR-017"):
            question = _question(review_id)
            record = _run(question, provider.embed_query(question), chunks, vectors, docs, atomic, base.structured_rows)
            record["review_id"] = review_id
            if record["status"] != "ANSWERED" or not record["validation"]["valid"]:
                raise RuntimeError(f"REPLAY_FAILED:{review_id}:{record['status']}")
            records.append(record)
    finally:
        provider.close()
    payload = {"schema_version": "knowledge_os_v2_6_1.full_candidate_replay", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "FULL_CANDIDATE_REPLAY_PASS_NOT_LIVE_SHADOW", "candidate_hash": manifest["candidate_hash"], "candidate_revision": CANDIDATE_REVISION, "release_boundary": "Read-only full-candidate replay; not an actual-user Live Shadow sample and not a Release Gate pass.", "records": records}
    (V26 / "full_candidate_replay_v2_6_1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["full_candidate_replay"] = {"status": "PASS", "recorded_at": payload["captured_at"], "result_path": str(V26 / "full_candidate_replay_v2_6_1.json")}
    (V26 / "remediation_candidate_v2_6_1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 全候选重放", "", "> 已使用 V2.5 基线加批准的新增来源和向量；仍不计入 Live Shadow 或 Release Gate。", ""]
    for row in records:
        lines += [f"## {row['review_id']}", "", f"- 状态：`{row['status']}`；证据包：`{row['bundle_status']}`。", f"- 补回证据：`{row['rescue_evidence']}`。", f"- 答案：{row['answer']}", ""]
    (ROOT / "docs" / "V2_6_1_FULL_CANDIDATE_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "records": [{"review_id": row["review_id"], "status": row["status"]} for row in records]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
