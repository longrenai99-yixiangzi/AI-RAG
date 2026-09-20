# worker

未来职责：

- 扫描只读知识源；
- 文档解析、质量检测和 OCR；
- Chunk、Metadata 和索引构建；
- 增量状态检测、失败报告、staging 发布和回滚。

Worker 与 FastAPI Server 分离，Worker 失败不得使 Server 退出。当前阶段不创建 Worker 进程、不改变现有索引命令。
