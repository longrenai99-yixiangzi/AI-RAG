from __future__ import annotations

from typing import Any


def describe_primary_runtime(mode: str, preflight_ready: bool, *, v1_initialized: bool = False, candidate: Any = None, dense: Any = None, expected_candidate_hash: str = "") -> dict[str, Any]:
    """Report existing runtime objects; a health check never initializes a model."""
    candidate_mode = mode in {"V2_6_2_CANDIDATE", "V2_6_1_CANDIDATE", "V2_CANDIDATE"}
    actual_hash = str(getattr(candidate, "candidate_hash", "") or "") if candidate_mode else ""
    model_ready = bool(getattr(dense, "ready", False)) if candidate_mode else v1_initialized
    identity_matches = bool(actual_hash) and (not expected_candidate_hash or actual_hash == expected_candidate_hash) if candidate_mode else True
    initialized = candidate is not None and dense is not None if candidate_mode else v1_initialized
    ready = bool(preflight_ready and initialized and model_ready and identity_matches)
    return {"runtime_mode": mode, "service_ready": ready, "preflight_ready": bool(preflight_ready), "runtime_initialized": bool(initialized), "embedding_model_ready": bool(model_ready), "candidate_hash": actual_hash, "expected_candidate_hash": expected_candidate_hash if candidate_mode else "", "candidate_identity_matches": bool(identity_matches), "runtime_readiness_status": "READY" if ready else "NOT_READY", "readiness_reason": "Ready" if ready else "Preflight failed" if not preflight_ready else "Runtime not initialized" if not initialized else "Candidate identity mismatch" if not identity_matches else "Embedding model not ready"}
