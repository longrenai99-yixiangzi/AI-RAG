# XLSX Loader 实现说明

> 任务：TASK-004F XLSX Loader 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已实现，未接入正式 indexer

## 1. 实现范围

新增：

```text
app/ingestion/loaders/xlsx_loader.py
```

新增 XLSX 测试 fixture：

```text
tests/fixtures/xlsx/
├─ normal.xlsx
├─ multi_sheet.xlsx
├─ table.xlsx
├─ empty.xlsx
└─ broken.xlsx
```

新增独立测试：

```text
tests/test_xlsx_loader.py
```

## 2. Loader API

```python
XLSXLoader().load(path, document_id) -> XLSXLoadResult
```

`XLSXLoadResult.blocks` 只包含标准 `app.domain.SourceBlock` 对象。Loader 不生成 Chunk、不执行 Embedding、不写 SQLite、不写 Qdrant。

## 3. 状态定义

| 状态 | 含义 |
|---|---|
| `parsed` | 至少有一个有效 Sheet 并生成 SourceBlock |
| `empty` | Workbook 能打开，但没有任何有效 Sheet 内容 |
| `read_error` | 文件读取失败、XLSX 损坏或扩展名不受支持 |

旧 `.xls` 文件不在本 Loader 支持范围内，直接返回 `read_error`，不自动转换。

## 4. 已实现功能

### 4.1 openpyxl 只读解析

使用：

```python
load_workbook(path, read_only=True, data_only=True)
```

含义：

- `read_only=True`：按只读方式读取 Workbook；
- `data_only=True`：读取 Excel 已保存的结果值，不执行公式计算；
- Workbook 处理结束后显式 `close()`；
- 读取异常返回 `read_error`。

本任务不计算复杂公式，不修改 Excel 源文件，不保存任何回写结果。

### 4.2 Workbook 与 Sheet 识别

`XLSXLoadResult` 保存：

- `workbook_name`：Workbook 文件名；
- `sheet_names`：Workbook 中全部 Sheet 名称；
- `blocks`：有效 Sheet 的 SourceBlock 列表。

每个有效 Sheet 生成一个 SourceBlock；空 Sheet 被统计在 `sheet_names` 中，但不生成空内容 Block。

### 4.3 SourceBlock 字段

每个 Sheet 的 SourceBlock 至少保存以下信息：

```python
SourceBlock(
    document_id=document_id,
    source_path=str(path),
    file_name=path.name,
    text=sheet_text,
    heading_path=sheet.title,
    location={
        "sheet_name": sheet.title,
        "row_start": row_start,
        "row_end": row_end,
        "column_count": column_count,
        "header_row": header_row,
    },
)
```

其中：

- `source_path`：原始 Excel 路径；
- `file_name`：原始文件名；
- `sheet_name`：Sheet 名称；
- `row_start`：首个非空行；
- `row_end`：最后一个非空行；
- `column_count`：有效区域最大列数；
- `header_row`：识别出的表头行号。

### 4.4 表头识别

每个有效 Sheet 的首个非空行作为表头：

- 有值的单元格直接作为列名；
- 空表头自动使用 `列1`、`列2` 等名称；
- 表头行号写入 `location["header_row"]`；
- 数据行使用表头名称和单元格值形成键值关系。

示例：

```text
工作表：设计管理
表头（第1行）：项目 | 状态
第2行：项目：EPC | 状态：可解析
```

### 4.5 行列关系

每个有效 Sheet 内：

- 每个数据行保留原始行号；
- 每个单元格按列顺序输出；
- 使用表头名称连接列和值；
- 使用 ` | ` 保留列边界；
- 尾部空列不扩大 `column_count`；
- 中间空单元格仍保留对应的列位置。

这样可以在检索时同时保留“值”和“值属于哪一列”的关系，避免只拼接单元格文本造成语义丢失。

### 4.6 空 Sheet 与空 Workbook

- 空 Sheet 保留在 `sheet_names`，不生成 SourceBlock；
- Workbook 所有 Sheet 均为空时返回 `empty`；
- `empty.xlsx` 通过该规则验证；
- 不人为制造空文本索引内容。

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
- 修改 Excel 源文件或 `D:\设计管理`。

后续迁移时应对比旧 Parser 与新 Loader 的 Workbook 数、Sheet 数、有效 Sheet 数、行列范围、表头和 SourceBlock 文本，再通过适配器接入正式 Document Engine。

## 6. 测试 Fixture

| Fixture | 用途 |
|---|---|
| `normal.xlsx` | Workbook、Sheet、表头、数据行和范围 |
| `multi_sheet.xlsx` | 多 Sheet 和空 Sheet 过滤 |
| `table.xlsx` | 表头及行列关系 |
| `empty.xlsx` | 空 Workbook 状态 |
| `broken.xlsx` | 损坏 XLSX 的 `read_error` |

测试另外使用临时目录创建旧 `.xls` 文件，验证 Loader 不自动转换。

## 7. 测试结果

新增测试覆盖：

- Workbook 与 Sheet 识别；
- 每个有效 Sheet 一个 SourceBlock；
- Sheet 名称、来源路径和文件名；
- 表头识别；
- 行列范围和列数；
- 表格行列关系；
- 空 Sheet 和空 Workbook；
- 损坏 XLSX；
- 旧 `.xls` 不转换。

执行结果：

```text
XLSX Loader 局部测试：6 passed
项目完整测试集：36 passed
```

## 8. TASK-004F 验收结论

| 验收项 | 结果 |
|---|---|
| 新建 XLSX Loader | 已完成 |
| 支持 `.xlsx` | 已完成 |
| openpyxl 解析 | 已完成 |
| Workbook 识别 | 已完成 |
| Sheet 识别 | 已完成 |
| 每个有效 Sheet 一个 SourceBlock | 已完成 |
| 保存 Sheet 名称 | 已完成 |
| 保存行列范围 | 已完成 |
| 表头识别 | 已完成 |
| 保留行列关系 | 已完成 |
| 空 Sheet 检测 | 已完成 |
| 异常返回 `read_error` | 已完成 |
| 不执行复杂公式计算 | 已满足 |
| 不执行 Embedding | 已满足 |
| 不写 Qdrant | 已满足 |
| 未修改 `app/parsers.py` | 是 |
| 未接入正式 indexer | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-004F：完成。**
