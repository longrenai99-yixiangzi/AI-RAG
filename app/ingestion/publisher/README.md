# app/ingestion/publisher

未来职责：

- 读取并校验 Document Engine 生成的 Staging JSON；
- 将 Chunk + Metadata 转换为 Qdrant payload 和 BM25 关联计划；
- 在真正写入前完成 Schema、完整性、冲突和回滚前置校验；
- 由后续 Worker/发布服务执行受控、可回滚的索引发布。

TASK-007 只建立纯读取/纯转换/纯校验骨架，不打开或写入正式 Qdrant，不替换旧 `app/indexer.py`。
