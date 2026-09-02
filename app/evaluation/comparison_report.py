from __future__ import annotations

from app.evaluation.retrieval_evaluator import FullCorpusEvaluation


def render_full_corpus_report(result: FullCorpusEvaluation) -> str:
    rows = [
        "# Full Corpus Retrieval Evaluation",
        "",
        "> 本报告评估 Document Pipeline + BGE-M3 + Shadow Qdrant + BM25/RRF/Reranker。",
        "> Gold 文件仍为候选标注，指标在人工复核 expected_files 前属于 provisional。",
        "",
        "## Corpus 与 Gold 摘要",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 知识源文件数 | {result.corpus_files} |",
        f"| Pipeline 文档数 | {result.corpus_documents} |",
        f"| Chunk 数 | {result.corpus_chunks} |",
        f"| Metadata 基础完整 Chunk | {result.metadata_complete_chunks} |",
        f"| location 完整 Chunk | {result.location_complete_chunks} |",
        f"| Gold Questions | {result.gold_questions} |",
        f"| Gold 状态 | `{result.gold_status}` |",
        "",
        "## 指标对比",
        "",
        "| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation 完整率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in result.modes.items():
        rows.append(
            f"| {name} | {metrics.recall_at_1:.2%} | {metrics.recall_at_3:.2%} | "
            f"{metrics.recall_at_5:.2%} | {metrics.mrr:.3f} | {metrics.citation_completeness:.2%} |"
        )
    rows.extend(
        [
            "",
            "## 失败问题摘要",
            "",
            "| 模式 | 未命中问题数 | 示例 |",
            "|---|---:|---|",
        ]
    )
    for name, metrics in result.modes.items():
        examples = "；".join(item["id"] for item in metrics.failures[:8]) or "无"
        rows.append(f"| {name} | {len(metrics.failures)} | {examples} |")
    rows.extend(
        [
            "",
            "## 解释边界",
            "",
            "- BM25 失败但 Hybrid 命中的问题，需要通过 Dense 语义召回记录确认；",
            "- Hybrid 失败但 Hybrid+Reranker 命中的问题，需要通过重排前后 rank 变化确认；",
            "- Metadata 效果必须单独记录过滤前后候选数，不能仅凭最终 Recall 判断；",
            "- 当前 Gold expected_files 为候选标注，正式结论必须经过内容负责人复核。",
            "",
        ]
    )
    return "\n".join(rows)
