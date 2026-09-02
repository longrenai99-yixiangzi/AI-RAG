# 知识源闭环修复设计

## TASK-016B：Knowledge Source Closure Design

## 1. 设计目标与边界

本设计用于解决 TASK-016A 发现的三类知识源闭环问题：

- `SOURCE_REGISTERED_ONLY`：知识库只有登记页、路径或外部链接，正文没有进入索引；
- `DOCUMENT_LINK_FAILURE`：Wiki、实体页、Query 页与真实 raw 文件之间没有完成自动展开；
- `INDEX_FAILURE`：正文或解析产物存在，但没有形成可检索的完整索引闭环。

本 TASK 只完成架构和数据治理设计，不执行实现。

明确不修改：

- `app/retriever.py`；
- `app/main.py`；
- 8000 服务；
- 正式 Qdrant collection；
- Embedding、Reranker 和 Answer Engine 逻辑；
- `D:\设计管理` 源文件。

后续实现必须继续保留只读知识源、Shadow Qdrant、staging、失败回滚和人工审核边界。

## 2. TASK-016A 诊断结论摘要

| 根因 | 数量 | 典型问题 | 诊断结论 |
|---|---:|---|---|
| `SOURCE_MISSING` | 1 | BA-005 | 未确认存在能够直接回答问题的专用源文件 |
| `SOURCE_REGISTERED_ONLY` | 4 | BA-003、BA-006、BA-007、BA-009 | 本地 Markdown 存在，但正文只是外部 DOCX/PDF/XLSX 登记或链接 |
| `INDEX_FAILURE` | 1 | BA-004 | 精确证据存在于 approved parsed artifact，但没有进入 Shadow Qdrant |
| `RETRIEVAL_FAILURE` | 1 | BA-002 | 正确的设计创效问答页已存在并有 Chunk，但没有进入最终 Evidence Bundle |
| `DOCUMENT_LINK_FAILURE` | 1 | BA-010 | Wiki 实体页到 raw 登记页再到外部 XLSX 的链路未展开 |
| `ANSWER_ENGINE_FAILURE` | 1 | BA-001 | 正确证据已经进入 Evidence Bundle，但最终回答仍被降级为部分证据 |

其中，TASK-016B 主要处理前三类知识源闭环问题；BA-002 和 BA-001 的检索/回答问题留给后续任务处理，但本设计会为它们保留可审计的源状态和链路信息。

## 3. 外部 PDF/DOCX/XLSX 自动发现方案

### 3.1 发现入口

对每个 Markdown 登记页、Wiki 页面、实体页和 Query 页面扫描以下来源引用形式：

1. Markdown 标准链接：`[标题](目标)`；
2. Obsidian Wikilink：`[[目标|显示名称]]`；
3. `file://` 本地文件链接；
4. Windows 绝对路径；
5. 相对于当前知识源根目录的路径；
6. front matter 中的 `source`、`sources`、`raw`、`attachments`、`related_documents` 字段；
7. 正文中的附件登记、原始文件名和文件类型提示。

发现阶段只登记候选源，不直接写入正式索引。

### 3.2 路径解析顺序

路径解析采用确定性顺序：

```text
原始链接
  ↓
去除 file:// 和 URL 编码
  ↓
解析绝对 Windows 路径
  ↓
若为相对路径，基于当前 Markdown 所在目录解析
  ↓
若为 Obsidian 路径，基于 D:\设计管理 根目录解析
  ↓
规范化大小写、分隔符和 .. 段
  ↓
检查是否在允许的知识源根目录或明确批准的外部源目录内
```

默认允许读取：

- `D:\设计管理`；
- 后续经人工批准的只读外部源目录。

不允许自动读取任意 `file://` 路径、网络 URL、用户目录或系统目录。无法安全解析的链接必须进入 `LINK_BROKEN` 或 `NEEDS_REVIEW`，不能静默忽略。

### 3.3 文件发现结果

发现器对每个候选文件输出：

- 是否存在；
- 规范化路径；
- 文件名和扩展名；
- 文件大小；
- mtime；
- sha256；
- 文件是否在允许根目录内；
- 是否已被 Document Pipeline 扫描；
- 是否已有 Chunk；
- 是否已有 Embedding；
- 是否已进入 Shadow Qdrant；
- 父登记页和原始链接位置。

对于 PDF、DOCX、XLSX：

- 只要发现真实文件，先登记 `BODY_AVAILABLE`；
- 通过对应 Loader 后才进入 `PARSED`；
- 通过 Chunk 和索引一致性检查后才进入 `INDEXED`；
- 解析失败、空文档或索引失败必须保留失败原因。

### 3.4 外部文件导入边界

自动发现不等于自动发布。

建议分为三步：

1. 自动发现并生成候选 SourceRecord；
2. 对允许根目录内的文件执行只读解析和 Shadow 验证；
3. 经业务负责人确认后，才允许进入正式发布流程。

外部 PDF/DOCX/XLSX 的原始文件不得被复制覆盖，不得修改原文件。需要缓存时使用独立 Shadow/staging 目录，并保存原始 sha256。

## 4. Markdown 登记页解析方案

### 4.1 登记页识别

Markdown 页面满足以下任一条件时，标记为可能的登记页：

- front matter 含 `source`、`sources`、`file`、`attachment` 或 `raw`；
- 正文包含 `file://`；
- 正文只有附件链接、关联链接或来源说明；
- 正文包含 PDF、DOCX、XLSX、PPTX 文件名；
- 页面位于 `wiki/sources`、实体页、Query 页或外部资料登记目录；
- 页面内容很短，但存在一个或多个外部文件链接。

### 4.2 正文与登记信息分离

登记页解析时必须区分：

| 内容 | 处理方式 |
|---|---|
| 登记页自身正文 | 作为 Markdown Document/Chunk 保存 |
| 真实外部文件 | 单独建立 SourceRecord，不与登记页混为同一 Document |
| `file://` 链接 | 保存原始链接和解析后路径 |
| Obsidian Wikilink | 保存 link target、显示名称和父页面 |
| 关联概念说明 | 作为关系边保存，不当作真实附件正文 |
| 外部文件不存在 | 登记 `LINK_BROKEN`，不生成虚假正文 |

登记页本身不能因为存在路径就被标记为 `BODY_AVAILABLE`。只有真实文件正文被发现并成功读取后，真实文件才能进入该状态。

### 4.3 Front Matter 规则

推荐支持：

```yaml
source:
  - path: "file://D:/.../source.pdf"
    kind: pdf
    title: "原始文件"
    authority_level: L1
sources:
  - "raw/设计支持/设计价值创造/项目价值创造清单.md"
related_documents:
  - "wiki/entities/项目名称.md"
```

解析时保留：

- 原始 front matter；
- 解析后的标准 SourceLink；
- 规则来源 `front_matter`；
- 发现位置和行号；
- 解析错误信息。

### 4.4 登记页状态

登记页与真实文件必须分别记录状态。例如：

```text
登记页：PARSED / INDEXED
真实 PDF：REGISTERED_ONLY
```

不能因为登记页已进入 Qdrant，就认为真实 PDF 已进入 Qdrant。

## 5. Wiki → raw → source 展开方案

### 5.1 图模型

将知识源关系表示为有向图：

```text
Wiki Concept / Entity / Query
        ↓ related / source / raw / attachment
Markdown Registration Page
        ↓ file:// / relative path / file name
真实 PDF / DOCX / XLSX / PPTX / Markdown
        ↓ loader
SourceBlock
        ↓ chunking
Chunk
        ↓ embedding + index adapter
Shadow / Formal Index
```

每条边必须记录：

- `link_id`；
- `from_document_id`；
- `from_source_path`；
- `to_target_raw`；
- `to_resolved_path`；
- `link_type`；
- `link_location`；
- `resolution_status`；
- `resolution_error`；
- `discovered_at`。

### 5.2 展开规则

1. 先解析当前页面中的所有链接；
2. 对相对 Wiki 链接解析到知识库根目录；
3. 对 `raw/...` 链接解析真实登记页或真实文件；
4. 若目标仍是 Markdown 登记页，继续解析其 source/file 链接；
5. 发现真实文件后停止继续沿正文扩展，进入 SourceRecord；
6. 对循环链接使用 visited set；
7. 设置最大展开深度，建议默认 4 层；
8. 无法解析、路径越界或目标不存在时保留失败边。

### 5.3 BA-010 专项链路

当前已确认的链路：

```text
wiki/entities/新洲星谷科创中心项目.md
        ↓
raw/设计支持/设计价值创造/新洲星谷科创中心价值创造清单.md
        ↓
外部 XLSX：方案比选与价值创造清单方案比选及价值创造.xlsx
```

当前问题：

- Entity 页面已进入 Shadow；
- Raw Markdown 登记页已进入 Shadow；
- 外部 XLSX 正文未形成 Shadow Chunk；
- Retriever 只能看到项目介绍、Query 页和概念页；
- Answer Engine 因缺少专业条目和数量信息只能部分回答。

目标闭环：

```text
识别 entity link
  → 解析 raw 登记页
  → 解析外部 XLSX 路径
  → 校验文件存在和根目录权限
  → XLSX Loader 逐 Sheet 生成 SourceBlock
  → Chunk + Metadata
  → Shadow Qdrant
  → Citation 指向 XLSX Sheet/行列位置
```

## 6. Document Pipeline 改造点

本 TASK 不实施改造，只定义后续改造边界。

### 6.1 Scanner 层

增加 `link_discovery` 阶段：

- 扫描正常文件；
- 扫描 Markdown 登记页；
- 生成 SourceLink；
- 解析候选真实文件；
- 输出 SourceRecord；
- 不改变现有只读扫描规则。

### 6.2 Loader 选择层

按真实文件扩展名选择 Loader：

| 扩展名 | Loader | 失败状态 |
|---|---|---|
| `.pdf` | PDF Loader | `PARSE_FAILURE` / `NEEDS_OCR` |
| `.docx` | DOCX Loader | `PARSE_FAILURE` |
| `.xlsx` | XLSX Loader | `PARSE_FAILURE` |
| `.pptx` | PPTX Loader | `PARSE_FAILURE` |
| `.md` / `.markdown` | Markdown Loader | `PARSE_FAILURE` |
| `.doc` / `.ppt` / `.xls` | 不自动转换 | `UNSUPPORTED_LEGACY_FORMAT` |

### 6.3 SourceBlock 层

每个 SourceBlock 继承：

- `source_id`；
- `document_id`；
- `source_path`；
- `parent_document_id`；
- `link_id`；
- `file_type`；
- `location`；
- `parse_status`；
- `source_status`；
- `sha256`。

这样 Citation 能够区分：

- 概念页引用；
- 登记页引用；
- 真实 PDF/DOCX/XLSX 正文引用。

### 6.4 Staging 层

建议增加以下 staging 文件：

```text
source_records.jsonl
source_links.jsonl
source_blocks.jsonl
chunks.jsonl
metadata.jsonl
pipeline_manifest.json
```

每个阶段写入独立临时目录，全部校验通过后再生成 staging manifest。任何阶段失败都不能删除上一版有效 staging。

## 7. Chunk / Embedding / Qdrant 一致性检查

### 7.1 核心不变量

对每个已发布 SourceRecord，必须满足：

```text
1 SourceRecord
  → N SourceBlock
  → M Chunk
  → M Embedding
  → M Qdrant points
```

要求：

- 每个 Chunk 有稳定 `chunk_id`；
- 每个 Chunk 关联唯一 `document_id`；
- 每个 Chunk 保存 `source_path` 和 `location`；
- 每个 Embedding 关联同一个 `chunk_id`；
- Qdrant payload 保存 `chunk_id`、`document_id`、`source_path`、`location` 和 Metadata；
- Qdrant point 数量等于有效 Embedding 数量；
- 删除或失效源文件后，不能继续把旧点标记为 `INDEXED`。

### 7.2 对账表

每次 Shadow 发布生成：

| 对账项 | 检查内容 |
|---|---|
| 文件对账 | SourceRecord 数量、sha256、size、mtime |
| 解析对账 | parsed SourceBlock 数量、失败文件数量 |
| Chunk 对账 | 每个 document 的 Chunk 数量、空 Chunk 数量 |
| Embedding 对账 | Chunk ID 与向量 ID 一一对应 |
| Qdrant 对账 | payload chunk_id、point 数、collection 名称 |
| Citation 对账 | location 是否完整、source_path 是否存在 |
| 删除对账 | 已删除/失效文档的旧 Chunk 是否被标记失效 |

### 7.3 一致性状态

建议按文档级和 Chunk 级分别输出：

```text
BODY_AVAILABLE
PARSED
CHUNKED
EMBEDDED
INDEXED
STALE
INVALIDATED
```

状态不能跳跃。例如：

```text
REGISTERED_ONLY → BODY_AVAILABLE → PARSED → CHUNKED → EMBEDDED → INDEXED
```

失败时保留：

- `failed_stage`；
- `error_type`；
- `error_message`；
- `last_successful_stage`；
- `retryable`；
- `source_sha256`。

## 8. 新增数据结构设计

### 8.1 SourceRecord

```json
{
  "source_id": "src-...",
  "document_id": "doc-...",
  "source_path": "D:\\设计管理\\raw\\...",
  "file_name": "source.xlsx",
  "file_type": "xlsx",
  "source_layer": "raw",
  "source_status": "REGISTERED_ONLY",
  "parse_status": "not_started",
  "size": 12345,
  "mtime": "2026-08-25T10:00:00+08:00",
  "sha256": "...",
  "parent_document_id": "wiki-...",
  "discovered_from_link_id": "link-...",
  "authority_level": "L1",
  "review_status": "NEEDS_REVIEW"
}
```

### 8.2 SourceLink

```json
{
  "link_id": "link-...",
  "from_document_id": "wiki-...",
  "from_path": "D:\\设计管理\\wiki\\entities\\...md",
  "raw_target": "raw/设计支持/设计价值创造/...md",
  "resolved_path": "D:\\设计管理\\raw\\...md",
  "link_type": "obsidian_wikilink",
  "link_location": {"line_start": 12, "line_end": 12},
  "resolution_status": "RESOLVED",
  "resolution_error": null
}
```

### 8.3 PipelineManifest

```json
{
  "run_id": "shadow-...",
  "source_root": "D:\\设计管理",
  "source_records": 498,
  "body_available": 0,
  "parsed": 0,
  "chunked": 0,
  "embedded": 0,
  "indexed": 0,
  "failed": 0,
  "stale": 0,
  "qdrant_collection": "full_corpus_shadow_bge_m3",
  "rollback_target": "previous-shadow-manifest"
}
```

## 9. TASK 拆解

### 016B-1：External Source Discovery

目标：识别真实 PDF/DOCX/XLSX/PPTX，并建立 `SourceRecord` 与 `SourceLink`。

范围：

- Markdown front matter 和链接解析；
- `file://`、绝对路径、相对路径和 Obsidian Wikilink 规范化；
- 路径安全和允许根目录校验；
- `REGISTERED_ONLY`、`BODY_AVAILABLE`、`LINK_BROKEN` 状态；
- 只读扫描报告和测试 fixture。

不做：

- 不写正式 Qdrant；
- 不改变 Retriever；
- 不自动将所有外部文件发布为正式知识。

验收重点：

- BA-003、BA-006、BA-007、BA-009 能识别外部文件候选；
- BA-010 能解析到真实价值创造清单 XLSX 候选；
- 路径不存在或越界时不产生虚假正文。

### 016B-2：Link Expansion and Document Pipeline Closure

目标：将已批准的 SourceLink 展开为真实 Document/SourceBlock/Chunk。

范围：

- Wiki → raw → external source 有向图展开；
- 循环检测、最大深度和失败边；
- PDF/DOCX/XLSX Loader 接入 staging；
- `BODY_AVAILABLE → PARSED → CHUNKED` 状态推进；
- 父页面、登记页、真实文件的 lineage 保存。

重点对象：

- BA-003 工厂产品线方案比选 DOCX；
- BA-004 喷淋/管材实际证据来源；
- BA-006、BA-007 外部 PDF；
- BA-009 2026 年 4 月服务台账 XLSX；
- BA-010 新洲星谷科创中心价值创造清单 XLSX。

不做：

- 不替换正式 Retriever；
- 不修改 8000 服务；
- 不清空或写入正式 Qdrant。

### 016B-3：Index Consistency and Shadow Reconciliation

目标：保证 Chunk、Embedding、Qdrant payload 和 Citation 的一致性。

范围：

- Chunk/Embedding/Qdrant 对账；
- `chunk_id`、`document_id`、sha256 和 location 一致性；
- Shadow collection 独立发布；
- 失败回滚和 stale/invalidate 处理；
- 生成按文档和按 Chunk 的一致性报告。

验收重点：

- 真实文件不存在时不产生 `INDEXED`；
- 登记页已索引但真实正文未索引时仍保持 `REGISTERED_ONLY`；
- Qdrant 点缺 payload 或 Chunk ID 不一致时发布失败并可回滚；
- Citation 能定位到真实文件、Sheet/页码/行号/章节，而不是只定位到登记页。

## 10. 设计完成标准

TASK-016B 设计达到以下条件后，才进入后续实现任务：

1. 外部文件发现、登记、解析、Chunk、Embedding、Qdrant 的状态边界明确；
2. `REGISTERED_ONLY` 不再被误标为可回答正文；
3. Wiki → raw → source 的链路可审计、可回溯、可处理断链；
4. BA-010 的实体页、raw 登记页和外部 XLSX 能形成完整 lineage；
5. 失败不会清空上一版 Shadow 索引；
6. 所有发布前对账结果可输出为机器可读报告；
7. 后续实现仍不需要修改正式 Retriever、8000 服务或正式 Qdrant。

**TASK-016B：知识源闭环修复设计完成。**
