# HIERARCHICAL RETRIEVAL METRIC INTEGRITY AUDIT

> TASK-020C.1.1。本次仅使用当前本地 BGE-M3 为 BA-001～BA-010 的 10 个冻结问题生成 Query Embedding；没有网络访问、LLM/Live Provider、Qdrant 写入、Index 更新、Retriever 改动、Root-002 refresh 或 Root-003 scan。

## 1. Registration 指标

- 观测值：{'numerator': 0, 'denominator': 50, 'rate': 0.0}。正确判断 `rate == 0`，结果：**PASS**。

## 2. Section Dense 覆盖率

- Direct Section Dense Count：3426；Eligible Direct Count：3242。
- Parent Document Vector Fallback Count：1870。
- Excluded / Eligible Sections：247 / 5049。
- Direct Section Dense Coverage：0.6421。
- Effective Section Vector Availability：1.0。
- 回退原因：Root-001 V2 Section boundaries cannot be matched to a legacy Qdrant chunk by exact heading path, page, or sheet in app/retrieval/hierarchical_v1.py::_match_root1_section. The Shadow index therefore uses the existing parent-document vector as an explicitly labeled fallback. No section embedding was added in this task.

## 3. Document Stage 纯度

- A. 是：Section-Assisted 路径在 Document TopK 前计算全库 Section Query 相关性。
- B. 是：全库 Section Rank 被折叠为父 Document 信号并参与 Document RRF。
- C. 是：因此 Section-Assisted 路径不是纯 Document Retrieval。
- D. Pure 路径不使用任何 Query-time Section BM25/Dense 排名，也不使用 Global Rescue；两路径仅共享冻结 Document Index Metadata/Soft Boost。

## 4. 同口径指标

| 路径 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |
|---|---:|---:|---:|---:|
| Pure Document Retrieval | 0.0 | 0.4 | 1.0 | 1.0 |
| Section-Assisted Document Retrieval | 0.0 | 0.6 | 1.0 | 1.0 |

## 5. BA 专项

| BA | Pure Document Rank | Section-Assisted Document Rank | Hierarchical Section Rank | Evidence Rank |
|---|---:|---:|---:|---:|
| BA-001 | 4 | 2 | 1 | 4 |
| BA-002 | 5 | 3 | 1 | 1 |
| BA-004 | 2 | 5 | 3 | 1 |
| BA-008 | 5 | 5 | 2 | 1 |
| BA-010 | 2 | 3 | 1 | 1 |

## 6. 执行记录

- query_embedding_model：BGE-M3；model_path：`D:\AI智能体\AI设计管理RAG-V1\models\bge-m3`；query_count：10。
- index_snapshot fingerprint：`8df66d23007d182de38c85b15f2896a1cc93255c5029bc6c4b5a54eda9394b18`。
- provider_http_requests=0；network_access=false；formal_qdrant_write=false；retriever_code_changed=false。
- Global Rescue Gold Dependency：0.0，未计入 Pure Document Recall。

## 7. 最终结论

**HIERARCHICAL_DOCUMENT_STAGE_VALID**

TASK-020C.1.1 = COMPLETE
