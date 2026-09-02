# AI设计管理知识库 V1.0 Chunk Strategy + Metadata Schema 设计

> 任务：TASK-004G Chunk Strategy + Metadata Schema 设计  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：仅完成统一数据模型设计，未接入正式 indexer

## 1. 设计边界与原则

本设计位于 Document Engine 和 RAG 索引之间：

```text
Loader / Quality Check
  -> SourceBlock
  -> Chunk Strategy
  -> Metadata 继承
  -> Chunk
  -> 后续 Index / Retriever / Citation
```

本任务不执行：

- 修改现有 `app/chunker.py`；
- 修改现有 `app/domain.py`；
- 接入正式 `app/indexer.py`；
- 生成 Embedding；
- 写入 Qdrant；
- 修改 `D:\设计管理`。

统一模型必须满足：

1. 来源可追溯：每个 Chunk 都能回到原文件和原始位置。
2. 结构不丢失：标题、页码、Sheet、表格和行列关系保留。
3. Metadata 可缺失：缺失字段为空，不因自动分类不确定而拒绝索引。
4. Chunk 可复现：同一文档、同一规则和同一文本得到确定性 Chunk ID。
5. 事实不猜测：Fact 只能引用已有 Chunk Evidence，不能由 Chunk 自动臆测。

## 2. SourceBlock 到 Chunk 的统一流程

### 2.1 通用流程

```text
Document Loader
  -> SourceBlock（格式定位 + 原文）
  -> Quality 状态确认
  -> 文档级 Metadata 识别
  -> SourceBlock Metadata 继承
  -> 按格式边界切分
  -> Chunk Metadata 快照
  -> Chunk
```

Quality 状态为 `read_error`、`empty` 或明确不可索引时，不生成可检索 Chunk；`needs_ocr` 先保留原始状态和可提取文本，是否进入正式索引由后续策略决定。

### 2.2 Markdown

SourceBlock 来自 `MarkdownLoader` 的章节/段落块：

1. 以标题层级建立 heading path。
2. 保留 `line_start/line_end`。
3. 优先按标题、段落、列表、表格和代码块边界切分。
4. 超长段落再按句子和 token 预算拆分。
5. Chunk 不跨越不相关的标题章节；必要 overlap 只复制局部上下文。
6. YAML front matter 作为 Metadata 候选，不重复写入正文 Chunk。

当前基线参数沿用 `app/chunker.py`：

```text
target_tokens = 450
max_tokens = 800
overlap_tokens = 80
```

Markdown 文件数量最多，优先保证标题路径、行号和正文不丢失，再通过 Gold 问题调整参数。

### 2.3 PPTX

SourceBlock 默认一页幻灯片一个：

1. 保留 `slide` 页号和标题。
2. 文本框、表格、备注先合并到该页 SourceBlock。
3. 一般不跨幻灯片切 Chunk。
4. 超长单页只在页内按段落/文本块拆分。
5. 每个页内 Chunk 继承同一个 slide 定位，不能把相邻页混成一个 Citation。
6. 表格行列关系保留在文本中，后续可增加表格结构字段。

PPT/PPTX 文件数量不多但占资产总容量很高，Chunk 过程必须有单页和单文件失败隔离，不能为节省 Chunk 数而跨页合并。

### 2.4 PDF

SourceBlock 默认一页一个：

1. 保留 `page` 页号。
2. 使用 PyMuPDF 提取文字，保留换行和表格文本顺序。
3. 普通文字页可在页内按文本块、段落和 token 预算切分。
4. 默认不跨页；如果未来允许跨页，只能保留起止页号和完整来源范围。
5. `needs_ocr` 只表示质量判断，不代表已执行 OCR。
6. 空页不生成有效文本 Chunk，但页级 SourceBlock 可保留用于状态和诊断。

PDF Chunk 不得丢失页号，否则 Citation 无法准确回指原文。

### 2.5 DOCX

SourceBlock 来自 DOCX Loader 的逻辑章节和表格块：

1. Heading 段落开启章节，保存 heading path。
2. 普通段落在章节内组合。
3. 过长章节按段落和句子切分，不拆散标题语境。
4. 表格作为独立 SourceBlock/Chunk 候选，保留表号、行数和列数。
5. 表格较大时按完整表头 + 数据行窗口拆分，不能让数据行脱离表头。
6. Citation 保存段落范围或表格定位。

旧 `.doc` 不进入本 Loader 的 Chunk 流程，先保留 `read_error`/待转换状态。

### 2.6 XLSX

SourceBlock 默认一个有效 Sheet 一个：

1. 保存 Workbook 文件名和 Sheet 名称。
2. 首个非空行作为表头候选。
3. 保存 `row_start/row_end/column_count/header_row`。
4. Sheet 较小时生成一个或少量完整表格 Chunk。
5. Sheet 较大时按“表头 + 数据行窗口”切分，每个窗口重复必要表头。
6. 每个数据值保留列名关系，不能只输出无列名的值串。
7. 公式只使用已保存结果值，不在 Chunk 阶段计算复杂公式。

XLSX 的 Chunk 必须同时保留 Sheet、行范围和列数，保证问答结果可以回到工作表和数据行。

## 3. Chunk 字段设计

### 3.1 必需字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `chunk_id` | string | 是 | 确定性唯一 ID；由文档、来源块、切分规则和文本身份共同生成 |
| `document_id` | string | 是 | 文档级稳定 ID，同一源文件路径保持一致 |
| `source_path` | string | 是 | 原始知识源完整路径，只读回指，不作为写入目标 |
| `file_name` | string | 是 | 原始文件名 |
| `file_type` | string | 是 | 规范化扩展名，如 `.md`、`.pptx`、`.pdf`、`.docx`、`.xlsx` |
| `heading_path` | string | 否 | 标题/章节路径；无标题时为空 |
| `location` | object | 是 | 格式相关的原始定位信息 |
| `text` | string | 是 | 可检索原文片段；不得用摘要替代原文 |

### 3.2 建议扩展字段

后续实现时可增加，但不在本任务修改现有 `Chunk`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ordinal` | integer | 文档内稳定顺序；当前 `app.domain.Chunk` 已有此字段 |
| `metadata` | object | Chunk 级 Metadata 快照 |
| `source_block_id` | string | SourceBlock 稳定身份，便于重新切分和调试 |
| `chunk_version` | string | 切分规则版本 |
| `quality_status` | string | 来源块质量状态，如 parsed、needs_ocr |
| `text_hash` | string | Chunk 文本哈希，辅助一致性检查 |

### 3.3 location 统一约定

`location` 使用 JSON 对象，按文件类型保存必要字段：

| 类型 | 示例 |
|---|---|
| Markdown | `{"line_start": 8, "line_end": 20}` |
| PPTX | `{"slide": 3, "title": "设计管理流程"}` |
| PDF | `{"page": 5, "text_length": 620}` |
| DOCX 段落 | `{"paragraph_start": 4, "paragraph_end": 8}` |
| DOCX 表格 | `{"table": 1, "rows": 6, "columns": 4}` |
| XLSX | `{"sheet_name": "设计管理", "row_start": 2, "row_end": 18, "column_count": 5, "header_row": 1}` |

定位字段必须与原始文件格式一致，不把页号、行号或 Sheet 名称丢到普通文本里后再猜回去。

## 4. Metadata Schema 设计

### 4.1 分层

```text
Document Metadata
  -> SourceBlock Metadata
  -> Chunk Metadata 快照
```

Document 级 Metadata 是默认值；SourceBlock 或 Chunk 只有在局部证据明确时才覆盖。Chunk 保存生成时的快照，保证检索和 Citation 不依赖实时重新解析。

### 4.2 基础 Metadata

| 字段 | 类型 | 允许值/说明 |
|---|---|---|
| `file_type` | string | `.md`、`.markdown`、`.pptx`、`.pdf`、`.docx`、`.xlsx` 等 |
| `file_name` | string | 原始文件名 |
| `source_path` | string | 原始文件完整路径，建议作为来源字段而非分类字段 |
| `file_size` | integer | 文件字节数 |
| `mtime_ns` | integer | 文件修改时间，用于状态检测 |
| `sha256` | string | 文件内容哈希，用于变化检测 |
| `parse_status` | string | parsed、empty、read_error、needs_ocr 等 |

用户明确要求的 `file_type` 和 `file_name` 是最小基础 Metadata，不得依赖分类规则才能获得。

### 4.3 企业知识 Metadata

以下枚举以 V1 执行手册为第一版约定。字段可以为空，未知值不得强行归类。

#### `board`

```text
设计管理
技术管理
科技管理
```

#### `knowledge_type`

```text
制度
案例
方法
模板
会议资料
培训资料
```

#### `discipline`

```text
建筑
结构
机电
BIM
EPC
```

### 4.4 Metadata 生成和继承规则

Metadata 识别优先级：

1. 文件夹路径；
2. 文件名；
3. 文档标题或 Sheet/Slide 标题；
4. 表头；
5. 正文关键词。

规则应配置化并保留：

```text
metadata_source       规则命中的来源
metadata_rule         使用的规则标识
metadata_confidence   置信度
metadata_review_status 自动/人工/待复核
```

约束：

- Metadata 缺失允许为空；
- 不因为缺少 Metadata 拒绝索引；
- 低置信度标签只能辅助检索，不能作为不可回退的硬过滤；
- 人工修正优先于自动标签；
- Metadata 变化应触发文档或 Chunk 的索引状态变化；
- 不把单个用户问题写成 Parser 的硬编码分类规则。

## 5. Fact 预留字段设计

Fact 是结构化事实，不等同于普通 Metadata。V1 只预留模型，不在本任务抽取或写入事实。

### 5.1 建议字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | string | Fact 稳定 ID |
| `entity_id` | string | 主体实体，如项目、组织或文件 |
| `entity_name` | string | 主体名称 |
| `predicate` | string | 属性/关系，如实施单位、项目阶段 |
| `value` | string/object | 事实值 |
| `value_type` | string | string、number、date、organization 等 |
| `evidence_chunk_ids` | list[string] | 必须至少绑定一个证据 Chunk |
| `source_path` | string | 证据原始文件路径 |
| `location` | object | 页码、段落、Sheet、行号等精确位置 |
| `status` | string | AUTO、REVIEW、CONFIRMED、CONFLICT、REJECTED |
| `confidence` | number/null | 自动提取置信度，不能代替证据 |
| `valid_from` | string/null | 生效时间，可选 |
| `valid_to` | string/null | 失效时间，可选 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

### 5.2 Fact 约束

1. 没有 Evidence 的 Fact 不得进入正式事实库。
2. Fact 值不能仅由文件名或模型猜测生成。
3. 多份来源不一致时标记 `CONFLICT`，不得静默覆盖。
4. Fact 直答仍应返回 Citation，不能因为进入结构化表就隐藏原文依据。
5. Fact 与 Metadata 分离：`board` 是分类标签，`实施单位=某组织` 才是候选 Fact。

## 6. 与 Retriever 的关系

### 6.1 存储

未来每个 Chunk 的 Metadata 应同时可被：

- SQLite 查询和管理页面读取；
- Qdrant payload 用于候选过滤和调试；
- BM25/RRF 结果携带来源元数据；
- Retrieval Debug 记录过滤前后数量。

### 6.2 检索流程

```text
Query Analysis
  -> Metadata 候选条件
  -> Dense + BM25
  -> RRF
  -> 去重
  -> Reranker
  -> Metadata 软过滤/必要时回退
  -> Evidence
```

Metadata 只作为辅助检索条件：

- 候选条件明确且有结果时提高相关性；
- 自动标签低置信度时不硬过滤；
- 过滤后无结果时回退全库检索；
- Debug 必须记录原问题、候选条件、过滤前后数量和最终 Chunk。

`chunk_id` 是 Retriever、SQLite 和 Qdrant 之间的稳定关联键；`document_id` 用于文档级去重和同源结果聚合。

## 7. 与 Citation 的关系

Citation 使用 Chunk 的来源字段生成可核查证据：

| Chunk 信息 | Citation 展示 |
|---|---|
| `file_name` | 文件名 |
| `source_path` | 来源路径 |
| `heading_path` | 标题/章节 |
| `location.page` | PDF 页码 |
| `location.slide` | PPTX 幻灯片页号 |
| `location.sheet_name`、行范围 | XLSX Sheet 和行范围 |
| `location.paragraph_start/end` | DOCX 段落范围 |
| `location.line_start/end` | Markdown 行范围 |
| `text` | 原文片段 |

Citation 不重新解析文件，也不根据答案文本猜测页码。所有来源标记必须来自实际发送给 Answer Engine 的 Chunk 集合。

## 8. 与当前代码的兼容关系

当前 `app.domain.Chunk` 已有：

```text
chunk_id
document_id
ordinal
source_path
file_name
text
heading_path
location
```

V1 设计新增的 `file_type`、`metadata`、`source_block_id`、`chunk_version` 等属于后续扩展，当前不修改 `app/domain.py` 或 `app/chunker.py`。迁移时应使用适配器或 Schema 版本方式扩展，保持现有 staging、回滚和旧索引读取能力。

## 9. TASK-004G 边界确认

- 已完成五类 Loader 到 Chunk 的统一流程设计；
- 已完成 Chunk 必需字段和定位结构设计；
- 已完成基础 Metadata 和企业知识 Metadata Schema；
- 已完成 Fact 预留字段和 Evidence 约束；
- 已说明与 Retriever、Citation 的关系；
- 未修改现有 `app/chunker.py`；
- 未接入正式 `app/indexer.py`；
- 未生成 Embedding；
- 未写 Qdrant；
- 未修改 `D:\设计管理`。

**TASK-004G：设计完成。**
