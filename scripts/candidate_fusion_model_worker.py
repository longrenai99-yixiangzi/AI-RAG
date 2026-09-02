from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from app.config import Settings
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("query", "evidence", "rerank"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.phase == "query":
        _queries(args.input, args.output)
    elif args.phase == "evidence":
        _evidence(args.input, args.output)
    else:
        _rerank(args.input, args.output)
    return 0


def _queries(input_path: Path, output_path: Path) -> None:
    settings = Settings.load()
    provider = BGEM3DenseProvider(settings.embedding_model, collection_name="candidate_fusion_v2_worker_query", use_fp16=True, batch_size=1)
    try:
        rows = _read_json(input_path)["records"]
        vectors = {str(row["id"]): provider.embed_query(str(row["question"])) for row in rows}
    finally:
        provider.close()
    _write_json(output_path, {"model": "BGE-M3", "model_path": str(settings.embedding_model), "precision": "fp16", "vectors": vectors, "provider_http_requests": 0, "network_access": False})


def _evidence(input_path: Path, output_path: Path) -> None:
    settings = Settings.load()
    provider = BGEM3DenseProvider(settings.embedding_model, collection_name="candidate_fusion_v2_worker_evidence", use_fp16=True, batch_size=1)
    scores: dict[str, dict[str, float]] = {}
    try:
        for row in _read_jsonl(input_path):
            query = np.asarray(row["query_vector"], dtype=np.float32)
            values: dict[str, float] = {}
            for candidate in row["raw_candidates"]:
                evidence_id = str(candidate.get("evidence_id") or "")
                vector = provider.embed_query(str(candidate.get("text") or "")[:360])
                values[evidence_id] = float(np.dot(query, np.asarray(vector, dtype=np.float32)))
            scores[str(row["question_id"])] = values
    finally:
        provider.close()
    _write_json(output_path, {"model": "BGE-M3", "model_path": str(settings.embedding_model), "precision": "fp16", "scores": scores, "provider_http_requests": 0, "network_access": False})


def _rerank(input_path: Path, output_path: Path) -> None:
    settings = Settings.load()
    reranker = BGERerankerProvider(settings.reranker_model, use_fp16=True, max_length=256)
    scores: dict[str, list[float]] = {}
    try:
        for row in _read_jsonl(input_path):
            scores[str(row["question_id"])] = reranker.score(str(row["question"]), [str(item) for item in row["passages"]]) or []
    finally:
        reranker.close()
    _write_json(output_path, {"model": "bge-reranker-v2-m3", "model_path": str(settings.reranker_model), "precision": "fp16", "scores": scores, "provider_http_requests": 0, "network_access": False})


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
