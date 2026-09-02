# PDF Loader + Quality Check 实现说明

> 任务：TASK-004D PDF Loader + Quality Check 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已实现，未接入正式 indexer，未执行 OCR

## 1. 实现范围

新增：

```text
app/ingestion/loaders/pdf_loader.py
app/ingestion/quality/pdf_quality.py
```

新增 PDF fixture：

```text
tests/fixtures/pdf/
├─ normal.pdf
├─ empty.pdf
├─ scanned_feature.pdf
└─ broken.pdf
```

新增独立测试：

```text
tests/test_pdf_loader.py
```

## 2. PDF Loader API

```python
PDFLoader().load(path, document_id) -> PDFLoadResult
```

`PDFLoadResult.blocks` 只包含标准 `app.domain.SourceBlock` 对象。Loader 不生成 Chunk、不调用 OCR、不调用 Embedding、不写 SQLite、不写 Qdrant。

## 3. PDF Loader 功能

### 3.1 格式与异常状态

Loader 支持大小写不敏感的 `.pdf` 扩展名。结果状态如下：

| 状态 | 含义 |
|---|---|
| `parsed` | PDF 有可用文字，完成页级 SourceBlock 输出 |
| `empty` | PDF 没有可提取文字，且没有足以判断为扫描件的图片页 |
| `needs_ocr` | Quality Check 判定疑似扫描 PDF，仅标记，不执行 OCR |
| `read_error` | 文件读取失败、PDF 损坏或页面解析异常 |

损坏 PDF 在 Loader 内捕获异常并返回 `read_error`，不会向调用方抛出未处理异常。

### 3.2 PyMuPDF 解析

使用现有依赖 PyMuPDF：

```python
with pymupdf.open(path) as pdf:
    page.get_text("text")
```

不修改 PDF，不保存提取文本，不执行 OCR。

### 3.3 一页一个 SourceBlock

每页生成一个标准 SourceBlock：

```python
SourceBlock(
    document_id=document_id,
    source_path=str(path),
    file_name=path.name,
    text=page_text,
    location={"page": page_number, "text_length": len(page_text)},
)
```

页号为 1-based。即使页面没有文字，也保留该页的空 SourceBlock；后续 Chunking 可以忽略空文本。文件无法打开时不生成 SourceBlock。

### 3.4 表格文本

PDF Loader 保留 PyMuPDF 返回的原始文本顺序和换行，不把表格内容丢弃或压缩为单个摘要。表格能否完美还原为行列结构取决于 PDF 的文字层布局；当前实现保证表格文字可进入 SourceBlock，精确表格结构属于后续质量增强范围。

## 4. PDF Quality Check

文件：

```text
app/ingestion/quality/pdf_quality.py
```

### 4.1 统计指标

`assess_pdf()` 对已打开的 PyMuPDF 文档只读检查：

- `total_pages`：总页数；
- `page_text_lengths`：每页可提取文字长度；
- `text_chars`：全文文字字符数；
- `text_pages`：有可提取文字的页数；
- `empty_text_pages`：无可提取文字的页数；
- `page_image_counts`：每页图片数量；
- `image_pages`：含图片的页数；
- `image_count`：图片总数；
- `image_page_ratio`：含图片页数 / 总页数；
- `suspected_scanned`：是否疑似扫描 PDF；
- `reason`：判断原因。

### 4.2 疑似扫描判断

默认判断参数：

```text
min_text_chars_per_page = 20
min_text_page_ratio = 0.5
min_image_page_ratio = 0.5
```

当图片页比例达到 50%，且满足以下任一条件时标记 `needs_ocr`：

- 全文文字数为 0；
- 平均每页文字少于 20 个字符；
- 有文字页比例低于 50%。

这是一种可解释的初步质量判断，不是 OCR 结果，也不宣称能够识别所有扫描 PDF。参数保留在函数参数中，后续可以配置化并使用真实 Gold/质量样本校准。

### 4.3 空文档与扫描件区分

- 0 页 PDF：`empty`；
- 有页、无文字、无足够图片特征：`empty`；
- 有页、图片页占比高且文字不足：`needs_ocr`；
- 有正常文字覆盖：`parsed`。

Quality Check 只判断，不执行 OCR，不下载 OCR 模型，不改变源文件。

## 5. 测试 Fixture

| Fixture | 用途 |
|---|---|
| `normal.pdf` | 文字 PDF，包含普通文本和表格样式文本 |
| `empty.pdf` | 只有空白页，验证 `empty` |
| `scanned_feature.pdf` | 两页图像、无文字层，验证 `needs_ocr` 和图片占比 |
| `broken.pdf` | 非法 PDF 字节，验证 `read_error` |

Fixture 只存放在 `tests/fixtures/pdf`，不属于 `D:\设计管理`，不参与正式索引。

## 6. 与现有系统的关系

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
- 执行 OCR；
- 修改 `D:\设计管理`。

后续迁移时应先比较旧 Parser 与新 Loader 的文件状态、页数、SourceBlock 数、文本覆盖和页码 Citation，再通过适配器接入正式 Document Engine。

## 7. 测试结果

新增测试覆盖：

- 普通 PDF；
- 页号和文本定位；
- 表格文本保留；
- 空 PDF；
- 图片占比和扫描特征；
- `needs_ocr` 判断但不执行 OCR；
- 损坏 PDF 的 `read_error`。

执行结果：

```text
PDF Loader 局部测试：4 passed
项目完整测试集：24 passed
```

## 8. TASK-004D 验收结论

| 验收项 | 结果 |
|---|---|
| 新建 PDF Loader | 已完成 |
| 支持 `.pdf` | 已完成 |
| PyMuPDF 解析 | 已完成 |
| 保存 page 页号 | 已完成 |
| 一页一个 SourceBlock | 已完成 |
| 保存文本定位 | 已完成 |
| 表格文本保留 | 已完成 |
| 损坏 PDF 返回 `read_error` | 已完成 |
| 总页数统计 | 已完成 |
| 页面文本长度统计 | 已完成 |
| 图片占比统计 | 已完成 |
| 疑似扫描 PDF 判断 | 已完成 |
| 不执行 OCR | 已满足 |
| 未修改 `app/parsers.py` | 是 |
| 未接入正式 indexer | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-004D：完成。**
