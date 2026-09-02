# app/ingestion

未来职责：

- Loader、Parser、Quality Check、Chunk、Metadata 的文档处理链；
- PDF、DOCX、XLSX、PPTX 和 Markdown 解析；
- 编码质量、乱码、解析失败和 needs_ocr 状态；
- 为 Worker 提供可测试的文档处理组件。

迁移来源主要是当前 `app/parsers.py`、`app/chunker.py` 和部分 `app/indexer.py`。当前阶段只建立职责边界，不移动文件。
