# app/ingestion/chunking

未来职责：

- 在 SourceBlock 基础上生成可检索 Chunk；
- 按文档类型保留标题、页码、幻灯片和表格边界；
- 统一 token 预算、重叠策略和确定性 Chunk ID；
- 将文档 Metadata 和来源定位继承到每个 Chunk。

当前阶段保留现有 `app/chunker.py`，不改变当前切片参数和索引结果。
