# AI设计管理知识库 V1.0 Metadata Governance 设计

> 任务：TASK-006 Metadata Schema 正式化 + Staging Pipeline 设计  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：已建立正式 Metadata 模块，未接入正式 indexer

## 1. 执行边界

本任务将 TASK-005 的临时 Metadata 提取提升为可复用治理模块，但只接入旁路验证 Pipeline：

- 不替换 `app/indexer.py`；
- 不写入正式 Qdrant；
- 不改变现有运行链路；
- 不修改 `D:\设计管理`；
- 不生成 Embedding；
- Staging JSON 只在内存中生成，不写正式索引目录。

## 2. 新增模块

```text
app/ingestion/metadata/
├─ schema.py
├─ rules.yaml
├─ classifier.py
└─ validator.py
```

另新增旁路 Staging 输出模型：

```text
app/ingestion/staging.py
```

`app/ingestion/pipeline.py` 已改为调用正式 `MetadataClassifier` 和 `validate_metadata`，但没有接入旧 `app/indexer.py`。

## 3. Metadata Schema

### 3.1 基础字段

`MetadataRecord` 必须包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `file_type` | string | 规范化扩展名，如 `.md`、`.pptx`、`.pdf`、`.docx`、`.xlsx` |
| `file_name` | string | 原始文件名 |
| `source_path` | string | 原始知识源路径 |
| `sha256` | string | 文件内容 SHA-256；用于变化检测 |
| `parse_status` | string | parsed、empty、read_error、needs_ocr 等 |

基础字段缺失或为空属于 Schema 错误；`sha256` 必须是 64 位十六进制字符串。

### 3.2 企业知识字段

#### `board`

允许值：

```text
设计管理
技术管理
科技管理
```

#### `knowledge_type`

允许值：

```text
制度
案例
方法
模板
会议资料
培训资料
```

#### `discipline`

允许值：

```text
建筑
结构
机电
BIM
EPC
```

企业知识字段可以为空。空值产生 warning 和待审核状态，不导致文档被拒绝。

### 3.3 治理字段

每个分类字段的判断同时输出：

```text
metadata_source
metadata_rule
metadata_confidence
metadata_review_status
```

当前实现类型：

| 字段 | 类型 | 示例 |
|---|---|---|
| `metadata_source` | object | `{"board": "path", "discipline": "headers"}` |
| `metadata_rule` | object | `{"board": "board_design_management"}` |
| `metadata_confidence` | object | `{"board": 0.98, "discipline": 0.76}` |
| `metadata_review_status` | string | `AUTO`、`NEEDS_REVIEW`、`MANUAL`、`REJECTED` |

## 4. 配置化分类规则

规则文件：

```text
app/ingestion/metadata/rules.yaml
```

规则中配置：

- 字段允许值；
- 规则 ID；
- 关键词；
- 证据来源优先级；
- 不同来源的置信度；
- 自动通过的最低置信度。

### 4.1 证据来源优先级

当前顺序为：

```text
path
  -> file_name
  -> title
  -> headers
  -> body
```

代码只负责加载和执行 YAML 规则，不把企业分类关键词全部硬编码在 Python 中。

### 4.2 置信度规则

当前默认值示例：

| 来源 | 默认置信度 |
|---|---:|
| path | 0.98 |
| file_name | 0.90 |
| title | 0.82 |
| headers | 0.76 |
| body | 0.62 |

分类命中且置信度达到 `0.8`，并且没有其他待复核原因时，可标记 `AUTO`；未命中或低于阈值时标记 `NEEDS_REVIEW`。

### 4.3 未知分类

未知分类不被强行映射到“其他”或某个相近枚举：

```text
字段值：null
metadata_source：unmatched
metadata_rule：no_match
metadata_confidence：0.0
metadata_review_status：NEEDS_REVIEW
```

这样可以区分“确实识别为某类”和“暂时没有证据”。

## 5. Schema 校验

`app/ingestion/metadata/validator.py` 输出：

```python
MetadataValidationResult(
    valid: bool,
    errors: list[str],
    warnings: list[str],
)
```

### 5.1 错误

- 缺少基础字段；
- 基础字段为空；
- `file_type` 格式错误；
- `sha256` 格式错误；
- 企业字段不在允许枚举中；
- 治理字段类型错误；
- 置信度不在 0 到 1 范围；
- `metadata_review_status` 不合法。

### 5.2 警告

- `board` 缺失；
- `knowledge_type` 缺失；
- `discipline` 缺失；
- 自动分类需要人工复核。

Metadata 缺失测试的判定原则是：企业分类字段可以缺失但产生 warning；基础字段缺失则 validation 不通过。

## 6. Staging 输出模型

`app/ingestion/staging.py::build_staging_record()` 在内存中生成 JSON-compatible 字典：

```json
{
  "schema_version": "staging.v1",
  "status": "parsed",
  "metadata": {
    "file_type": ".md",
    "file_name": "example.md",
    "source_path": "D:\\设计管理\\example.md",
    "sha256": "...",
    "parse_status": "parsed",
    "board": null,
    "knowledge_type": null,
    "discipline": null,
    "metadata_source": {},
    "metadata_rule": {},
    "metadata_confidence": {},
    "metadata_review_status": "NEEDS_REVIEW"
  },
  "source_blocks": [],
  "chunks": [],
  "error": null
}
```

### 6.1 输出关系

```text
SourceBlock
  -> Chunk
  -> Metadata 快照
  -> Staging JSON
```

每个 Staging Chunk 保存自己的 `metadata` 快照，使用 `chunk_id` 关联。Staging JSON 不会自动发布到 SQLite、BM25 或 Qdrant。

### 6.2 Staging 验证要求

发布前应检查：

1. SourceBlock 的来源字段存在；
2. Chunk 的 `chunk_id` 唯一；
3. 每个 Chunk 有 Metadata 快照；
4. Metadata Schema 校验通过；
5. location 与文件类型匹配；
6. 文档状态和错误信息完整。

## 7. 真实样本验证

对 `D:\设计管理` 每种支持格式各取 1 个样本，通过正式 Metadata 模块运行旁路 Pipeline：

| 指标 | 结果 |
|---|---:|
| 样本文件 | 5 |
| SourceBlock | 78 |
| Chunk | 164 |
| Metadata 完整 Chunk | 164/164 |
| location 有效 Chunk | 164/164 |
| Staging Schema | `staging.v1` |
| 文件状态 | 5 个 parsed |

所有样本的 `metadata_review_status` 均为 `NEEDS_REVIEW`。这不是解析失败，而是说明当前路径/标题证据不足以让所有企业分类自动确认；基础 Metadata 和 Staging Schema 仍然有效。

真实样本过程中同时修正了 XLSX 首行表头少于后续数据列的边界问题，并新增回归测试。

## 8. 测试结果

新增治理测试覆盖：

- 自动分类；
- 未知分类；
- 低置信度；
- 企业 Metadata 缺失；
- 基础 Schema 缺失；
- 枚举错误和置信度越界；
- Staging JSON 输出模型。

执行结果：

```text
Metadata Governance 测试：6 passed
完整项目测试集：47 passed
```

## 9. 后续接入边界

正式接入 indexer 前仍需：

1. 将 Metadata Schema 迁移到 SQLite `metadata` 结构；
2. 将 Chunk Metadata 写入 Qdrant payload；
3. 增加 Metadata 版本、人工修正和变更日志；
4. 为低置信度标签建立审核入口；
5. 保持软过滤和无结果回退，避免错标造成零召回；
6. 保留 staging 发布、校验、备份和回滚机制。

## 10. TASK-006 验收结论

| 验收项 | 结果 |
|---|---|
| Metadata Schema 定义 | 已完成 |
| 基础字段 | 已完成 |
| 企业字段枚举 | 已完成 |
| YAML 配置化规则 | 已完成 |
| metadata_source | 已完成 |
| metadata_rule | 已完成 |
| metadata_confidence | 已完成 |
| metadata_review_status | 已完成 |
| 自动分类测试 | 已完成 |
| 未知分类测试 | 已完成 |
| 低置信度测试 | 已完成 |
| Metadata 缺失测试 | 已完成 |
| Schema 校验测试 | 已完成 |
| Staging JSON 模型 | 已完成 |
| 未替换 `app/indexer.py` | 是 |
| 未写入正式 Qdrant | 是 |
| 未改变现有运行链路 | 是 |

**TASK-006：完成。**
