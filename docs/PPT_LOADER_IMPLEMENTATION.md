# PPT/PPTX Loader 实现说明

> 任务：TASK-004C PPT/PPTX Loader 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已实现，未接入正式 indexer

## 1. 实现范围

新增：

```text
app/ingestion/loaders/ppt_loader.py
```

新增 PPTX 测试 fixture：

```text
tests/fixtures/ppt/
├─ normal.pptx
├─ multi_page.pptx
├─ table.pptx
└─ empty.pptx
```

新增独立测试：

```text
tests/test_ppt_loader.py
```

## 2. Loader API

```python
PPTLoader().load(path, document_id) -> PPTLoadResult
```

`PPTLoadResult.blocks` 只包含标准 `app.domain.SourceBlock` 对象。Loader 不生成 Chunk、不调用 Embedding、不写 SQLite、不写 Qdrant。

## 3. 状态定义

| 状态 | 含义 |
|---|---|
| `parsed` | 成功打开 PPTX，并为每张幻灯片生成一个 SourceBlock |
| `empty` | PPTX 没有幻灯片 |
| `read_error` | 文件不存在、读取失败、格式损坏、超过大小上限或解析异常 |
| `unsupported_legacy_format` | 扩展名为 `.ppt`，明确不自动转换 |

内容为空的单页仍保留一个 SourceBlock，保证“一页幻灯片一个 SourceBlock”；后续 Chunking 可忽略空文本。完全没有幻灯片的 PPTX 才返回 `empty`。

## 4. 已实现功能

### 4.1 PPTX 解析

使用现有依赖 `python-pptx` 的 `Presentation` 打开 `.pptx`。每页幻灯片独立处理，单页异常由 Loader 捕获并返回 `read_error`，不会向调用方抛出未处理异常。

### 4.2 SourceBlock 输出

每张幻灯片生成一个标准 `SourceBlock`：

```python
SourceBlock(
    document_id=document_id,
    source_path=str(path),
    file_name=path.name,
    text=content,
    heading_path=title,
    location={"slide": slide_number, "title": title},
)
```

来源路径保存在 `source_path`，文件名保存在 `file_name`，页号保存在 `location["slide"]`。

### 4.3 文本框

- 按幻灯片 shape 顺序提取带文本框架的形状；
- 保留文本框的段落文本；
- 空文本框跳过；
- 不跨幻灯片合并文本。

### 4.4 表格

- 识别 `has_table` 的 shape；
- 按行读取单元格文本；
- 每行使用 ` | ` 保留列关系；
- 以 `表格：` 前缀标识表格内容；
- 表格与同一页其他文本共同进入该页 SourceBlock。

### 4.5 备注信息

读取 `slide.notes_slide.notes_text_frame.text`：

- 去除空行；
- 忽略默认的 `Click to add notes` 占位文本；
- 有效备注以 `讲者备注：` 前缀加入该页 SourceBlock。

### 4.6 标题识别

标题识别顺序：

1. 优先识别标题占位符 `TITLE` 或 `CENTER_TITLE`；
2. 如果没有标题占位符，使用第一个非空文本形状的首行作为标题候选；
3. 标题保存到 `heading_path` 和 `location["title"]`；
4. 标题同时保留在 SourceBlock 正文中，避免证据脱离上下文。

### 4.7 大文件异常隔离

`PPTLoader` 支持可选的 `max_file_size_mb`：

```python
PPTLoader(max_file_size_mb=150)
```

超过上限时返回 `read_error`，不会尝试加载文件。默认不在 Loader 内改变项目配置；正式流程后续应由 Worker 传入现有 Settings 的文件大小上限。

读取、损坏压缩包和其他解析异常均被捕获为 `read_error`，避免单个 PPTX 使整批处理崩溃。

### 4.8 旧 `.ppt` 格式

扩展名为 `.ppt` 时只返回：

```text
unsupported_legacy_format
```

不自动转换、不改名、不写回 `D:\设计管理`，也不引入转换工具。

## 5. 与现有系统的关系

本实现是旁路 Loader：

```text
新 PPTLoader
  -> PPTLoadResult
  -> 标准 SourceBlock
```

当前正式索引链路仍然是：

```text
app/indexer.py
  -> app.parsers.iter_source_files
  -> app.parsers.parse_file
  -> app.chunker.chunk_blocks
```

本任务没有：

- 修改 `app/parsers.py`；
- 修改 `app/indexer.py`；
- 修改 `app/chunker.py`；
- 修改 `app/domain.py`；
- 接管正式索引；
- 修改 `D:\设计管理`。

后续迁移时应先对比旧 Parser 与新 Loader 的页数、SourceBlock 数、文本覆盖、标题和 Citation 页号，再通过适配器接入正式流程。

## 6. 测试结果

新增测试覆盖：

- 普通 PPTX 文本框；
- 多页 PPTX 和 slide 页号；
- PPTX 表格；
- 讲者备注；
- 空 PPTX；
- `.ppt` 旧格式拒绝自动转换；
- 损坏 PPTX 的 `read_error`；
- 大文件上限的异常隔离。

执行结果：

```text
PPT Loader 局部测试：7 passed
项目完整测试集：20 passed
```

PPTX fixture 使用现有 `.venv` 中已安装的 `python-pptx` 生成，仅用于测试目录，不涉及知识源和正式运行数据。

## 7. TASK-004C 验收结论

| 验收项 | 结果 |
|---|---|
| 新建 PPT/PPTX Loader | 已完成 |
| 支持 `.pptx` | 已完成 |
| 一页一个 SourceBlock | 已完成 |
| 保存 slide 页号 | 已完成 |
| 提取文本框 | 已完成 |
| 提取表格 | 已完成 |
| 提取备注 | 已完成 |
| 标题识别 | 已完成 |
| 保存来源路径 | 已完成 |
| 大文件异常隔离 | 已完成 |
| `parsed` | 已完成 |
| `empty` | 已完成 |
| `read_error` | 已完成 |
| `unsupported_legacy_format` | 已完成 |
| `.ppt` 不自动转换 | 已满足 |
| 未修改 `app/parsers.py` | 是 |
| 未接入正式 indexer | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-004C：完成。**
