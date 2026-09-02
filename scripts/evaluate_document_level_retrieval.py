from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient
from rank_bm25 import BM25Okapi

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.answer_response import build_shadow_response
from app.answer_engine.citation_map import build_citation_map
from app.answer_engine.evidence_selector import select_evidence_optimized
from app.answer_engine.evaluation.evidence_quality import evaluate_evidence_quality
from app.bm25 import BM25Index, tokenize
from app.config import Settings
from app.evaluation.gold_dataset_loader import load_gold_questions
from app.ingestion.metadata.governance import GovernanceClassifier
from app.document_intelligence.profile_retriever import DocumentProfileRetriever
from app.domain import SearchHit
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import MockDenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider
from app.retrieval.shadow_precision import analyze_precision_intent
from scripts.evaluate_precision_optimization import _run_candidates
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Document-level Retrieval in Shadow.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--profile-limit", type=int, default=30)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; document-level evaluation stopped.")
        return 2

    questions = load_gold_questions(args.gold, minimum=100)
    client = QdrantClient(path=str(args.shadow_dir))
    collection_count = client.count(COLLECTION_NAME, exact=True).count
    chunks, metadata_by_chunk = _load_shadow_chunks(client)
    client.close()
    if collection_count != len(chunks):
        raise RuntimeError(
            f"Shadow Collection count mismatch: qdrant={collection_count}, payload={len(chunks)}"
        )

    profile_path = args.shadow_dir / "document_profiles.jsonl"
    profile_retriever = DocumentProfileRetriever.from_jsonl(profile_path)
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
    chunks_by_document: dict[str, list[Any]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(chunk.document_id, []).append(chunk)
    bm25 = BM25Index(Path("data") / "shadow" / "document_level_eval_bm25.json")
    bm25.build(chunks)

    dense = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name=COLLECTION_NAME,
        use_fp16=True,
        batch_size=16,
    )
    dense.client.close()
    dense.client = QdrantClient(path=str(args.shadow_dir))
    dense.load()
    dense_map: dict[str, list[tuple[str, float]]] = {}
    query_started = time.perf_counter()
    for index, question in enumerate(questions, start=1):
        dense_map[question.question] = dense.search(question.question, limit=20)
        if index == 1 or index % 10 == 0 or index == len(questions):
            print(f"dense_query_progress={index}/{len(questions)}", flush=True)
    query_elapsed = time.perf_counter() - query_started

    reranker = BGERerankerProvider(settings.reranker_model, use_fp16=True)
    rerank_started = time.perf_counter()
    baseline_candidates = _run_candidates(
        bm25,
        chunks,
        questions,
        MockDenseProvider(dense_map),
        reranker=reranker,
    )
    baseline_rerank_elapsed = time.perf_counter() - rerank_started

    baseline_responses = []
    new_responses = []
    profile_file_hits = 0
    candidate_counts: list[int] = []
    for question, baseline_hits in zip(questions, baseline_candidates, strict=True):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        baseline_bundle = select_evidence_optimized(
            baseline_hits,
            policy,
            governance_by_chunk,
            max_items=5,
        )
        baseline_map = build_citation_map(baseline_bundle)
        baseline_responses.append(
            build_shadow_response(question.question, policy, baseline_bundle, baseline_map)
        )

        profile_candidates = profile_retriever.search(
            question.question,
            policy,
            limit=args.profile_limit,
        )
        candidate_ids = {item.document_id for item in profile_candidates}
        candidate_counts.append(len(candidate_ids))
        profile_names = {item.document_name.casefold() for item in profile_candidates}
        profile_file_hits += int(
            any(
                expected.casefold() in profile_names
                for expected in question.expected_files
            )
        )
        profile_scores = {
            item.document_id: item.score for item in profile_candidates
        }
        internal_hits = _retrieve_inside_documents(
            question.question,
            candidate_ids,
            profile_scores,
            chunks_by_document,
            reranker,
        )
        new_bundle = select_evidence_optimized(
            internal_hits,
            policy,
            governance_by_chunk,
            max_items=5,
        )
        new_map = build_citation_map(new_bundle)
        new_responses.append(
            build_shadow_response(question.question, policy, new_bundle, new_map)
        )

    new_rerank_elapsed = time.perf_counter() - rerank_started
    reranker.close()
    dense.close()

    baseline_quality = evaluate_evidence_quality(questions, baseline_responses)
    new_quality = evaluate_evidence_quality(questions, new_responses)
    report = {
        "summary": {
            "gold_questions": len(questions),
            "shadow_collection_points": collection_count,
            "shadow_chunks": len(chunks),
            "profile_count": len(profile_retriever.profiles),
            "profile_limit": args.profile_limit,
            "profile_candidate_expected_file_rate": profile_file_hits / len(questions),
            "average_candidate_document_count": sum(candidate_counts) / len(candidate_counts),
            "query_elapsed_seconds": round(query_elapsed, 3),
            "baseline_rerank_elapsed_seconds": round(baseline_rerank_elapsed, 3),
            "document_chunk_rerank_elapsed_seconds": round(new_rerank_elapsed, 3),
            "llm_calls": 0,
            "baseline": baseline_quality.summary(),
            "new": new_quality.summary(),
            "intent_counts": dict(Counter(analyze_precision_intent(q.question).question_type for q in questions)),
        },
        "new_confusions": [
            item.to_dict() for item in new_quality.questions if item.confusion
        ],
    }
    report_path = Path("docs") / "DOCUMENT_LEVEL_RETRIEVAL_EVALUATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _build_bm25(chunks: list[Any]) -> BM25Okapi:
    return BM25Okapi([tokenize(f"{chunk.heading_path} {chunk.text}") or ["_empty_"] for chunk in chunks])


def _retrieve_inside_documents(
    question: str,
    candidate_ids: set[str],
    profile_scores: dict[str, float],
    chunks_by_document: dict[str, list[Any]],
    reranker: BGERerankerProvider,
) -> list[SearchHit]:
    candidates = [
        chunk
        for document_id in candidate_ids
        for chunk in chunks_by_document.get(document_id, [])
    ]
    if not candidates:
        return []
    corpus = [tokenize(f"{chunk.heading_path} {chunk.text}") or ["_empty_"] for chunk in candidates]
    model = BM25Okapi(corpus)
    query_terms = tokenize(question) or ["_empty_"]
    scores = model.get_scores(query_terms)
    max_score = max(scores) if len(scores) else 0.0
    ranked_indexes = sorted(
        range(len(candidates)),
        key=lambda index: (-float(scores[index]), candidates[index].chunk_id),
    )[:20]
    hits = [
        SearchHit(
            chunk=candidates[index],
            score=0.7 * (float(scores[index]) / max_score if max_score > 0 else 0.0)
            + 0.3 * profile_scores.get(candidates[index].document_id, 0.0),
            bm25_rank=rank,
        )
        for rank, index in enumerate(ranked_indexes, start=1)
    ]
    rerank_scores = reranker.score(question, [hit.chunk.text for hit in hits])
    if rerank_scores is not None:
        for hit, score in zip(hits, rerank_scores, strict=True):
            hit.reranker_score = score
        hits.sort(
            key=lambda hit: (
                -(hit.reranker_score if hit.reranker_score is not None else hit.score),
                hit.chunk.chunk_id,
            )
        )
    return hits


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    baseline = summary["baseline"]
    new = summary["new"]
    lines = [
        "# Document-level Retrieval Evaluation Report",
        "",
        "> 本报告比较 TASK-014C Evidence Ranking 基线与 Document Profile Retrieval + Evidence Ranking。",
        "> 不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. Shadow 流程",
        "",
        "Baseline：全库 Chunk Retrieval → Evidence Ranking。",
        "",
        "New：Document Profile Retrieval → Candidate Documents → 文档内部 Chunk Retrieval → Evidence Ranking。",
        "",
        "Document Profile Retrieval 仅使用 Profile 的 document_name、document_role、authority_level、scope、contains_topics 和相关限制字段；没有硬过滤，候选为空时保留回退空间。",
        "",
        "## 2. 评估范围",
        "",
        f"- Gold Questions：{summary['gold_questions']}。",
        f"- Shadow Collection：{summary['shadow_collection_points']} 点；Shadow Chunk：{summary['shadow_chunks']}。",
        f"- Document Profile：{summary['profile_count']} 个；每题候选文档上限：{summary['profile_limit']}。",
        f"- Profile 候选 expected_file 覆盖率：{summary['profile_candidate_expected_file_rate']:.2%}。",
        f"- 平均候选文档数：{summary['average_candidate_document_count']:.2f}。",
        f"- LLM 调用次数：{summary['llm_calls']}。",
        "",
        "## 3. 核心指标",
        "",
        "| 指标 | TASK-014C Baseline | Document-level New |",
        "|---|---:|---:|",
        f"| Expected File Hit Rate | {baseline['expected_file_hit_rate']:.2%} | {new['expected_file_hit_rate']:.2%} |",
        f"| Role Match Top-1 | {baseline['role_top1_match_rate']:.2%} | {new['role_top1_match_rate']:.2%} |",
        f"| Role Match Top-5 | {baseline['role_any_match_rate']:.2%} | {new['role_any_match_rate']:.2%} |",
        f"| Authority Match Top-1 | {baseline['authority_top1_match_rate']:.2%} | {new['authority_top1_match_rate']:.2%} |",
        f"| Authority Match Top-5 | {baseline['authority_any_match_rate']:.2%} | {new['authority_any_match_rate']:.2%} |",
        f"| Intent-Evidence Top-1 | {baseline['intent_top1_match_rate']:.2%} | {new['intent_top1_match_rate']:.2%} |",
        f"| Intent-Evidence Top-5 | {baseline['intent_any_match_rate']:.2%} | {new['intent_any_match_rate']:.2%} |",
        f"| 制度/案例/模板混淆率 | {baseline['confusion_rate']:.2%} | {new['confusion_rate']:.2%} |",
        "",
        "## 4. 按 Intent 对比",
        "",
        "| Intent | Baseline Expected File | New Expected File | Baseline Role Top-1 | New Role Top-1 | Baseline Intent Top-1 | New Intent Top-1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for intent in sorted(set(baseline["by_intent"]) | set(new["by_intent"])):
        before = baseline["by_intent"].get(intent, {})
        after = new["by_intent"].get(intent, {})
        lines.append(
            f"| {intent} | {before.get('expected_file_hit_rate', 0):.2%} | "
            f"{after.get('expected_file_hit_rate', 0):.2%} | "
            f"{before.get('role_top1_match_rate', 0):.2%} | "
            f"{after.get('role_top1_match_rate', 0):.2%} | "
            f"{before.get('intent_top1_match_rate', 0):.2%} | "
            f"{after.get('intent_top1_match_rate', 0):.2%} |"
        )
    lines.extend(
        [
            "",
            "重点关注：POLICY_QUERY、TEMPLATE_QUERY、CASE_QUERY 的 Expected File Hit Rate 和 Role Match。",
            "",
            "## 5. 结论与边界",
            "",
            "1. Document Profile Retrieval 的价值应以 Expected File Hit Rate 为主要判断，不应只看角色匹配率。",
            "2. 如果角色匹配提升但 Expected File Hit Rate 下降，说明 Profile 只改善了文档类别判断，没有解决具体文件主题和范围对齐。",
            "3. 如果新流程出现候选文档为空，应回退到全库 Chunk Retrieval，不能造成零召回。",
            "4. 本次新流程只在 Shadow 环境运行，未修改正式 Retriever，也未写入正式 Qdrant。",
            "",
            "**TASK-014F：Document-level Retrieval Shadow Evaluation 完成。**",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
