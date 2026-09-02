# AI设计管理知识库 V1.0 Staging → Index Pipeline 设计

> 任务：TASK-007 Staging → Index Pipeline 设计  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：完成设计和纯转换骨架，未执行正式发布

## 1. 执行边界

本任务只设计安全发布链路，不改变当前可运行系统：

- 不替换 `app/indexer.py`；
- 不删除旧索引逻辑；
- 不清空 Qdrant；
- 不生成全量 Embedding；
- 不写入正式 Qdrant、SQLite 或 BM25 文件；
- 不修改 `D:\设计管理`。

新增发布骨架：

```text
app/ingestion/publisher/
├─ README.md
├─ staging_reader.py
├─ index_adapter.py
└─ publish_validator.py
```

当前三个模块分别只负责读取、纯数据转换和发布前校验，没有发布写入副作用。

## 2. 总体发布链路

```text
Document Engine
  -> Staging JSON
  -> staging_reader
  -> publish_validator
  -> index_adapter
  -> Embedding Worker（后续授权）
  -> Qdrant / SQLite / BM25 staging artifacts
  -> artifact consistency check
  -> atomic publish
  -> backup / rollback
```

重要原则：

1. Staging 是发布边界，解析和索引写入不直接耦合。
2. 任何校验失败都不能触碰当前正式索引。
3. 新索引必须完整生成并校验后，才能替换正式产物。
4. 旧产物保留到新版本验证完成，失败时可恢复。

## 3. Staging JSON 读取流程

### 3.1 Reader

`app/ingestion/publisher/staging_reader.py` 提供：

```python
read_staging_json(mapping_or_json_or_path) -> StagingDocument
```

支持三种输入：

- Pipeline 内存字典；
- JSON 字符串；
- 已存在的 Staging JSON 文件路径。

Reader 只读取，不创建目录、不修改文件、不启动索引。

### 3.2 Staging 结构

```json
{
  "schema_version": "staging.v1",
  "status": "parsed",
  "metadata": {},
  "source_blocks": [],
  "chunks": [],
  "error": null
}
```

每个 Chunk 中包含自己的 Metadata 快照：

```json
{
  "chunk_id": "stable-chunk-id",
  "document_id": "stable-document-id",
  "source_path": "D:\\设计管理\\example.md",
  "file_name": "example.md",
  "heading_path": "设计管理",
  "location": {"line_start": 1, "line_end": 8},
  "text": "原文片段",
  "metadata": {}
}
```

### 3.3 读取后检查

Reader 后的 `publish_validator` 必须确认：

- Schema 版本支持；
- `status` 存在且可发布；
- `error` 为空；
- Metadata 基础字段和分类治理字段符合 Schema；
- Chunk ID 存在且不重复；
- Chunk 文本和 location 可用；
- `parsed` 文档至少有一个 Chunk；
- `empty` 文档不能含 Chunk；
- `read_error`、`encoding_error` 不得进入发布。

## 4. Chunk 发布流程

### 4.1 发布前

```text
Staging Reader
  -> Metadata Schema 校验
  -> Chunk 唯一性校验
  -> location 校验
  -> 文档 sha256 状态比较
  -> 生成 IndexAdapterPlan
```

`IndexAdapterPlan` 是纯内存对象，包含：

- Qdrant payload 列表；
- BM25 record 列表；
- 每条记录的 `chunk_id` 和 `document_id`。

当前不包含向量，向量生成必须由后续明确授权的 Worker 完成。

### 4.2 未来 Staging artifacts

建议一个发布批次使用独立目录：

```text
data/staging/<batch-id>/
├─ manifest.json
├─ documents.json
├─ chunks.json
├─ qdrant-payloads.json
├─ bm25-records.json
└─ validation.json
```

未来真正写入 Qdrant/SQLite/BM25 前，所有 artifacts 都必须在该目录完成并校验。TASK-007 不创建或写入上述发布目录。

## 5. Metadata 进入 Qdrant payload

### 5.1 Payload 结构

`index_adapter.py::qdrant_payload()` 设计输出：

```json
{
  "chunk_id": "stable-chunk-id",
  "document_id": "stable-document-id",
  "file_name": "example.md",
  "source_path": "D:\\设计管理\\example.md",
  "heading_path": "设计管理",
  "location": {"line_start": 1, "line_end": 8},
  "file_type": ".md",
  "metadata": {
    "board": "设计管理",
    "knowledge_type": "制度",
    "discipline": null,
    "metadata_source": {"board": "path"},
    "metadata_rule": {"board": "board_design_management"},
    "metadata_confidence": {"board": 0.98},
    "metadata_review_status": "NEEDS_REVIEW"
  }
}
```

Qdrant point 的 ID 使用 `chunk_id`。Payload 不保存向量生成过程，只保存检索过滤、调试和 Citation 所需信息。

### 5.2 过滤原则

未来 Retriever 可以按 payload 的 Metadata 候选过滤，但必须：

- 低置信度标签不作为不可回退的硬过滤；
- 过滤后无结果自动回退全库；
- 保留 `metadata_review_status` 供 Debug 使用；
- 不因为 Metadata 为空而删除 Chunk。

## 6. BM25 与 chunk_id 关联

### 6.1 设计

`index_adapter.py::bm25_record()` 输出：

```json
{
  "chunk_id": "stable-chunk-id",
  "document_id": "stable-document-id",
  "text": "原文片段",
  "metadata": {}
}
```

BM25 的词料索引可以继续保存为：

```json
{
  "chunk_ids": ["chunk-1", "chunk-2"],
  "corpus": [["词1", "词2"], ["词3"]]
}
```

`chunk_ids[index]` 必须与 `corpus[index]` 一一对应；BM25 命中后通过 `chunk_id` 回查 SQLite/Chunk，不使用文件名作为主键。

### 6.2 更新约束

- Chunk 文本变化时重新生成该 Chunk 的 BM25 token；
- Chunk ID 不变但文本变化时，必须更新对应语料位置；
- 文档被删除/失效时，BM25 不能保留孤立 chunk_id；
- 新旧 BM25 artifacts 必须在 staging 中完成一致性校验后再替换。

## 7. 增量更新策略

### 7.1 文档状态

以稳定 `document_id` 和文件指纹判断：

| 状态 | 判定 |
|---|---|
| `NEW` | 当前索引无该 `document_id` |
| `UNCHANGED` | path、size、mtime、sha256 均未变化 |
| `MODIFIED` | 任一有效指纹变化 |
| `DELETED` | 上次索引存在，本次只读扫描不存在 |
| `INVALID` | 文件存在但解析/质量校验失败 |

### 7.2 增量批次

```text
扫描文件
  -> 计算 path/size/mtime/sha256
  -> 与 documents 状态表比较
  -> 只为 NEW/MODIFIED 重新解析和切 Chunk
  -> DELETED 进入失效清单
  -> UNCHANGED 复用现有 Chunk/向量/BM25 记录
  -> 在独立 staging artifacts 中组装完整索引
```

第一版仍建议“增量检测 + staging 全量发布”：只减少解析和向量计算，但最终 Qdrant/SQLite/BM25 产物保持完整一致，不做在线局部写入。

## 8. sha256 变化检测

### 8.1 指纹字段

每个文档至少保存：

```text
path
size
mtime_ns
sha256
```

判断优先级：

1. path 用于定位和 document_id；
2. size/mtime 用于快速初筛；
3. sha256 作为内容变化的最终确认。

### 8.2 变化处理

- path 不变、sha256 不变：`UNCHANGED`；
- mtime 变化但 sha256 不变：记录文件状态变化，内容仍可复用；
- sha256 变化：`MODIFIED`，重新解析、切 Chunk、分类和建向量；
- 无法计算 sha256：`INVALID`，不得覆盖旧的有效索引。

## 9. 删除与失效文档处理

### 9.1 删除

扫描结果中不存在但旧索引存在的文档标记为 `DELETED`：

- 进入本次 staging 的删除清单；
- 从新 SQLite documents/chunks 视图中移除或标记 inactive；
- 从新 BM25 record 集合中去除相关 chunk_id；
- 从新 Qdrant collection 计划中去除相关 point ID；
- 不直接在当前正式 Qdrant 上逐条删除。

### 9.2 解析失败

文件仍存在但新解析失败时标记为 `INVALID`：

- 保留错误原因和 sha256；
- 不用失败结果覆盖旧的有效文档索引；
- 发布前由策略决定“保留旧版本”还是“将文档置为失效”；
- 默认安全策略是保留旧有效索引并生成告警。

## 10. 回滚机制

### 10.1 发布前条件

只有满足以下条件才允许从 staging 发布：

- 所有 Staging JSON Schema 校验通过；
- SourceBlock/Chunk/Metadata 数量一致；
- Qdrant point ID 与 Chunk ID 一致；
- BM25 chunk_ids 与 record/corpus 对齐；
- 删除/修改清单已经审计；
- 新 SQLite、BM25、Qdrant artifacts 可独立打开并通过计数校验；
- 向量维度与 BGE-M3 约定一致；
- 当前服务/Worker 进程不占用 Qdrant Local。

### 10.2 原子发布

建议沿用旧 `app/indexer.py` 已验证的发布思想：

1. 为当前正式 artifacts 创建带时间戳的 backup；
2. 将 staging artifacts 原子替换到正式位置；
3. 重新打开并校验 SQLite、BM25、Qdrant；
4. 校验失败时停止服务使用新产物；
5. 将新产物移入 failed-publish 目录；
6. 恢复完整旧 artifacts，包括 SQLite WAL/SHM sidecar；
7. 保留失败报告和 backup 供诊断。

不能只回滚 Qdrant 而不回滚 SQLite/BM25，否则会出现 Chunk ID、来源和检索结果不一致。

## 11. 旧 indexer 逐步迁移

### 阶段 0：当前 TASK-007

- 新 publisher 只读 Staging、生成适配计划、执行校验；
- 旧 `app/indexer.py` 继续是唯一正式索引入口；
- 不改变当前 Qdrant、SQLite、BM25 和 staging 发布行为。

### 阶段 1：Shadow Plan

- 旧 indexer 正常运行；
- 新 publisher 只对同一批 Staging JSON 生成 Qdrant/BM25 计划；
- 比较文档数、Chunk 数、Metadata、Chunk ID、来源定位和失败状态；
- 不写正式索引。

### 阶段 2：受控 Staging 发布

- 新 publisher 写入独立 staging artifacts；
- 旧 indexer 的发布/回滚代码暂时复用；
- 新旧结果通过一致性校验后才允许小样本发布；
- 仍保留旧 indexer 作为回退入口。

### 阶段 3：Worker 接管构建

- Document Worker 负责扫描、解析、Metadata、Chunk 和向量构建；
- Server 只读取已发布索引并提供问答；
- publisher 负责校验、原子替换和回滚；
- 旧 indexer 降级为兼容命令和回滚工具。

### 阶段 4：旧 indexer 退出正式路径

只有在多批次 Gold 问题、Citation、增量、删除和回滚验证通过后，才考虑移除旧 indexer 的正式调用；旧代码仍应保留一段时间作为回退和数据恢复工具。

## 12. TASK-007 边界确认

| 项目 | 结果 |
|---|---|
| Staging JSON 读取骨架 | 已完成 |
| Qdrant payload 适配计划 | 已完成，纯转换 |
| BM25 chunk_id 关联计划 | 已完成，纯转换 |
| 发布前校验 | 已完成，纯校验 |
| 增量更新策略 | 已设计 |
| sha256 变化检测 | 已设计 |
| 删除/失效处理 | 已设计 |
| 回滚机制 | 已设计 |
| 旧 indexer 迁移路径 | 已设计 |
| 未替换 `app/indexer.py` | 是 |
| 未删除旧索引逻辑 | 是 |
| 未清空 Qdrant | 是 |
| 未生成全量 Embedding | 是 |

**TASK-007：完成。**
