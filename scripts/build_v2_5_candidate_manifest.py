from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    baseline = json.loads((V24 / "candidate_frozen_manifest.json").read_text(encoding="utf-8"))
    admitted = json.loads((V25 / "admitted_sources.json").read_text(encoding="utf-8"))
    smoke = json.loads((V25 / "source_coverage_smoke_test.json").read_text(encoding="utf-8"))
    chunks_path = STAGING / "semantic_chunks.jsonl"
    vectors_path = STAGING / "dense_embeddings.npy"
    now = datetime.now(timezone.utc).astimezone().isoformat()
    baseline_payload = {"schema_version": "knowledge_os_v2_5.v2_4_baseline_manifest", "captured_at": now, "source_manifest": str(V24 / "candidate_frozen_manifest.json"), "baseline": baseline, "formal_8000_touched": False}
    candidate = {"schema_version": "knowledge_os_v2_5.candidate_manifest", "status": "CANDIDATE_STAGED", "captured_at": now, "baseline_candidate_hash": baseline.get("candidate_hash"), "baseline_git_head": baseline.get("git_head"), "chunk_version": baseline.get("chunk_version"), "embedding_model": baseline.get("embedding_model"), "embedding_version": baseline.get("embedding_version"), "bm25_config": baseline.get("bm25_config"), "rrf_config": baseline.get("rrf_config"), "validator_config": baseline.get("validator_config"), "reranker": baseline.get("reranker"), "parameter_changes": False, "source_additions": {"count": len(admitted.get("records") or []), "source_sha256": [row.get("source_version") for row in admitted.get("records") or []], "records": admitted.get("records") or []}, "coverage_smoke": {"gate": smoke.get("gate"), "passed_count": smoke.get("passed_count"), "expected_count": smoke.get("expected_count")}, "staging": {"path": str(STAGING), "semantic_chunks_path": str(chunks_path), "semantic_chunks_sha256": sha(chunks_path), "semantic_chunk_count": sum(1 for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()), "dense_vectors_path": str(vectors_path), "dense_vectors_sha256": sha(vectors_path)}, "runtime": {"formal_8000_touched": False, "formal_qdrant_write": False, "8010_switch": "NOT_USED"}}
    candidate_material = json.dumps({key: candidate[key] for key in ("baseline_candidate_hash", "source_additions", "staging", "parameter_changes")}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    candidate["candidate_hash"] = hashlib.sha256(candidate_material).hexdigest()
    (V25 / "v2_4_baseline_manifest.json").write_text(json.dumps(baseline_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "candidate_v2_5_manifest.json").write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": candidate["status"], "candidate_hash": candidate["candidate_hash"], "semantic_chunk_count": candidate["staging"]["semantic_chunk_count"], "coverage_gate": candidate["coverage_smoke"]["gate"], "parameter_changes": candidate["parameter_changes"]}, ensure_ascii=False, indent=2))
    return 0 if candidate["coverage_smoke"]["gate"] == "PASS" and not candidate["parameter_changes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
