# CANDIDATE FUSION V2 REPORT

> TASK-020D Shadow Only。候选仅来自020C；BGE-M3与bge-reranker-v2-m3均为本地模型，Provider HTTP Requests=0。

## 1. 结果

- Business Gold Pre-Rerank MRR：0.72；Post-Rerank MRR：0.85；020C Baseline MRR：0.85。
- Post-Rerank Document/Section/Evidence Recall@5/10：1.0 / 1.0 / 1.0 / 1.0。
- Generic Regression (30) Post-Rerank MRR：0.0667；Baseline MRR：0.0667。

## 2. BA 矩阵

| BA | Document | Section | Baseline Evidence | Pre-Rerank | Post-Rerank | Status |
|---|---:|---:|---:|---:|---:|---|
| BA-001 | 2 | 1 | 4 | 1 | 1 | FUSED |
| BA-002 | 3 | 1 | 1 | 1 | 1 | FUSED |
| BA-003 | None | None | None | None | None | SOURCE_SCOPE_MISSING |
| BA-004 | 5 | 1 | 1 | 2 | 1 | FUSED |
| BA-005 | None | None | None | None | None | SOURCE_SCOPE_MISSING |
| BA-006 | None | None | None | None | None | SOURCE_SCOPE_MISSING |
| BA-007 | None | None | None | None | None | SOURCE_SCOPE_MISSING |
| BA-008 | 5 | 2 | 1 | 10 | 4 | FUSED |
| BA-009 | None | None | None | None | None | SOURCE_SCOPE_MISSING |
| BA-010 | 3 | 1 | 1 | 1 | 1 | LINEAGE_SAFETY_BLOCK |

## 3. Ranking 安全性

- Scope Match@Top5：1.0；Authority Appropriate Rate（Generic）：0.5。
- Registration / Query Page Dominance：0.0 / 0.0；Duplicate Rate：0.0。
- Lineage Unsafe Join：0；BA-010保持 `LINEAGE_SAFETY_BLOCK`，未自动Join。

## 4. 执行边界

- embedding：`D:\AI智能体\AI设计管理RAG-V1\models\bge-m3`；reranker：`D:\AI智能体\AI设计管理RAG-V1\models\bge-reranker-v2-m3`。
- Snapshot：`4deb66d9655a769bb844dcbbc0cf0dc30734e9db8d5220d546187bc991c74029`；运行耗时：0.566s。
- formal Retriever modified=false；formal 8000 modified=false；formal Qdrant write=0；Root-002 refresh=0；Root-003 scan=0；Gold runtime injection=0；BA runtime hardcoding=0。

TASK-020D = COMPLETE

等待架构评审。

## 验收结论

**NOT_PASSED_MRR_NO_IMPROVEMENT**：Gold Evidence MRR stayed at 0.85; TASK-020D cannot claim ranking success.

