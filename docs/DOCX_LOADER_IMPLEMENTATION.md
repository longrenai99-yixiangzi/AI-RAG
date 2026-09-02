# DOCX Loader 实现说明

> 任务：TASK-004E DOCX Loader 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已实现，未接入正式 indexer

## 1. 实现范围

新增：

```text
app/ingestion/loaders/docx_loader.py
```

新增 DOCX 测试 fixture：

```text
tests/fixtures/docx/
├─ normal.docx
├─ headings.docx
├─ table.docx
├─ empty.docx
└─ broken.docx
```

新增独立测试：

```text
tests/test_docx_loader.py
```

## 2. Loader API

```python
DOCXLoader().load(path, document_id) -> DOCXLoadResult
```

`DOCXLoadResult.blocks` 只包含标准 `app.domain.SourceBlock` 对象。Loader 不生成 Chunk、不执行 Embedding、不写 SQLite、不写 Qdrant。

## 3. 状态定义

| 状态 | 含义 |
|---|---|
| `parsed` | DOCX 成功读取并生成一个或多个 SourceBlock |
| `empty` | DOCX 没有可提取的段落或表格内容 |
| `read_error` | 文件读取失败、DOCX 损坏、解析异常或扩展名不受支持 |

旧 `.doc` 文件直接返回 `read_error`，错误信息明确说明不自动转换；不会改名、转换或写回 `D:\设计管理`。

## 4. 已实现功能

### 4.1 python-docx 解析

使用现有依赖：

```python
from docx import Document
document = Document(path)
```

单个文件的读取和解析异常均在 Loader 内隔离，返回 `read_error`，不向正式调用方抛出未处理异常。

### 4.2 段落与 SourceBlock

段落按逻辑章节组织：

- 标题段落开启新的章节 SourceBlock；
- 后续普通段落加入当前章节；
- 每个章节保存 `paragraph_start` 和 `paragraph_end`；
- 标题文本保留在正文中，避免证据失去上下文；
- 空段落不生成空内容。

SourceBlock 结构示例：

```python
SourceBlock(
    document_id=document_id,
    source_path=str(path),
    file_name=path.name,
    text=section_text,
    heading_path="一级标题 > 二级标题",
    location={"paragraph_start": 3, "paragraph_end": 4},
)
```

### 4.3 标题层级与 Heading 路径

识别 Word 内置 Heading 样式和中文标题样式：

```text
Heading 1 / 标题 1
Heading 2 / 标题 2
...
```

标题层级以确定性路径维护，例如：

```text
一级标题 > 二级标题 > 三级标题
```

同级标题会替换当前层级，父级路径继续保留。

### 4.4 表格读取与行列关系

每张非空表格生成一个独立 SourceBlock：

- 每一行保留为一行文本；
- 单元格之间使用 ` | ` 分隔；
- 表格前加 `表格：` 标识；
- `location` 保存表号、有效行数和列数；
- 表格继承当前章节的 `heading_path`；
- 表格与普通段落不会混写成一个无法定位的长文本块。

示例：

```text
表格：
字段 | 内容
类型 | DOCX
状态 | 可解析
```

### 4.5 来源路径

每个 SourceBlock 都保存：

- `source_path`：原始 DOCX 完整路径；
- `file_name`：原始文件名；
- `location`：段落范围或表格位置。

不复制、不移动、不改写知识源文件。

## 5. 与当前系统的关系

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
- 执行 Embedding；
- 写入 Qdrant；
- 修改 `D:\设计管理`。

后续迁移应先比较旧 Parser 与新 Loader 的段落数量、章节路径、表格文本和 Citation 定位，再通过适配器接入正式 Document Engine。

## 6. 测试 Fixture

| Fixture | 用途 |
|---|---|
| `normal.docx` | 普通段落解析 |
| `headings.docx` | 多级 Heading 路径和段落范围 |
| `table.docx` | 表格行列关系和表格定位 |
| `empty.docx` | 空文档状态 |
| `broken.docx` | 损坏 DOCX 的 `read_error` |

测试另外使用临时目录创建旧 `.doc` 文件，验证 Loader 不自动转换。

## 7. 测试结果

新增测试覆盖：

- 普通 DOCX；
- 段落文本和来源路径；
- 多级标题和 Heading path；
- 表格行列关系；
- 空 DOCX；
- 损坏 DOCX；
- 旧 `.doc` 不转换。

执行结果：

```text
DOCX Loader 局部测试：6 passed
项目完整测试集：30 passed
```

## 8. TASK-004E 验收结论

| 验收项 | 结果 |
|---|---|
| 新建 DOCX Loader | 已完成 |
| 支持 `.docx` | 已完成 |
| python-docx 解析 | 已完成 |
| 段落文本提取 | 已完成 |
| 标题层级识别 | 已完成 |
| Heading 路径保存 | 已完成 |
| 表格读取 | 已完成 |
| 表格行列关系保留 | 已完成 |
| SourceBlock 输出 | 已完成 |
| 来源路径保存 | 已完成 |
| 异常返回 `read_error` | 已完成 |
| 旧 `.doc` 不处理 | 已满足 |
| 不执行 Embedding | 已满足 |
| 不写 Qdrant | 已满足 |
| 未修改 `app/parsers.py` | 是 |
| 未接入正式 indexer | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-004E：完成。**
