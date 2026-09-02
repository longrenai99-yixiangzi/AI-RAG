from __future__ import annotations

from app.ingestion.shadow.comparison import ShadowComparison


def render_shadow_markdown(comparison: ShadowComparison) -> str:
    """Render a deterministic Markdown report without writing it to disk."""

    rows = [
        "# Shadow Index Pipeline 验证报告",
        "",
        "> 本报告由新 Document Engine 旁路结果与旧 Parser 只读投影比较生成。",
        "> 未调用旧 indexer，不生成 Embedding，不写入 Qdrant。",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 新 Pipeline 文档数 | {comparison.new_document_count} |",
        f"| 旧 Parser 文档数 | {comparison.legacy_document_count} |",
        f"| 新 Pipeline Chunk 数 | {comparison.new_chunk_count} |",
        f"| 旧 Parser Chunk 数 | {comparison.legacy_chunk_count} |",
        f"| 稳定 chunk_id 数 | {comparison.stable_chunk_id_count} |",
        f"| chunk_id 稳定率 | {comparison.chunk_id_stability_rate:.2%} |",
        f"| source_path 文件级匹配数 | {comparison.source_path_document_match_count} |",
        f"| source_path 文件级匹配率 | {comparison.source_path_document_match_rate:.2%} |",
        f"| source_path 匹配率（稳定 ID） | {comparison.source_path_match_rate:.2%} |",
        f"| 新 location 完整数 | {comparison.new_location_complete_count} |",
        f"| 旧 location 完整数 | {comparison.legacy_location_complete_count} |",
        f"| 新 Metadata 完整数 | {comparison.new_metadata_complete_count} |",
        f"| 新 Metadata 覆盖率 | {comparison.new_metadata_coverage_rate:.2%} |",
        f"| 新异常文件数 | {comparison.new_exception_file_count} |",
        f"| 旧异常文件数 | {comparison.legacy_exception_file_count} |",
        f"| Adapter Qdrant payload 数 | {comparison.adapter_qdrant_payload_count} |",
        f"| Adapter BM25 record 数 | {comparison.adapter_bm25_record_count} |",
        "",
        "## 文件明细",
        "",
        "| 文件 | 新状态 | 旧状态 | 新 Chunk | 旧 Chunk | 稳定 ID |",
        "|---|---|---|---:|---:|---:|",
    ]
    rows.extend(
        f"| `{item['path']}` | {item['new_status']} | {item['legacy_status']} | "
        f"{item['new_chunks']} | {item['legacy_chunks']} | {item['stable_chunk_ids']} |"
        for item in comparison.per_file
    )
    return "\n".join(rows) + "\n"
