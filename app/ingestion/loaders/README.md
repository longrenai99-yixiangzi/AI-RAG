# app/ingestion/loaders

未来职责：

- 按扩展名选择只读 Loader；
- 将 Markdown、PPT/PPTX、Word、PDF 等文件转换为统一 SourceBlock；
- 保留章节、页码、幻灯片、表格和行号等来源定位；
- 将不支持格式和读取异常转换为明确的文档状态。

当前阶段只建立职责目录，不复制或迁移 `app/parsers.py` 中的实现。
