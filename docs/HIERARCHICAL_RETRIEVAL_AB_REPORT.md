# HIERARCHICAL RETRIEVAL A/B REPORT

> A：020A.3 Chunk-first Baseline；B：020C Hierarchical Candidate Generation。仅比较候选召回，不评价最终答案。

| 指标 | A | B |
|---|---:|---:|
| Document Recall@5 | 0.2 | 0.6 |
| Section Hit/Recall@5 | 0.2 | 0.6 |
| Gold Evidence Recall@10 | 0.4 | 0.8 |

- B Document Recall@5门槛（>=0.60）：PASS。
- B Section Recall@5门槛（>=0.60）：PASS。
- B Evidence Recall@10不得低于0.40：PASS。

| BA | Gold Type | Document Rank | Section Rank | Table Rank | Evidence Rank | Failure |
|---|---|---:|---:|---:|---:|---|
| BA-001 | `FULL_GOLD` | None | None | None | None | `DOCUMENT_MISSED` |
| BA-002 | `FULL_GOLD` | None | 3 | None | 4 | `DOCUMENT_MISSED` |
| BA-003 | `SOURCE_SCOPE_GOLD` | None | None | None | None | `SOURCE_SCOPE_MISSING` |
| BA-004 | `FULL_GOLD` | 2 | 12 | 12 | 1 | `NO_FAILURE` |
| BA-005 | `FULL_GOLD` | None | None | None | None | `SOURCE_SCOPE_MISSING` |
| BA-006 | `FULL_GOLD` | None | None | None | None | `SOURCE_SCOPE_MISSING` |
| BA-007 | `FULL_GOLD` | None | None | None | None | `SOURCE_SCOPE_MISSING` |
| BA-008 | `FULL_GOLD` | 5 | 4 | None | 1 | `NO_FAILURE` |
| BA-009 | `FULL_GOLD` | None | None | None | None | `SOURCE_SCOPE_MISSING` |
| BA-010 | `PARTIAL_GOLD` | 2 | 1 | 1 | 1 | `LINEAGE_SAFETY_BLOCK` |

本TASK不进入020D，也不修改正式Retriever或Answer Engine。
