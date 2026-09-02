from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import select_evidence_optimized
from app.bm25 import BM25Index
from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceClassifier
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.query_analyzer import analyze_query
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.shadow_precision import analyze_precision_intent


ROOT_ID = "Root-002"
COLLECTION = "root002_shadow_bge_m3"
DEFAULT_SHADOW = Path("data") / "shadow" / "root002_import"
DEFAULT_GOLD = Path("tests") / "gold_questions" / "business_acceptance_10.yaml"
SCHEMA_VERSION = "retrieval-trace.v1"
BM25_LIMIT = 20
DENSE_LIMIT = 20
RRF_LIMIT = 20
SELECTION_INPUT_LIMIT = 10
EVIDENCE_LIMIT = 5


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_questions(path: Path) -> list[dict[str, Any]]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = [item for item in payload.get("questions", []) if str(item.get("id", "")).startswith("BA-")]
    expected = {f"BA-{index:03d}" for index in range(1, 11)}
    if {str(item.get("id")) for item in questions} != expected:
        raise ValueError("Gold Dataset 必须完整包含 BA-001 至 BA-010")
    return sorted(questions, key=lambda item: str(item["id"]))


def build_chunks(staging: list[dict[str, Any]]) -> tuple[list[Chunk], dict[str, dict[str, Any]]]:
    chunks: list[Chunk] = []
    metadata_by_chunk: dict[str, dict[str, Any]] = {}
    for document in staging:
        for item in document.get("chunks", []):
            chunk = Chunk(**item)
            chunks.append(chunk)
            metadata_by_chunk[chunk.chunk_id] = dict(
                document.get("chunk_metadata", {}).get(chunk.chunk_id)
                or document.get("metadata", {})
            )
    return chunks, metadata_by_chunk


class ShadowDenseSearch:
    def __init__(self, client: QdrantClient, provider: BGEM3DenseProvider) -> None:
        self.client = client
        self.provider = provider

    def search(self, question: str, limit: int) -> list[tuple[str, float]]:
        vector = self.provider.embed_query(question)
        response = self.client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            (str((point.payload or {}).get("chunk_id") or point.id), float(point.score))
            for point in response.points
        ]


def chunk_ref(chunk: Chunk, score: float, rank: int) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "file_name": chunk.file_name,
        "source_path": chunk.source_path,
        "score": float(score),
        "rank": rank,
    }


def build_selection_trace(
    rrf_hits: list[SearchHit],
    bundle: Any,
    governance_by_chunk: dict[str, Any],
    *,
    rank_offset: int = 0,
) -> list[dict[str, Any]]:
    selected = {item.chunk_id: item for item in bundle.items}
    selected_document_counts = Counter(item.document_id for item in bundle.items)
    rows: list[dict[str, Any]] = []
    for local_index, hit in enumerate(rrf_hits, start=1):
        index = local_index + rank_offset
        chunk = hit.chunk
        governance = governance_by_chunk.get(chunk.chunk_id)
        item = selected.get(chunk.chunk_id)
        if item is not None:
            reason = "selected"
            selection_score = item.selection_score
            source_id = item.source_id
            selected_value = True
        elif index > SELECTION_INPUT_LIMIT:
            reason = "outside_selection_input_top10"
            selection_score = None
            source_id = None
            selected_value = False
        elif selected_document_counts.get(chunk.document_id, 0) >= 2:
            reason = "document_chunk_quota"
            selection_score = None
            source_id = None
            selected_value = False
        elif len(bundle.items) >= EVIDENCE_LIMIT:
            reason = "evidence_limit_or_diversity"
            selection_score = None
            source_id = None
            selected_value = False
        else:
            reason = "document_score_or_role_order"
            selection_score = None
            source_id = None
            selected_value = False
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "rank": index,
                "selected": selected_value,
                "source_id": source_id,
                "selection_score": selection_score,
                "reason": reason,
                "document_role": governance.document_role if governance else None,
                "authority_level": governance.authority_level if governance else None,
                "location": chunk.location,
            }
        )
    return rows


def make_trace(
    question: dict[str, Any],
    chunks_by_id: dict[str, Chunk],
    bm25_pairs: list[tuple[str, float]],
    dense_pairs: list[tuple[str, float]],
    governance_by_chunk: dict[str, Any],
    bundle: Any,
) -> dict[str, Any]:
    query = str(question["question"])
    precision_intent = analyze_precision_intent(query)
    query_analysis = analyze_query(query)
    bm25_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(bm25_pairs, start=1)}
    dense_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(dense_pairs, start=1)}
    bm25_scores = dict(bm25_pairs)
    dense_scores = dict(dense_pairs)
    rrf_candidates = reciprocal_rank_fusion(
        {
            "bm25": [chunk_id for chunk_id, _ in bm25_pairs],
            "dense": [chunk_id for chunk_id, _ in dense_pairs],
        }
    )
    rrf_candidates = rrf_candidates[:RRF_LIMIT]
    rrf_hits = [
        SearchHit(
            chunk=chunks_by_id[candidate.chunk_id],
            score=candidate.score,
            bm25_rank=bm25_ranks.get(candidate.chunk_id),
            dense_rank=dense_ranks.get(candidate.chunk_id),
        )
        for candidate in rrf_candidates
        if candidate.chunk_id in chunks_by_id
    ]
    selection_hits = rrf_hits[:SELECTION_INPUT_LIMIT]
    selection_policy = policy_for_intent(precision_intent.question_type)
    selection_bundle = select_evidence_optimized(
        selection_hits,
        selection_policy,
        governance_by_chunk,
        max_items=EVIDENCE_LIMIT,
    )
    rrf_rows = []
    for rank, candidate in enumerate(rrf_candidates, start=1):
        chunk = chunks_by_id.get(candidate.chunk_id)
        if chunk is None:
            continue
        rrf_rows.append(
            {
                "chunk_id": candidate.chunk_id,
                "rrf_score": float(candidate.score),
                "rank": rank,
                "source_bm25_rank": candidate.ranks.get("bm25"),
                "source_dense_rank": candidate.ranks.get("dense"),
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
                "location": chunk.location,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "task": "TASK-016D-2A",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_root_id": ROOT_ID,
        "question_id": str(question["id"]),
        "question": query,
        "intent": precision_intent.question_type,
        "intent_metadata_hints": precision_intent.metadata_hints,
        "query_analysis": {
            "question_type": query_analysis.question_type,
            "keywords": query_analysis.keywords,
            "metadata": {
                key: {"value": value.value, "confidence": value.confidence}
                for key, value in query_analysis.metadata.items()
            },
        },
        "config": {
            "bm25_limit": BM25_LIMIT,
            "dense_limit": DENSE_LIMIT,
            "rrf_limit": RRF_LIMIT,
            "rrf_rank_constant": 60,
            "selection_input_limit": SELECTION_INPUT_LIMIT,
            "evidence_limit": EVIDENCE_LIMIT,
            "reranker_executed": False,
        },
        "bm25_top20": [
            chunk_ref(chunks_by_id[chunk_id], score, rank)
            for rank, (chunk_id, score) in enumerate(bm25_pairs, start=1)
            if chunk_id in chunks_by_id
        ],
        "dense_top20": [
            chunk_ref(chunks_by_id[chunk_id], score, rank)
            for rank, (chunk_id, score) in enumerate(dense_pairs, start=1)
            if chunk_id in chunks_by_id
        ],
        "rrf_top20": rrf_rows,
        "reranker": {
            "executed": False,
            "items": [],
            "reason": "保持 TASK-016C-3 实际运行口径；本任务不启用或调整 Reranker",
        },
        "evidence_selection": {
            "selection_input": "rrf_top10",
            "selected_count": len(selection_bundle.items),
            "selection_notes": selection_bundle.selection_notes,
            "items": build_selection_trace(selection_hits, selection_bundle, governance_by_chunk)
            + build_selection_trace(
                rrf_hits[SELECTION_INPUT_LIMIT:],
                selection_bundle,
                governance_by_chunk,
                rank_offset=SELECTION_INPUT_LIMIT,
            ),
        },
        "final_evidence": [
            {
                "source_id": item.source_id,
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "file_name": item.file_name,
                "source_path": item.source_path,
                "document_role": item.document_role,
                "authority_level": item.authority_level,
                "location": item.location,
                "excerpt": item.excerpt,
                "selection_score": item.selection_score,
            }
            for item in selection_bundle.items
        ],
    }


def render_report(
    *,
    shadow_dir: Path,
    trace_dir: Path,
    trace_count: int,
    collection_count: int,
    total_bm25: int,
    total_dense: int,
    total_rrf: int,
    total_selected: int,
) -> str:
    return f"""# Retrieval Trace Persistence Design Report

> TASK-016D-2A：在 Shadow 环境补充 BM25、Dense、RRF、Reranker 和 Evidence Selection 逐阶段轨迹持久化。
>
> 本任务只增加评估能力，不修改正式 Retriever 排序逻辑、Evidence Selection、Answer Engine、8000 服务或正式 Qdrant。

## 1. 执行范围

- Knowledge Root：`{ROOT_ID}`
- Shadow 路径：`{shadow_dir.resolve()}`
- Shadow Collection：`{COLLECTION}`
- Shadow Qdrant 当前点数：`{collection_count}`
- 轨迹问题数：`{trace_count}`（BA-001～BA-010）
- Embedding：只调用已存在的 BGE-M3 Shadow 查询能力，不写向量。
- LLM：未调用。
- Reranker：按 C-3 实际口径记录为未执行，不加载、不调参。

## 2. 轨迹 Schema

每题一个 JSON 文件：`evaluation/traces/BA-XXX.json`。

### 2.1 BM25 Top20

字段：`chunk_id`、`document_id`、`file_name`、`source_path`、`score`、`rank`。

### 2.2 Dense Top20

字段：`chunk_id`、`document_id`、`file_name`、`source_path`、`score`、`rank`。

### 2.3 RRF Top20

字段：`chunk_id`、`rrf_score`、`rank`、`source_bm25_rank`、`source_dense_rank`，以及文件和定位字段。

### 2.4 Reranker

字段：`executed`、`items`、`reason`。本批结果为：`executed=false`，`items=[]`。

后续启用 Reranker 时，`items` 使用 `chunk_id`、`score`、`rank`、`document_id`、`file_name`。

### 2.5 Evidence Selection

字段：`selected`、`source_id`、`selection_score`、`reason`，以及文件、角色、权威等级和 location。

当前保持 C-3 口径：RRF Top10 进入 Evidence Selection，最多输出 5 条 Evidence；RRF 第 11～20 名记录为 `outside_selection_input_top10`。

当前 `reason` 是评估脚本基于最终 Bundle 的可解释归因，不改变 Evidence Selection 内部逻辑。若要获得完全精确的内部淘汰原因，未来应让 Selector 原样返回决策事件。

## 3. 本次生成统计

| 指标 | 结果 |
|---|---:|
| 轨迹文件 | {trace_count} |
| 每题 BM25 条目 | {total_bm25 // max(trace_count, 1)} |
| 每题 Dense 条目 | {total_dense // max(trace_count, 1)} |
| 每题 RRF 条目 | {total_rrf // max(trace_count, 1)} |
| Evidence Selection 选中总数 | {total_selected} |
| 正式 Qdrant 写入 | 0 |

## 4. 使用方式

1. 先看 `bm25_top20` 与 `dense_top20` 是否包含 Gold 文件或 Gold Chunk；
2. 再看 `rrf_top20` 是否把 Gold Chunk 融合到前 10；
3. 再看 `reranker.executed`，避免把未运行的 Reranker 当作失败原因；
4. 最后看 `evidence_selection.items` 的 `selected` 与 `reason`；
5. 对 `GOLD_OUT_OF_SCOPE` 问题，不把未命中当前 Root 误判为排序失败。

## 5. 验收标准

- 每题存在 BM25 Top20、Dense Top20、RRF Top20；
- 每个 RRF 条目可回溯 BM25/Dense 来源排名；
- 每个 RRF Top20 条目都有 Evidence Selection selected/reason；
- Reranker 是否执行明确记录；
- Source path、file name、document id、chunk id、location 可回查；
- 轨迹目录不被正式服务读取，不写正式 Qdrant。

## 6. 后续用途

该轨迹为 TASK-016D-2B 的 Evidence Ranking Shadow A/B 对比提供输入。后续可以逐题回答：

- Gold Chunk 是否被 BM25 找到；
- Dense 是否补回 BM25 未命中的 Chunk；
- RRF 是否把正确 Chunk 推进 Top10；
- Reranker 是否实际参与；
- Evidence Selection 在哪一步淘汰了正确证据。

"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist Shadow retrieval traces for BA-001 to BA-010")
    parser.add_argument("--shadow-dir", type=Path, default=DEFAULT_SHADOW)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    args = parser.parse_args()

    staging = read_jsonl(args.shadow_dir / "pipeline_staging.jsonl")
    chunks, metadata_by_chunk = build_chunks(staging)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    questions = load_questions(args.gold)
    client = QdrantClient(path=str(args.shadow_dir / "qdrant"))
    collection_count = client.count(collection_name=COLLECTION, exact=True).count
    bm25 = BM25Index(args.shadow_dir / "root002_trace_bm25_runtime.json")
    bm25.build(chunks)
    provider = BGEM3DenseProvider(
        PROJECT_ROOT / "models" / "bge-m3",
        collection_name=COLLECTION,
        use_fp16=True,
        batch_size=4,
    )
    provider.load()
    dense = ShadowDenseSearch(client, provider)
    classifier = GovernanceClassifier()
    governance_by_chunk = {
        chunk.chunk_id: classifier.classify(
            file_name=chunk.file_name,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
            metadata=metadata_by_chunk.get(chunk.chunk_id, {}),
        )
        for chunk in chunks
    }
    trace_dir = PROJECT_ROOT / "evaluation" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    total_bm25 = total_dense = total_rrf = total_selected = 0
    try:
        for index, question in enumerate(questions, start=1):
            analysis = analyze_query(str(question["question"]))
            bm25_pairs = bm25.search(analysis.search_text, limit=BM25_LIMIT)
            dense_pairs = dense.search(str(question["question"]), limit=DENSE_LIMIT)
            trace = make_trace(
                question,
                chunks_by_id,
                bm25_pairs,
                dense_pairs,
                governance_by_chunk,
                bundle=None,
            )
            trace_path = trace_dir / f"{question['id']}.json"
            write_json(trace_path, trace)
            total_bm25 += len(trace["bm25_top20"])
            total_dense += len(trace["dense_top20"])
            total_rrf += len(trace["rrf_top20"])
            total_selected += trace["evidence_selection"]["selected_count"]
            print(f"trace_progress={index}/{len(questions)}", flush=True)
    finally:
        provider.close()
        client.close()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "task": "TASK-016D-2A",
        "knowledge_root_id": ROOT_ID,
        "shadow_dir": str(args.shadow_dir.resolve()),
        "collection": COLLECTION,
        "collection_points": collection_count,
        "model_path": str(PROJECT_ROOT / "models" / "bge-m3"),
        "torch_note": "Model execution uses the existing CUDA environment; no environment change was made.",
        "reranker_executed": False,
        "trace_files": [f"BA-{index:03d}.json" for index in range(1, 11)],
    }
    write_json(trace_dir / "manifest.json", manifest)
    report = render_report(
        shadow_dir=args.shadow_dir,
        trace_dir=trace_dir,
        trace_count=len(questions),
        collection_count=collection_count,
        total_bm25=total_bm25,
        total_dense=total_dense,
        total_rrf=total_rrf,
        total_selected=total_selected,
    )
    report_path = PROJECT_ROOT / "docs" / "RETRIEVAL_TRACE_DESIGN_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"trace_dir": str(trace_dir), "report": str(report_path), "collection_points": collection_count}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
