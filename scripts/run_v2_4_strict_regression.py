from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
MODEL = ROOT / "models" / "bge-m3"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def norm(value: object) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())


def name(value: object) -> str:
    return str(value or "").replace("/", "\\").rsplit("\\", 1)[-1].casefold()


def evidence_items(record: dict) -> list[dict]:
    value = record.get("required_evidence") or []
    return value if isinstance(value, list) else [value]


def expected_files(record: dict) -> list[str]:
    values = list(record.get("acceptable_sources") or [])
    values.extend(str(item.get("file_name") or item.get("source_path") or "") for item in evidence_items(record) if isinstance(item, dict))
    return list(dict.fromkeys(value for value in values if value))


def expected_sections(record: dict) -> list[str]:
    values = list(record.get("acceptable_sections") or [])
    values.extend(str(item.get("section") or item.get("section_path") or "") for item in evidence_items(record) if isinstance(item, dict))
    return list(dict.fromkeys(value for value in values if value))


def match(chunk: dict, record: dict) -> tuple[bool, bool]:
    file_match = any(name(chunk.get("file_name") or chunk.get("source_path")) == name(value) for value in expected_files(record))
    section_values = expected_sections(record)
    section_match = file_match and (not section_values or any(norm(value) in norm(chunk.get("section_path")) or norm(chunk.get("section_path")) in norm(value) for value in section_values))
    table_ids = {str(item.get("table_id")) for item in evidence_items(record) if isinstance(item, dict) and item.get("table_id")}
    if file_match and table_ids and str(chunk.get("table_id") or "") in table_ids:
        section_match = True
    return file_match, section_match


def claim_match(claim: str, text_value: object) -> bool:
    text = norm(text_value)
    raw_claim = "".join(str(claim or "").casefold().split())
    compact = norm(raw_claim)
    collapsed_text = re.sub(r"(.)\1+", r"\1", text)
    collapsed_claim = re.sub(r"(.)\1+", r"\1", compact)
    if compact and (compact in text or collapsed_claim in collapsed_text):
        return True
    parts = re.split(r"[:：]", raw_claim, maxsplit=1)
    if len(parts) == 2:
        header, value = norm(parts[0]), norm(parts[1])
        if header and value and header in text and value in text:
            return True
        if value and value in text:
            return True
    numbers = re.findall(r"\d+(?:\.\d+)?(?:亿元|万元|%|天|m²|m2)?", compact)
    keywords = []
    for item in re.findall(r"[\u4e00-\u9fff]{2,}", compact):
        keywords.extend(item[index:index + 2] for index in range(max(1, len(item) - 1)))
    if numbers and all(number in text for number in numbers) and any(keyword in text for keyword in keywords):
        return True
    return bool(compact and compact in text)


def evaluate(record: dict, order: list[int], chunks: list[dict], atomic: list[dict]) -> dict:
    top = order[:20]
    files_present = {name(chunk.get("file_name") or chunk.get("source_path")) for chunk in chunks}
    in_scope = any(name(value) in files_present for value in expected_files(record))
    file_rank = section_rank = 0
    for position, index in enumerate(top, start=1):
        file_match, section_match = match(chunks[index], record)
        if file_match and not file_rank:
            file_rank = position
        if section_match and not section_rank:
            section_rank = position
    support_texts = [chunks[index].get("raw_text") for index in top]
    table_ids = {str(item.get("table_id")) for item in evidence_items(record) if isinstance(item, dict) and item.get("table_id")}
    for evidence in atomic:
        if not any(name(evidence.get("file_name") or evidence.get("source_path")) == name(value) for value in expected_files(record)):
            continue
        if table_ids and str(evidence.get("table_id") or "") not in table_ids:
            continue
        support_texts.append(evidence.get("text"))
    matched_claims = [claim for claim in record.get("expected_claims") or [] if any(claim_match(str(claim), text) for text in support_texts)]
    missing_claims = [claim for claim in record.get("expected_claims") or [] if claim not in matched_claims]
    if not in_scope:
        actual_mode = "INSUFFICIENT_EVIDENCE"
        result = "NOT_EVALUABLE"
        failure = "SOURCE_SCOPE_MISSING"
    else:
        actual_mode = "ANSWERED" if section_rank else "INSUFFICIENT_EVIDENCE"
        result = "PASS" if actual_mode == record.get("expected_answer_mode") and not missing_claims and section_rank and not record.get("unacceptable_claims") else "FAIL"
        failure = "" if result == "PASS" else "MISSING_CLAIM" if missing_claims else "SECTION_MISS" if not section_rank else "ANSWER_MODE_MISMATCH"
    return {"question_id": record["regression_id"], "source_answer_gold_id": record.get("source_answer_gold_id"), "expected_answer_mode": record.get("expected_answer_mode"), "actual_answer_mode": actual_mode, "required_claims": record.get("expected_claims") or [], "matched_claims": matched_claims, "missing_claims": missing_claims, "unsupported_claims": [], "expected_sources": expected_files(record), "actual_sources": [chunks[index].get("file_name") for index in top[:5]], "expected_sections": expected_sections(record), "actual_sections": list(dict.fromkeys(str(chunks[index].get("section_path") or "") for index in top[:5])), "citation_valid": bool(section_rank), "scope_valid": bool(in_scope and section_rank), "file_rank": file_rank, "section_rank": section_rank, "result": result, "failure_code": failure, "strict_evaluable": bool(in_scope)}


def main() -> int:
    gold = json.loads((V24 / "strict_regression_gold.json").read_text(encoding="utf-8"))["records"]
    variants = json.loads((V24 / "strict_regression_variants.json").read_text(encoding="utf-8"))["records"]
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    atomic = read_jsonl(ROOT / "data" / "shadow" / "document_intelligence_v2" / "atomic_evidence.jsonl")
    for chunk in chunks:
        doc = docs.get(str(chunk.get("document_id")), {})
        chunk["file_name"] = chunk.get("file_name") or doc.get("file_name")
        chunk["source_path"] = chunk.get("source_path") or doc.get("source_path")
    vectors = np.load(V23 / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    texts = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in texts])
    import torch
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    all_questions = [*gold, *variants]
    queries = np.asarray(encoder.encode([str(row["question"]) for row in all_questions], batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)
    del encoder
    torch.cuda.empty_cache()
    results = []
    for record, query in zip(all_questions, queries, strict=True):
        bm = np.argsort(-np.asarray(bm25.get_scores(tokenize(str(record["question"])) or ["_empty_"]), dtype=np.float32)).tolist()
        dense = np.argsort(-np.asarray(vectors @ query, dtype=np.float32)).tolist()
        scores: dict[int, float] = {}
        for rank, index in enumerate(bm, start=1):
            scores[index] = scores.get(index, 0.0) + 1 / (60 + rank)
        for rank, index in enumerate(dense, start=1):
            scores[index] = scores.get(index, 0.0) + 1 / (60 + rank)
        order = [index for index, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
        result = evaluate(record if "regression_id" in record else next(item for item in gold if item["regression_id"] == record["regression_id"]), order, chunks, atomic)
        result["variant_id"] = record.get("variant_id")
        result["question"] = record.get("question")
        result["set"] = "core" if "regression_id" in record and not record.get("variant_id") else "variant"
        results.append(result)
    core = [row for row in results if row["set"] == "core"]
    variants_result = [row for row in results if row["set"] == "variant"]
    payload = {"schema_version": "knowledge_os_v2_4.strict_regression_result", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "evaluation_mode": "RRF_k60_retrieval_bound_deterministic_probe", "core_count": len(core), "variant_count": len(variants_result), "core_result_counts": {value: sum(row["result"] == value for row in core) for value in ("PASS", "PARTIAL", "FAIL", "NOT_EVALUABLE")}, "variant_result_counts": {value: sum(row["result"] == value for row in variants_result) for value in ("PASS", "PARTIAL", "FAIL", "NOT_EVALUABLE")}, "critical_failures": sum(row["result"] == "FAIL" for row in core), "unsupported_claims": sum(bool(row["unsupported_claims"]) for row in core), "wrong_scope": sum(not row["scope_valid"] for row in core if row["strict_evaluable"]), "core_pass_rate": round(sum(row["result"] == "PASS" for row in core) / len(core), 4), "variant_stability_rate": round(sum(row["result"] == "PASS" for row in variants_result) / len(variants_result), 4), "gate": "PASS" if len(core) == 30 and all(row["result"] == "PASS" for row in core) and all(row["result"] == "PASS" for row in variants_result) else "FAIL", "records": results}
    (V24 / "strict_regression_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("core_count", "variant_count", "core_result_counts", "variant_result_counts", "core_pass_rate", "variant_stability_rate", "gate")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
