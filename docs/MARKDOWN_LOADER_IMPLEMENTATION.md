# Markdown Loader 实现说明

> 任务：TASK-004B Markdown Loader 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已实现，未接入正式 indexer

## 1. 实现范围

新增：

```text
app/ingestion/loaders/markdown_loader.py
```

同时新增 Markdown 测试 fixture：

```text
tests/fixtures/markdown/
├─ normal.md
├─ bom.md
├─ encoding_error.md
├─ nested_headings.md
├─ table.md
└─ code_block.md
```

新增独立测试：

```text
tests/test_markdown_loader.py
```

## 2. Loader API

```python
MarkdownLoader().load(path, document_id) -> MarkdownLoadResult
```

`MarkdownLoadResult.blocks` 只包含标准 `app.domain.SourceBlock` 对象，不生成 Chunk、不调用 Embedding、不写数据库、不写向量库。

结果状态：

| 状态 | 含义 |
|---|---|
| `parsed` | 成功读取并生成一个或多个 SourceBlock |
| `empty` | 文件为空，或只包含空白/front matter |
| `encoding_error` | 文件不是有效 UTF-8 |
| `front_matter_error` | YAML front matter 缺少结束标记、解析失败或不是映射 |
| `read_error` | 文件读取失败 |
| `unsupported_extension` | 文件扩展名不是 `.md` 或 `.markdown` |

## 3. 已实现功能

### 3.1 `.md` 与 `.markdown`

Loader 只接受大小写不敏感的 `.md`、`.markdown` 扩展名，其他扩展名返回 `unsupported_extension`，不进入正文解析。

### 3.2 UTF-8 严格读取与 BOM

使用：

```python
path.read_bytes().decode("utf-8-sig")
```

`utf-8-sig` 兼容一个 UTF-8 BOM，同时保持严格解码行为。代码没有使用 `errors="replace"`。非法 UTF-8 会返回 `encoding_error`，不会生成部分 SourceBlock，也不会把替代字符写入索引。

### 3.3 YAML front matter

- 识别文件开头的 `---`；
- 支持 `---` 或 `...` 作为结束标记；
- 使用现有依赖 PyYAML 的 `safe_load`；
- front matter 必须解析为 mapping；
- 解析结果放在 `MarkdownLoadResult.front_matter`，正文仍只生成 SourceBlock；
- front matter 行不进入正文 SourceBlock 的行号范围；
- 缺少结束标记或 YAML 无效时返回 `front_matter_error`。

### 3.4 标题层级与 heading path

识别一级至六级 ATX 标题：

```text
# 一级
## 二级
### 三级
```

每个 SourceBlock 保存从根标题到当前标题的路径，例如：

```text
一级标题 > 二级标题 > 三级标题
```

标题文本保留在对应 SourceBlock 中，避免正文脱离标题语境。

### 3.5 line_start / line_end

每个非空 SourceBlock 的 `location` 保存：

```python
{
    "line_start": 8,
    "line_end": 10,
}
```

定位使用原始 Markdown 文件的 1-based 行号；front matter 被跳过，但后续正文仍使用原始文件行号。首尾空白行不计入内容范围。

### 3.6 空文件与异常状态

- 空字节文件、全空白文件和只有 front matter 的文件返回 `empty`；
- 非法 UTF-8 返回 `encoding_error`；
- 文件系统异常返回 `read_error`；
- 异常均通过结果状态返回，不影响其他文件的调用方。

### 3.7 表格与代码块

Markdown Loader 不对表格或 fenced code block 做破坏性转换：

- 表格原文行保留在 SourceBlock 文本中；
- 代码围栏、语言标识和代码内容保留在 SourceBlock 文本中；
- 后续 Chunking 再依据结构和 token 预算切分。

## 4. 与当前系统的关系

本实现是旁路 Loader：

```text
新 MarkdownLoader
  -> MarkdownLoadResult
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

后续迁移时应先用测试 fixture 对比新旧解析结果，再通过适配器把新结果接入现有 `ParsedDocument`/`SourceBlock` 链路，避免一次性替换正式流程。

## 5. 测试结果

新增测试覆盖：

- 正常 Markdown 和 YAML front matter；
- UTF-8 BOM；
- 非法 UTF-8 编码状态；
- 多级标题和 heading path；
- 表格原文保留；
- 代码块原文保留；
- 空文件状态。

执行结果：

```text
Markdown Loader 局部测试：7 passed
项目完整测试集：12 passed
```

编码异常测试基于 `encoding_error.md` fixture 生成临时非法字节副本，避免把不可逆的非法字节写入源码 fixture；该临时文件只位于 pytest 临时目录。

## 6. TASK-004B 验收结论

| 验收项 | 结果 |
|---|---|
| 新建 Markdown Loader | 已完成 |
| 支持 `.md` | 已完成 |
| 支持 `.markdown` | 已完成 |
| UTF-8 严格读取 | 已完成 |
| UTF-8 BOM 兼容 | 已完成 |
| 禁止 `errors=replace` | 已满足 |
| YAML front matter | 已完成 |
| 标题层级和 heading path | 已完成 |
| line_start/line_end | 已完成 |
| 空文件检测 | 已完成 |
| 编码异常状态 | 已完成 |
| 标准 SourceBlock 输出 | 已完成 |
| 未修改 `app/parsers.py` | 是 |
| 未接入正式 indexer | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-004B：完成。**
