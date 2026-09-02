# app/ingestion/metadata

未来职责：

- 从路径、文件名、标题、表头和正文提取文档级 Metadata；
- 维护 Metadata 规则和置信度；
- 将文档级 Metadata 继承到 SourceBlock 和 Chunk；
- 缺失 Metadata 时保留为空，不拒绝文档进入索引。

当前阶段只定义职责，不增加 Metadata 字段，不改变现有索引流程。
