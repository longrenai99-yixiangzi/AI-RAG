from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    reports = sorted(Path("data/reports").glob("retrieval-sample-*.json"))
    if not reports:
        raise FileNotFoundError("retrieval sample report not found")
    source = reports[-1]
    payload = json.loads(source.read_text(encoding="utf-8"))
    lines = [
        "# RAG 22份样本：Reranker 精排人工复核表",
        "",
        "请对每个最终 Top8 结果填写：`相关`、`部分相关` 或 `不相关`。",
        "本报告只验证检索，不调用 LLM；Reranker 当前关闭。RRF原始分数仅是融合信号，最终排序还包含来源路由加权和同文件去重。不要把文件名相似直接判为相关，应打开原文核对内容。",
        "",
        f"- 文档数：{payload.get('documents')}；Chunk 数：{payload.get('chunks')}；Qdrant 点数：{payload.get('qdrant_points')}",
        "- 复核结论：由业务人员根据原文证据填写。",
        "",
    ]
    for index, result in enumerate(payload["results"], 1):
        lines.extend([
            f"## 问题 {index}",
            "",
            f"> {result['question']}",
            "",
            "| 最终排名 | 文件 | 章节/标题 | 定位 | Dense排名 | BM25排名 | RRF原始分数 | 人工判断 | 备注 |",
            "|---:|---|---|---|---:|---:|---:|---|---|",
        ])
        for hit in result["hits"]:
            location = ", ".join(f"{key}={value}" for key, value in hit["location"].items())
            lines.append(
                f"| {hit['rank']} | {hit['file']} | {hit['heading'] or '—'} | {location} | "
                f"{hit['dense_rank'] or '—'} | {hit['bm25_rank'] or '—'} | {hit['rrf_score']:.6f} |  |  |"
            )
        lines.extend(["", "人工复核备注：", "", "- 命中是否直接回答问题：", "- 是否存在更权威但排名更低的来源：", "- 是否有同一文件重复占位：", ""])
    output = Path("data/reports/retrieval-sample-artificial-review.md")
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
