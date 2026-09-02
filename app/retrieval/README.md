# app/retrieval

这是 V1 Retrieval Pipeline 的设计骨架，未来负责：

- Query Analysis；
- BM25 + Dense Hybrid Retrieval；
- RRF 融合、去重和候选排序；
- 可选 Reranker；
- Context/Evidence/Citation 组装。

当前阶段只建立模块边界和接口约定，不导入、不替换现有 `app/retriever.py`，也不接入生产 Qdrant。
