# app/core/retrieval

未来职责：

- Query Analysis；
- BM25、Dense、Qdrant、RRF 和 Reranker 检索链；
- Metadata Filter、软过滤和全库回退；
- 去重、Evidence 组装和 Retrieval Debug 数据。

迁移来源主要是当前 `app/retriever.py`、`app/bm25.py`、`app/vector_store.py` 和 `app/embeddings.py`。当前阶段不移动这些文件。
