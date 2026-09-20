"""T05 - 真实 BGE / Reranker 检索能力审计（P0）。

用本地 models/bge-m3 与 models/bge-reranker-v2-m3 **真实运行**四种检索方式：

    A. BM25 / Lexical Only
    B. Dense Only（复用已落盘的真实 BGE-M3 向量，不重算语料）
    C. Lexical + Dense（RRF 融合）
    D. Lexical + Dense + Reranker（对融合 Top30 用真实 reranker 重排）

相同问题、相同来源版本、相同索引、相同候选预算。

输出：
    evaluation/knowledge_os_system_audit/t05/retrieval_model_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t05"
SECTION_DIR = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "section_index"
GOLD_PATH = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
BGE_PATH = ROOT / "models" / "bge-m3"
RERANKER_PATH = ROOT / "models" / "bge-reranker-v2-m3"

RRF_K = 60
POOL = 100
RERANK_POOL = 30

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_gold(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for q in data.get("questions") or []:
        files = [str(f).strip() for f in (q.get("expected_files") or []) if str(f).strip()]
        if q.get("question") and files:
            rows.append(
                {
                    "id": q.get("id"),
                    "topic": q.get("topic"),
                    "question": q.get("question"),
                    "expected_files": files,
                    "difficulty": q.get("difficulty"),
                }
            )
    return rows


def load_sections() -> tuple[list[dict], np.ndarray]:
    records = [
        json.loads(line)
        for line in (SECTION_DIR / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    vectors = np.load(SECTION_DIR / "vectors.npy")
    if len(records) != vectors.shape[0]:
        raise SystemExit(
            f"records({len(records)}) 与 vectors({vectors.shape[0]}) 数量不一致，终止以避免错误结论"
        )
    return records, vectors.astype(np.float32)


def build_bm25(records: list[dict]):
    from rank_bm25 import BM25Okapi

    from app.bm25 import tokenize

    corpus = [tokenize(str(r.get("section_search_text") or "")) or ["_empty_"] for r in records]
    return BM25Okapi(corpus), tokenize


def recall_at(ranks: list[int], k: int) -> float:
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if 1 <= r <= k) / len(ranks)


def mrr(ranks: list[int]) -> float:
    vals = [1.0 / r for r in ranks if r and r > 0]
    return sum(vals) / len(ranks) if vals else 0.0


def ndcg_at(per_question_hits: list[list[bool]], k: int) -> float:
    """binary relevance 的 nDCG@k。"""
    total = 0.0
    for hits in per_question_hits:
        dcg = sum(1.0 / np.log2(i + 2) for i, h in enumerate(hits[:k]) if h)
        ideal = sum(1.0 / np.log2(i + 2) for i in range(min(k, sum(hits))))
        total += dcg / ideal if ideal > 0 else 0.0
    return total / len(per_question_hits) if per_question_hits else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题，0 表示全部")
    parser.add_argument("--skip-reranker", action="store_true", help="跳过 D 组 reranker")
    parser.add_argument("--verify-align", type=int, default=3, help="向量对齐实证校验抽样数")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    log("加载 section 索引与真实向量 ...")
    records, vectors = load_sections()
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors_normed = vectors / norms
    log(f"  sections={len(records)} dim={vectors.shape[1]}")

    gold = load_gold(GOLD_PATH)
    if args.limit:
        gold = gold[: args.limit]
    log(f"  问题数={len(gold)}")

    # ground truth 覆盖率（先确认评估可行）
    file_names = {str(r.get("file_name") or "") for r in records}
    covered = [q for q in gold if any(f in file_names for f in q["expected_files"])]
    log(f"  ground truth 可在 section 级命中的问题={len(covered)}/{len(gold)}")
    if not covered:
        log("  没有可评估问题，终止")
        return 1

    log("构建 BM25 ...")
    bm25, tokenize = build_bm25(records)

    log("加载真实 BGE-M3（CPU）...")
    from FlagEmbedding import BGEM3FlagModel

    bge = BGEM3FlagModel(str(BGE_PATH), use_fp16=False)

    # ---- 向量来源统计（审计发现，非校验）----
    source_counter: dict[str, int] = defaultdict(int)
    for r in records:
        source_counter[str(r.get("dense_vector_source") or "<none>")] += 1
    fallback = source_counter.get("PARENT_DOCUMENT_FALLBACK", 0)
    per_doc_counter: dict[str, int] = defaultdict(int)
    for r in records:
        per_doc_counter[str(r.get("file_name") or "<none>")] += 1
    size_counter: dict[int, int] = defaultdict(int)
    for n in per_doc_counter.values():
        size_counter[min(n, 10)] += 1
    section_size_distribution = dict(size_counter)
    log(f"  dense 向量来源分布={dict(source_counter)}")
    if fallback:
        log(f"  注意：{fallback} 条({fallback / len(records):.1%}) section 使用父文档向量，"
            f"同文档内多个 section 共享同一向量，dense 无法区分")

    # ---- 向量对齐实证校验：防止 vectors.npy 与 records.jsonl 错位 ----
    if args.verify_align > 0:
        log("实证校验向量与记录对齐 ...")
        # 只对 SECTION_DIRECT 校验：PARENT_DOCUMENT_FALLBACK 本就不是自身文本编码
        direct_idx = [
            i for i, r in enumerate(records)
            if str(r.get("dense_vector_source")) == "SECTION_DIRECT"
        ]
        if not direct_idx:
            log("  没有 SECTION_DIRECT 样本，跳过对齐校验")
        else:
            idxs = [
                direct_idx[int(x)]
                for x in np.linspace(0, len(direct_idx) - 1, min(args.verify_align, len(direct_idx)))
            ]
            sims = []
            for i in idxs:
                best = 0.0
                for field in ("section_search_text", "section_content_text"):
                    text = str(records[i].get(field) or "")[:1024]
                    if not text.strip():
                        continue
                    v = bge.encode([text], max_length=1024, return_dense=True, return_sparse=False, return_colbert_vecs=False)["dense_vecs"][0]
                    v = np.asarray(v, dtype=np.float32)
                    cos = float(np.dot(v, vectors[i]) / (np.linalg.norm(v) * np.linalg.norm(vectors[i]) + 1e-9))
                    best = max(best, cos)
                sims.append(round(best, 4))
            log(f"  SECTION_DIRECT 对齐余弦相似度={sims}")
            if not all(s > 0.85 for s in sims):
                log("  对齐校验未通过，终止以避免错误结论")
                return 1
            log("  对齐校验通过")

    log("编码 query ...")
    started = time.perf_counter()
    qvecs = bge.encode(
        [q["question"] for q in covered],
        batch_size=8,
        max_length=1024,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )["dense_vecs"]
    qvecs = np.asarray(qvecs, dtype=np.float32)
    qnorms = np.linalg.norm(qvecs, axis=1, keepdims=True)
    qnorms[qnorms == 0] = 1.0
    qvecs = qvecs / qnorms
    log(f"  query 编码完成 {qvecs.shape}，用时 {time.perf_counter() - started:.1f}s")

    reranker = None
    if not args.skip_reranker:
        log("加载真实 bge-reranker-v2-m3（CPU）...")
        try:
            # 复用项目封装：内部处理 tokenizer 兼容性问题
            from app.retrieval.reranker_provider import BGERerankerProvider

            reranker = BGERerankerProvider(str(RERANKER_PATH), use_fp16=False)
            reranker.load()
            log("  reranker 就绪")
        except Exception as exc:
            log(f"  reranker 加载失败，D 组将标记为 NOT_RUN：{exc}")

    results = {
        "A_LEXICAL": {"ranks": [], "hits": [], "details": []},
        "B_DENSE": {"ranks": [], "hits": [], "details": []},
        "C_HYBRID": {"ranks": [], "hits": [], "details": []},
        "D_RERANK": {"ranks": [], "hits": [], "details": []},
    }
    rerank_inputs = []

    for qi, q in enumerate(covered):
        expected = set(q["expected_files"])

        # A. Lexical
        lex_scores = bm25.get_scores(tokenize(q["question"]) or ["_empty_"])
        lex_order = np.argsort(-lex_scores)[:POOL]
        lex_rankmap = {int(i): r + 1 for r, i in enumerate(lex_order)}

        # B. Dense
        dense_scores = vectors_normed @ qvecs[qi]
        dense_order = np.argsort(-dense_scores)[:POOL]
        dense_rankmap = {int(i): r + 1 for r, i in enumerate(dense_order)}

        # C. RRF
        rrf_scores: dict[int, float] = defaultdict(float)
        for i, r in lex_rankmap.items():
            rrf_scores[i] += 1.0 / (RRF_K + r)
        for i, r in dense_rankmap.items():
            rrf_scores[i] += 1.0 / (RRF_K + r)
        hybrid_order = sorted(rrf_scores, key=lambda i: -rrf_scores[i])[:POOL]
        rerank_inputs.append({"question_id": q["id"], "question": q["question"], "expected_files": q["expected_files"], "section_indices": hybrid_order[:RERANK_POOL]})

        def first_hit(order) -> int:
            for pos, i in enumerate(order, start=1):
                if str(records[i].get("file_name") or "") in expected:
                    return pos
            return 0

        def hit_flags(order, k=20) -> list[bool]:
            return [
                str(records[i].get("file_name") or "") in expected for i in list(order)[:k]
            ]

        for name, order in (
            ("A_LEXICAL", list(lex_order)),
            ("B_DENSE", list(dense_order)),
            ("C_HYBRID", hybrid_order),
        ):
            results[name]["ranks"].append(first_hit(order))
            results[name]["hits"].append(hit_flags(order))
            results[name]["details"].append(
                {
                    "question_id": q["id"],
                    "question": q["question"],
                    "expected_files": q["expected_files"],
                    "first_hit_rank": first_hit(order),
                    "top_files": [
                        str(records[i].get("file_name") or "") for i in list(order)[:5]
                    ],
                }
            )

        # D. Reranker
        if reranker is not None:
            pool = hybrid_order[:RERANK_POOL]
            passages = [str(records[i].get("section_content_text") or records[i].get("section_search_text") or "")[:512] for i in pool]
            try:
                scores = reranker.score(q["question"], passages)
                if scores is None:
                    raise RuntimeError("reranker 返回 None")
                if isinstance(scores, float):
                    scores = [scores]
                order = [i for _, i in sorted(zip(scores, pool), key=lambda x: -x[0])]
            except Exception as exc:
                log(f"  [warn] reranker 在第 {qi + 1} 题失败，退回融合顺序：{exc}")
                order = list(pool)
            results["D_RERANK"]["ranks"].append(first_hit(order))
            results["D_RERANK"]["hits"].append(hit_flags(order))
            results["D_RERANK"]["details"].append(
                {
                    "question_id": q["id"],
                    "question": q["question"],
                    "expected_files": q["expected_files"],
                    "first_hit_rank": first_hit(order),
                    "top_files": [str(records[i].get("file_name") or "") for i in order[:5]],
                }
            )
        else:
            results["D_RERANK"]["ranks"].append(0)
            results["D_RERANK"]["hits"].append([])

        if (qi + 1) % 10 == 0:
            log(f"  已完成 {qi + 1}/{len(covered)}")

    metrics = {}
    for name, data in results.items():
        ranks = data["ranks"]
        if name == "D_RERANK" and reranker is None:
            metrics[name] = {"status": "NOT_RUN", "reason": "reranker 未加载"}
            continue
        hits = [h for h in data["hits"] if h]
        metrics[name] = {
            "status": "RUN",
            "evaluated_questions": len(ranks),
            "recall@5": round(recall_at(ranks, 5), 4),
            "recall@10": round(recall_at(ranks, 10), 4),
            "recall@20": round(recall_at(ranks, 20), 4),
            "mrr": round(mrr(ranks), 4),
            "ndcg@10": round(ndcg_at(hits, 10), 4),
            "rerank@5_hit_rate": round(recall_at(ranks, 5), 4),
            "miss_count": sum(1 for r in ranks if r == 0),
        }

    failures = []
    for qi, q in enumerate(covered):
        row = {
            "question_id": q["id"],
            "question": q["question"],
            "expected_files": q["expected_files"],
            "lexical_rank": results["A_LEXICAL"]["ranks"][qi],
            "dense_rank": results["B_DENSE"]["ranks"][qi],
            "hybrid_rank": results["C_HYBRID"]["ranks"][qi],
            "reranker_rank": results["D_RERANK"]["ranks"][qi],
        }
        if results["C_HYBRID"]["ranks"][qi] == 0:
            failures.append(row)

    payload = {
        "task": "T05_REAL_MODEL_RETRIEVAL_AUDIT",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "mode": "REAL_MODEL_RUN",
        "environment": {
            "bge_model": str(BGE_PATH),
            "reranker_model": str(RERANKER_PATH),
            "device": "CPU (CUDA unavailable)",
            "corpus": "section_index (真实 BGE-M3 向量复用，未重算)",
        },
        "setup": {
            "questions_total": len(gold),
            "questions_evaluated": len(covered),
            "rrf_k": RRF_K,
            "candidate_pool": POOL,
            "rerank_pool": RERANK_POOL,
            "ground_truth": "expected_files 命中 file_name 即视为相关",
        },
        "corpus_audit": {
            "section_total": len(records),
            "dense_vector_source_distribution": dict(source_counter),
            "parent_document_fallback_rate": round(fallback / len(records), 4) if records else 0,
            "note": "PARENT_DOCUMENT_FALLBACK 的 section 与同文档其他 section 共享向量，dense 阶段不可区分",
            "sections_per_document": {
                "document_count": len(per_doc_counter),
                "distribution": {
                    ("10+" if k >= 10 else str(k)): v
                    for k, v in sorted(section_size_distribution.items())
                },
                "documents_with_le_2_sections": sum(
                    v for k, v in section_size_distribution.items() if k <= 2
                ),
                "documents_with_le_2_ratio": round(
                    sum(v for k, v in section_size_distribution.items() if k <= 2)
                    / max(1, len(per_doc_counter)),
                    4,
                ),
            },
        },
        "metrics": metrics,
        "recall_miss_cases": failures,
        "per_question": [
            {
                "question_id": q["id"],
                "question": q["question"],
                "lexical_rank": results["A_LEXICAL"]["ranks"][i],
                "dense_rank": results["B_DENSE"]["ranks"][i],
                "hybrid_rank": results["C_HYBRID"]["ranks"][i],
                "reranker_rank": results["D_RERANK"]["ranks"][i],
            }
            for i, q in enumerate(covered)
        ],
    }
    (OUT / "retrieval_model_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "rerank_inputs.json").write_text(json.dumps(rerank_inputs, ensure_ascii=False), encoding="utf-8")

    log("")
    log("===== T05 真实模型检索能力 =====")
    for name, m in metrics.items():
        if m.get("status") != "RUN":
            log(f"  {name}: {m.get('status')} ({m.get('reason','')})")
            continue
        log(
            f"  {name:<10} R@5={m['recall@5']:.3f}  R@10={m['recall@10']:.3f}  "
            f"R@20={m['recall@20']:.3f}  MRR={m['mrr']:.3f}  nDCG@10={m['ndcg@10']:.3f}  miss={m['miss_count']}"
        )
    log(f"  输出: {OUT / 'retrieval_model_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
