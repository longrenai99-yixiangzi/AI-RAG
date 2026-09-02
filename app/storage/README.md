# app/storage

未来职责：

- SQLite Schema、迁移和 Repository；
- documents、chunks、metadata、entities、facts 及状态记录；
- Qdrant、BM25 等索引存储适配；
- staging、发布、备份和回滚所需的持久化边界。

迁移来源主要是当前 `app/database.py` 和 `app/vector_store.py`。当前阶段不修改现有数据库结构和存储逻辑。
