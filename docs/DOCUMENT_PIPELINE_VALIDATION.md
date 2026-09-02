# Document Engine 集成验证报告

> 任务：TASK-005 Document Engine 集成验证  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：旁路验证完成，未替换正式 indexer

## 1. 验证边界

本次建立并验证：

```text
文件扫描
  -> Loader 选择
  -> SourceBlock 生成
  -> 现有 chunk_blocks 切 Chunk
  -> Pipeline 基线 Metadata 生成
  -> SourceBlock/Chunk/Metadata/location 校验
```

本任务明确没有：

- 替换 `app/indexer.py`；
- 修改旧 `app/parsers.py`；
- 写入正式 Qdrant；
- 生成 Embedding；
- 修改 `D:\设计管理`；
- 发布或替换正式索引。

## 2. 新增 Pipeline

新增：

```text
app/ingestion/pipeline.py
```

入口：

```python
run_document_pipeline(root, files=None, limit_per_type=None)
```

Pipeline 的职责：

1. 扫描支持的 `.md/.markdown/.pptx/.pdf/.docx/.xlsx` 文件；
2. 根据扩展名选择新 Loader；
3. 收集 Loader 返回的标准 SourceBlock；
4. 复用现有纯函数 `app.chunker.chunk_blocks()` 生成 Chunk；
5. 生成最小 Metadata 基线并复制到每个 Chunk；
6. 校验 Metadata 完整性和 location 定位；
7. 汇总每个文件的状态、质量信息和异常。

Pipeline 没有调用 `app.indexer.index_vault()`，也没有初始化或写入 Qdrant。

## 3. Loader 选择关系

| 扩展名 | Loader | 状态来源 |
|---|---|---|
| `.md`、`.markdown` | `MarkdownLoader` | parsed、empty、encoding_error 等 |
| `.pptx` | `PPTLoader` | parsed、empty、read_error |
| `.pdf` | `PDFLoader` | parsed、empty、needs_ocr、read_error |
| `.docx` | `DOCXLoader` | parsed、empty、read_error |
| `.xlsx` | `XLSXLoader` | parsed、empty、read_error |

旧 `.doc`、`.xls`、`.ppt` 不进入该支持集合，现阶段由各 Loader/扫描边界保留为不支持或读取异常状态，不自动转换。

## 4. Metadata 验证方案

当前 Pipeline 生成最小 Metadata：

```text
file_type
file_name
source_path
board
knowledge_type
discipline
```

其中 `file_type`、`file_name`、`source_path` 为完整性必需字段；`board`、`knowledge_type`、`discipline` 为企业知识分类候选字段，无法判断时允许为空。

当前验证阶段使用路径/文件名关键词生成候选分类，不将低置信度分类作为硬过滤条件。正式 Metadata 规则后续应迁移到 `app/ingestion/metadata` 的配置化实现；本 Pipeline 不把验证用规则当作最终治理规则。

每个 Chunk 通过 `chunk_id` 关联一份 Metadata 快照，验证要求：

```text
metadata_complete_chunks == chunks
```

## 5. location 验证方案

Pipeline 按文件类型校验 Chunk 的原始定位：

| 类型 | 校验字段 |
|---|---|
| Markdown | `line_start <= line_end` 且均为正整数 |
| PPTX | `slide` 为正整数 |
| PDF | `page` 为正整数 |
| DOCX 段落 | `paragraph_start <= paragraph_end` |
| DOCX 表格 | `table` 为正整数 |
| XLSX | `sheet_name`、`row_start`、`row_end`、`column_count` |

验证要求：

```text
location_valid_chunks == chunks

## 6. 五类真实知识源样本验证

执行方式：对 `D:\设计管理` 只读扫描，每种支持格式取 1 个样本，不执行全量索引。

### 6.1 汇总结果

| 指标 | 结果 |
|---|---:|
| 样本文件数 | 5 |
| 样本格式数 | 5 |
| SourceBlock 数量 | 78 |
| Chunk 数量 | 164 |
| Metadata 完整 Chunk | 164 |
| location 有效 Chunk | 164 |
| parsed | 5 |
| read_error | 0 |
| scan_error | 0 |

### 6.2 按格式结果

| 格式 | 文件数 | SourceBlock | Chunk | Metadata 完整 | location 有效 | 状态 |
|---|---:|---:|---:|---:|---:|---|
| Markdown | 1 | 1 | 1 | 1 | 1 | parsed |
| PPTX | 1 | 26 | 25 | 25 | 25 | parsed |
| PDF | 1 | 2 | 2 | 2 | 2 | parsed |
| DOCX | 1 | 47 | 61 | 61 | 61 | parsed |
| XLSX | 1 | 2 | 75 | 75 | 75 | parsed |
| 合计 | 5 | 78 | 164 | 164 | 164 | parsed |

DOCX 的 Chunk 数多于 SourceBlock，是因为章节文本按当前 token 策略继续切分；XLSX 的 Chunk 数多于 Sheet SourceBlock，是因为大 Sheet 按当前切片规则拆分。两者均保留原始定位。

## 7. 异常状态验证

使用独立 fixture 验证，不触碰知识源：

| 场景 | 验证结果 |
|---|---|
| 空 PPTX | `empty` |
| 空 PDF | `empty` |
| 空 DOCX | `empty` |
| 空 XLSX | `empty` |
| 损坏 PDF | `read_error` |
| 损坏 DOCX | `read_error` |
| 损坏 XLSX | `read_error` |
| 非法 UTF-8 Markdown | `encoding_error` |
| 旧 `.ppt` | `unsupported_legacy_format` |

异常文件不会生成 Chunk；错误原因保留在 Pipeline 文档记录中，不影响其他样本继续验证。

## 8. 真实样本发现与修正

真实 XLSX 样本暴露一个边界：首个非空表头行的列数少于后续数据行时，若直接按表头长度访问后续列会产生 `IndexError`。

已在新 `xlsx_loader.py` 中补齐表头列名：

```text
缺失列名 -> 列2、列3……
```

并新增回归测试。旧 `app/parsers.py` 未修改，正式 indexer 未接入。

## 9. 测试结果

新增 Pipeline 测试：

```text
tests/test_pipeline.py：4 passed
```

完整项目测试：

```text
41 passed
```

## 10. 后续接入前置条件

本次验证通过不等于可以直接替换正式索引。正式接入前仍需：

1. 将 Metadata 规则从验证 Pipeline 迁移到配置化模块；
2. 明确 `Chunk.file_type/metadata` 的 Schema 扩展方式；
3. 建立新旧 Parser/Loader 的文本覆盖和 Citation 对比；
4. 建立 staging Pipeline 到 SQLite/Qdrant 的一致性校验；
5. 在 Worker 任务中处理大 PPTX、OCR 状态和失败隔离；
6. 保留旧 indexer 回退路径后，再由后续 Task 明确授权接入。

## 11. TASK-005 验收结论

| 验收项 | 结果 |
|---|---|
| 新增 `app/ingestion/pipeline.py` | 已完成 |
| 文件扫描 | 已完成 |
| Loader 选择 | 已完成 |
| SourceBlock 生成 | 已完成 |
| Chunk 生成 | 已完成，复用现有纯切片函数 |
| Metadata 生成 | 已完成，最小基线字段 |
| SourceBlock 数量验证 | 已完成 |
| Chunk 数量验证 | 已完成 |
| Metadata 完整性验证 | 已完成 |
| location 定位验证 | 已完成 |
| 异常状态验证 | 已完成 |
| 未替换 `app/indexer.py` | 是 |
| 未修改 `app/parsers.py` | 是 |
| 未写入正式 Qdrant | 是 |
| 未影响当前可运行系统 | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-005：完成。**
```
