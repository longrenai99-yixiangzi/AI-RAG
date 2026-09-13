from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.knowledge_engineering.structured_v2 import build_structured_layer


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
OLD = ROOT / "data" / "shadow" / "knowledge_v2_staging"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
STATE = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"

SOURCES = [
    Path(r"D:\工作\二公司技术部\2026\各类文件\设计管理\《项目设计管理手册》.pdf"),
    Path(r"D:\工作\二公司技术部\2026\知识库\全专业施工图审核要点提示汇编\全专业施工图审核要点提示汇编（2026年）.xlsx"),
    Path(r"D:\工作\二公司技术部\2026\责任状\局\3.二公司：2026年设计与技术专项责任书 .docx"),
    Path(r"D:\工作\二公司技术部\2026\示范工程\关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx"),
    Path(r"D:\工作\二公司技术部\2026\EPC项目双周推进会\4月\EPC项目设计管理工作监督任务表（2026年4月第一周）.xlsx"),
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    missing = [str(path) for path in SOURCES if not path.is_file()]
    if missing:
        raise RuntimeError(f"source_missing: {missing}")
    builder = DocumentIntelligenceV2Builder(Path(r"D:\工作"))
    raw_atomic = []
    for path in SOURCES:
        raw_atomic.extend(build_atomic_evidence(path, Path(r"D:\工作")).get("records") or [])
    new_bundle = builder.build(SOURCES, raw_atomic)
    old = {name: read_jsonl(OLD / f"{name}.jsonl") for name in ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts", "atomic_evidence")}
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    registry = {str(row.get("source_path") or "").casefold(): row for row in (state.get("sources") or {}).values() if isinstance(row, dict)}
    owner_gold_refs = {
        "《项目设计管理手册》.pdf": ["BA-001", "BA-002"],
        "全专业施工图审核要点提示汇编（2026年）.xlsx": ["BA-005"],
        "3.二公司：2026年设计与技术专项责任书 .docx": ["BA-006"],
        "关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx": ["BA-007"],
        "EPC项目设计管理工作监督任务表（2026年4月第一周）.xlsx": ["BA-009"],
    }
    admitted = []
    for path in SOURCES:
        digest = sha(path)
        source_id = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
        registry[str(path).casefold()] = {"source_id": f"V25-{source_id}", "source_path": str(path), "current_hash": digest, "body_status": "OWNER_GOLD_ADMITTED", "index_status": "STAGING_ONLY"}
        admitted.append({"source_id": f"V25-{source_id}", "source_version": digest, "source_hash": digest, "effective_status": "OWNER_GOLD_ADMITTED", "source_path": str(path), "owner_gold_refs": owner_gold_refs.get(path.name, []), "file_name": path.name, "file_type": path.suffix.lower()})
    for document in new_bundle["documents"]:
        path = Path(str(document.get("source_path") or ""))
        digest = sha(path)
        document.update({"source_id": f"V25-{hashlib.sha256(str(path.resolve()).casefold().encode('utf-8')).hexdigest()[:24]}", "source_version": digest, "source_hash": digest, "effective_status": "OWNER_GOLD_ADMITTED"})
    new_layer = build_structured_layer(new_bundle["documents"], new_bundle["sections"], new_bundle["paragraphs"], new_bundle["tables"], new_bundle["table_rows"], new_bundle["atomic_evidence"], registry)
    combined = {name: [*old[name], *new_bundle[name]] for name in old}
    old_chunks = read_jsonl(OLD / "semantic_chunks.jsonl")
    new_chunks = [*old_chunks, *new_layer["semantic_chunks"]]
    STAGING.mkdir(parents=True, exist_ok=True)
    for name, rows in combined.items():
        write_jsonl(STAGING / f"{name}.jsonl", rows)
    write_jsonl(STAGING / "semantic_chunks.jsonl", new_chunks)
    write_jsonl(STAGING / "knowledge_node_bindings.jsonl", new_layer["knowledge_node_bindings"])
    old_by_id = {str(row.get("chunk_id")): row for row in old_chunks}
    changed_old = [row for row in new_chunks if str(row.get("chunk_id")) in old_by_id and (row.get("retrieval_text") != old_by_id[str(row.get("chunk_id"))].get("retrieval_text") or row.get("source_version") != old_by_id[str(row.get("chunk_id"))].get("source_version"))]
    new_only = [row for row in new_chunks if str(row.get("chunk_id")) not in old_by_id]
    old_vectors = np.load(V23 / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    if len(old_vectors) != len(old_chunks):
        raise RuntimeError("old vector/chunk count mismatch")
    old_vectors_by_id = {str(row.get("chunk_id")): old_vectors[index] for index, row in enumerate(old_chunks)}
    current_vectors = np.zeros((len(new_chunks), old_vectors.shape[1]), dtype=np.float32)
    unchanged_old = 0
    for index, row in enumerate(new_chunks):
        vector = old_vectors_by_id.get(str(row.get("chunk_id")))
        if vector is not None and str(row.get("chunk_id")) not in {str(item.get("chunk_id")) for item in changed_old}:
            current_vectors[index] = vector
            unchanged_old += 1
    V25.mkdir(parents=True, exist_ok=True)
    np.save(STAGING / "dense_embeddings.npy", current_vectors)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    ingestion = {"schema_version": "knowledge_os_v2_5.ingestion_report", "captured_at": now, "source_count": len(SOURCES), "documents_added": len(new_bundle["documents"]), "documents_parse_status": dict(Counter(str(row.get("parse_status")) for row in new_bundle["documents"])), "sections_added": len(new_bundle["sections"]), "tables_added": len(new_bundle["tables"]), "table_rows_added": len(new_bundle["table_rows"]), "atomic_evidence_added": len(raw_atomic), "semantic_chunks_total": len(new_chunks), "semantic_chunks_added": len(new_only), "changed_old_chunks": len(changed_old), "quarantined_added": sum(row.get("index_status") == "QUARANTINED" for row in new_only), "duplicate_added": sum(bool(row.get("duplicate_of")) for row in new_only), "node_binding_added": len(new_layer["knowledge_node_bindings"]), "source_version_recorded": all(bool(row.get("source_version")) for row in admitted), "quality_gate": "PASS" if new_bundle["documents"] and all(row.get("parse_status") == "parsed" for row in new_bundle["documents"]) and not changed_old else "FAIL", "staging_path": str(STAGING), "formal_8000_touched": False}
    embedding = {"schema_version": "knowledge_os_v2_5.embedding_increment_report", "captured_at": now, "status": "READY_FOR_NEW_ONLY_EMBEDDING", "old_chunk_count": len(old_chunks), "new_chunk_count": len(new_chunks), "new_chunks": len(new_only), "changed_old_chunks": len(changed_old), "old_vectors_reused": unchanged_old, "old_vectors_changed": 0, "new_vectors_pending": len(new_only), "model": "BAAI/bge-m3", "input": "retrieval_text", "old_vector_source": str(V23 / "dense_embeddings.npy"), "staging_vector_path": str(STAGING / "dense_embeddings.npy"), "hash_policy": "unchanged chunk_id and retrieval_text reuse old vector; changed/new chunk requires incremental encoding", "formal_8000_touched": False}
    (V25 / "admitted_sources.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_5.admitted_sources", "captured_at": now, "count": len(admitted), "records": admitted}, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "ingestion_report.json").write_text(json.dumps(ingestion, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "embedding_increment_report.json").write_text(json.dumps(embedding, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ingestion": ingestion, "embedding": embedding}, ensure_ascii=False, indent=2))
    return 0 if ingestion["quality_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
