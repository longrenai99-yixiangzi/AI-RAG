# AI设计管理知识库 V1.0 Document Engine 设计

> 任务：TASK-004A 文档处理框架设计  
> 正式目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：仅完成骨架和设计，未迁移代码

## 1. 设计目标与边界

Document Engine 的目标是把文件处理拆成可测试、可替换的阶段：

```text
文件扫描
  -> Loader
  -> Parser
  -> Quality Check
  -> SourceBlock
  -> Chunk
  -> Metadata 继承
  -> Index
```

本任务只建立设计和目录骨架：

- 不删除 `app/parsers.py`；
- 不迁移现有解析代码；
- 不改变 `app/indexer.py` 的调用链；
- 不修改 `D:\设计管理`；
- 不加载模型、不执行 OCR、不执行索引构建。

当前已建立：

```text
app/ingestion/
├─ loaders/
├─ quality/
├─ chunking/
└─ metadata/
```

## 2. 资产优先级

本设计根据 `docs/KNOWLEDGE_ASSET_BASELINE.md` 制定：

| 优先级 | 资产 | 数量 | 设计影响 |
|---|---|---:|---|
| 第一优先级 | Markdown | 475 | 数量最多，先建立稳定的编码、标题、段落和行号定位 |
| 第二重点 | PPT/PPTX | 39 | 文件总容量约 1.227 GB，存在超大文件，重点控制加载、定位和失败隔离 |
| 基础支持 | PDF | 16 | 保留 PyMuPDF 页级文本，增加 OCR 判断和低文本复核 |
| 基础支持 | Word | 30 | 兼容 `.docx`，旧 `.doc` 先明确报告为待转换/不支持 |
| 基础支持 | Excel | 15 | 本任务沿用现有实现，后续质量任务再细化 |

Markdown 约占全部文件的 66.9%；PPT/PPTX 约占总字节数的 71.7%。第一优先级由数量决定，第二重点由容量和处理风险决定。

## 3. Markdown 解析方案（第一优先级）

### 3.1 Loader 与编码

- 只读取 `.md` 和明确配置的 `.markdown` 文件；
- 默认按 UTF-8 严格解码，允许识别 UTF-8 BOM；
- 禁止 `errors="replace"`；
- 解码失败时记录 `encoding_error`，不得将替代字符静默写入索引；
- 保留 SHA-256、大小、mtime 和相对路径，作为文档身份与状态检测依据。

### 3.2 结构解析

- 识别一级至六级标题，维护 heading path；
- YAML front matter 只作为属性候选读取，不把它误当正文；
- 段落、列表、引用、表格和代码块保留原有文本语义；
- 以章节/段落形成 SourceBlock，并记录 `line_start`；
- 标题保留在对应块或块上下文中，避免正文脱离标题；
- 空章节不生成空块；
- 超长段落交给统一 Chunking，不在 Loader 中复制切片逻辑。

### 3.3 质量检查

- 检测解码异常和明显替代字符；
- 检测空文件、只有 front matter、只有目录或只有链接的文件；
- 检测标题层级异常，但不因格式不规范直接拒绝全文；
- 质量问题写入文档状态和报告，正文按可用部分处理。

### 3.4 当前迁移边界

现有 `app/parsers.py::_parse_markdown()` 已具备 UTF-8 读取、front matter 跳过、标题路径和行号基础能力，但使用了 `errors="replace"`。TASK-004A 不修改它；后续迁移时先用 fixture 覆盖严格编码和结构边界，再通过新 Loader 替换调用。

## 4. PPT/PPTX 解析方案（第二重点）

### 4.1 格式范围

- `.pptx` 使用 `python-pptx` 读取；
- `.ppt` 旧格式当前库不能直接可靠解析，先标记 `unsupported_legacy_format` 或 `needs_conversion`；
- 不自动把 `.ppt` 改名为 `.pptx`，不在知识源目录中转换或回写；
- 如未来需要转换，转换应是独立、受控、写入项目临时区的 Worker 任务。

### 4.2 PPTX SourceBlock

默认以“一页幻灯片一个 SourceBlock”：

- 记录 `slide` 页号；
- 按 shape 顺序提取文本框；
- 提取表格并保留行列边界；
- 提取讲者备注，并明确标记为备注文本；
- 优先使用标题占位符，无法识别时再使用第一段文本作为标题候选；
- 保留标题、页号和来源路径，便于 Citation 显示。

### 4.3 大文件与失败隔离

PPT/PPTX 只有 39 个，但约占总容量 71.7%，且存在 100 MB 以上文件。因此：

- 继续使用现有单文件大小上限；
- Loader 必须在文件级别捕获异常；
- 大文件解析放在 Worker，不能阻塞 Server；
- 单页内容超过 Chunk 预算时只拆分该页，不能跨页混合来源；
- 解析报告记录文件大小、页数、文本量、失败原因和耗时；
- TASK-004A 不改变现有 `app/parsers.py` 的 PPTX 处理。

## 5. Word 解析方案

### 5.1 DOCX

- `.docx` 使用 `python-docx`；
- 段落按 Heading/标题样式维护 heading path；
- 普通段落按原顺序形成 SourceBlock；
- 表格按表号、行号和列文本形成结构化块；
- 记录 `paragraph` 或 `table` 定位；
- 保留文档读取异常和空文档状态。

### 5.2 DOC

资产盘点发现 18 个 `.doc`。当前 Python 解析器不支持旧 `.doc`，因此 Document Engine 不应把它们误报为已解析：

- 先记录 `unsupported_legacy_format` 或 `needs_conversion`；
- 保留文件统计和后续处理队列；
- 转换链路另行设计，不修改 `D:\设计管理`；
- 没有稳定转换工具前，不强行引入新依赖。

### 5.3 当前迁移边界

现有 `app/parsers.py::_parse_docx()` 的段落、标题样式和表格处理可作为迁移基线。TASK-004A 不改变其行为。

## 6. PDF 解析方案

### 6.1 文字 PDF

- 使用现有 PyMuPDF；
- 逐页提取文字；
- 每页保留 `page` 页号；
- 尽量保留页面内文本顺序；
- 空页不生成空 SourceBlock；
- 页面内容交给统一 Chunking，不跨来源定位边界丢失页码。

### 6.2 质量与状态

对整份 PDF 和页面分别记录：

- 总页数；
- 可提取文字字符数；
- 有文字页数；
- 空文字页数；
- 含图像页数；
- 解析异常。

当前资产盘点中 16 个 PDF 均能提取到至少一部分文字，按现有严格规则没有明确 `needs_ocr` 文件；其中 2 个低文本图像型 PDF 需要人工复核，不能据此宣布 OCR 已解决。

### 6.3 当前迁移边界

现有 `app/parsers.py::_parse_pdf()` 已按页读取并在整份无文字时返回 `needs_ocr`。该行为在 TASK-004A 保持不变；后续通过 Quality Check 扩展低文本和图像页判断。

## 7. OCR 判断方案

OCR 判断与 OCR 执行分离：

```text
PyMuPDF 提取
  -> Quality Check
  -> needs_ocr / needs_review / parsed
  -> OCR Provider（后续任务）
```

建议状态：

| 状态 | 判定 |
|---|---|
| `parsed` | 文本量和页面覆盖达到最低阈值 |
| `needs_review` | 有少量文字、图像页较多或页面文字覆盖不均，需要人工复核 |
| `needs_ocr` | 整份或页面没有可提取文字，且图像内容表明可能需要 OCR |
| `ocr_pending` | 已判定需要 OCR，等待 Worker 处理 |
| `ocr_failed` | OCR Provider 失败，保留原始解析结果和失败原因 |

第一版不要只用文件扩展名判断 OCR，也不要仅因页面包含图片就判定扫描件。阈值应配置化，并在报告中保留文字量、页数和图像页数。

OCR Provider 后续应通过接口注入：

- `DisabledOCRProvider`：默认不执行 OCR，返回明确的 disabled 状态；
- `PaddleOCRProvider`：后续可选实现；
- OCR 失败不能导致整批索引失败；
- OCR 产生的文字必须回到 SourceBlock/Chunk，并保留 OCR 来源标记。

TASK-004A 不创建 OCR 引擎、不下载模型、不执行 OCR。

## 8. Chunk 策略

### 8.1 共同原则

- 先得到带来源定位的 SourceBlock，再切 Chunk；
- 不跨文档、不跨不可合并的来源边界；
- 标题路径、页码、幻灯片、Sheet、段落和表格定位随 Chunk 保存；
- Chunk ID 必须确定性生成，文件未变化时重复构建得到相同 ID；
- Chunk 文本不能因为切片而丢失可引用原文；
- 空文本不生成 Chunk。

### 8.2 初始参数

沿用当前 `app/chunker.py` 的可验证基线，暂不在 TASK-004A 改参数：

```text
target_tokens = 450
max_tokens = 800
overlap_tokens = 80
```

默认按段落、句子和结构边界切分；超长单元递归拆分。后续如果 Markdown 或 PPT 评测显示参数不合适，再通过 Gold 问题调整，不为单个问题增加硬编码规则。

### 8.3 类型化边界

- Markdown：优先按标题、段落、列表、表格和代码块边界；
- PPT/PPTX：默认不跨幻灯片，超长单页内部再拆分；
- Word：优先按标题、段落和表格；
- PDF：优先按页和文本块，跨页拼接必须保留两端页码；
- 表格：尽量保留表头与数据行关系，避免孤立数据行失去字段含义。

## 9. Metadata 继承方案

Metadata 采用“文档级提取、块级继承、Chunk 快照”的方式：

```text
Document Metadata
  -> SourceBlock.metadata
  -> Chunk.metadata
```

### 9.1 来源优先级

初始提取顺序：

1. 文件夹路径；
2. 文件名；
3. 文档标题；
4. 表头或页面标题；
5. 正文关键词。

规则应放在配置文件中，后续再实现具体加载；不得把单个问题的硬编码判断写进 Parser。

### 9.2 V1 第一版字段

按 V1 执行手册，首批至少支持：

- `board`：设计管理、技术管理、科技管理；
- `knowledge_type`：制度、案例、方法、模板、会议资料、培训资料；
- `discipline`：建筑、结构、机电、总图、BIM、EPC。

字段缺失允许为空，不得因 Metadata 不完整拒绝索引。自动识别结果应保存规则来源和置信度，人工修正应能覆盖自动结果。

### 9.3 继承与覆盖

- Document 级 Metadata 作为默认值；
- SourceBlock 只在标题、表头或明确局部证据出现时覆盖对应字段；
- Chunk 保存最终快照，确保检索和 Citation 不依赖重新解析；
- Metadata 变化应能触发文档或 Chunk 的索引状态更新；
- 所有 Metadata 变化保留来源和时间，避免静默覆盖。

## 10. 与现有 `app/parsers.py` 的迁移关系

### 10.1 当前链路

当前 `app/indexer.py` 直接调用：

```text
app.parsers.iter_source_files
  -> app.parsers.parse_file
  -> app.chunker.chunk_blocks
  -> Embedding/Qdrant/BM25/SQLite
```

### 10.2 迁移策略

1. **保留**：`app/parsers.py`、`app/chunker.py`、`app/indexer.py` 原位不动。
2. **先测试**：为 Markdown 和 PPT/PPTX 增加 fixture，固定现有行为和定位字段。
3. **再定义接口**：在 `app/ingestion/loaders`、`quality`、`chunking`、`metadata` 中逐步建立最小接口。
4. **先旁路验证**：新 Engine 先对测试 fixture 或预检样本运行，不接管正式索引发布。
5. **再加适配器**：由适配层把新 Engine 输出转换为现有 `ParsedDocument`、`SourceBlock`、`Chunk`，避免一次性修改数据库和向量链。
6. **对比验收**：比较文件数、状态、Chunk 数、文本覆盖和 Citation 定位；通过后再按 Task 授权替换调用。
7. **最后迁移编排**：Document Engine 稳定后，才将索引编排从 `app/indexer.py` 逐步交给 Worker。

TASK-004A 不执行以上第 2 步之后的代码迁移，也不改变当前索引流程。

## 11. 后续实现顺序

建议后续按以下最小顺序推进：

1. Markdown Loader 与严格编码质量测试；
2. PPTX Loader 与大文件/页级定位测试；
3. PDF Quality Check 与 OCR Provider 接口；
4. DOCX Loader 和旧格式状态；
5. 统一 Chunking 适配器；
6. Metadata 规则加载与继承；
7. 适配现有 `ParsedDocument`/`Chunk`；
8. 仅在回归通过后接入 Worker 和新索引流程。

## 12. TASK-004A 边界确认

- 已创建 `app/ingestion/loaders`；
- 已创建 `app/ingestion/quality`；
- 已创建 `app/ingestion/chunking`；
- 已创建 `app/ingestion/metadata`；
- 未删除 `app/parsers.py`；
- 未迁移现有解析代码；
- 未改变当前索引流程；
- 未修改 `D:\设计管理`；
- 未下载模型、执行 OCR 或建立新索引。

**TASK-004A：Document Engine 骨架和设计完成，未执行代码迁移。**
