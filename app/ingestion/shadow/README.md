# app/ingestion/shadow

未来职责：

- 用同一批输入并行运行新 Document Engine 与旧 Parser 投影；
- 比较文档、Chunk、ID、来源、location、Metadata 和异常状态；
- 生成 Shadow 验证报告，为正式切换提供证据。

当前阶段只读验证，不调用旧 indexer、不生成向量、不写 Qdrant、不替换正式索引。
