# AI设计管理知识库 V1.0 Retrieval Pipeline 设计

> 任务：TASK-009 Retrieval Pipeline V1 设计  
> 正式目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：仅完成架构设计和骨架，未实现完整代码

## 1. 设计边界

V1 Retrieval Pipeline 位于 Document Engine 输出和 Answer/Citation 之间：

```text
Document Engine
  -> Chunk + Metadata
  -> Indexes
  -> Query Analysis
  -> Hybrid Retrieval
  -> RRF
  -> Deduplicate
  -> Reranker
  -> Evidence/Context/Citation
  -> Answer Engine
```

本任务不执行：

- 替换现有问答链路；
- 删除旧 `app/retriever.py`；
- 接入生产 Qdrant；
- 生成全量 Embedding；
- 修改 `D:\设计管理`。

新设计骨架位于：

```text
app/retrieval/
├─ query_analyzer.py
├─ hybrid_retriever.py
├─ rrf.py
├─ reranker.py
└─ context_builder.py
```

这些模块当前不被 `app/main.py` 或旧 Retriever 导入。

## 2. Query Analysis

### 2.1 问题类型

分析结果至少包含：

| 类型 | 典型意图 | 默认回答倾向 |
|---|---|---|
| `POLICY_QUERY` | 制度、规则、要求、流程 | 制度证据优先，必须引用 |
| `CASE_QUERY` | 项目案例、经验、复盘 | 案例证据汇总，不能写成制度 |
| `METHOD_QUERY` | 如何做、步骤、方法 | 方法/指南/手册优先 |
| `TEMPLATE_QUERY` | 模板、任务书、表单、栏目 | 模板和结构化资料优先 |
| `DISCIPLINE_QUERY` | 建筑、结构、机电、BIM、EPC 专业问题 | 专业 Metadata 辅助过滤 |
| `GENERAL_QUERY` | 无法归入以上类别 | 使用通用混合检索，不强制分类 |

规则分析不是最终答案。无法判断时使用 `GENERAL_QUERY`，不能因为分类不确定而拒绝检索。

### 2.2 Metadata 候选

Query Analysis 产生候选值和置信度：

```json
{
  "board": {"value": "设计管理", "confidence": 0.86},
  "knowledge_type": {"value": "制度", "confidence": 0.78},
  "discipline": {"value": "EPC", "confidence": 0.91}
}
```

候选来源：

1. 问题中的明确词；
2. 问题类型词；
3. 同义词/词典；
4. 项目、专业、业态和阶段词。

约束：

- 低置信度候选只能用于排序加权或软过滤；
- 不允许一个自动标签直接造成零召回；
- 无结果时自动回退全库；
- Debug 必须记录原问题、分类、候选值和置信度。

## 3. Hybrid Retrieval

### 3.1 BM25

BM25 使用 Chunk 文本和必要的结构化投影：

- 正文文本；
- heading_path；
- Markdown 标题/关键词；
- PPTX 标题、页号相关文本；
- PDF 页文本；
- DOCX 标题和表格文本；
- XLSX Sheet、表头和列名关系。

BM25 返回：

```text
(chunk_id, bm25_score, bm25_rank)
```

`chunk_id` 是唯一关联键，不使用文件名或数组位置作为长期身份。

### 3.2 Dense Vector

Dense 检索保留现有 BGE-M3 和 Qdrant 能力：

- Query 使用 BGE-M3 生成向量；
- Chunk 向量在后续 Worker/Index Pipeline 中生成；
- Qdrant payload 保存 chunk_id、document_id、source_path、location 和 Metadata；
- 当前 V1 仍保持 1024 维 Cosine 约定；
- 本设计阶段不生成全量 Embedding、不连接生产 Qdrant。

Dense 返回：

```text
(chunk_id, dense_score, dense_rank)
```

### 3.3 Metadata 辅助

Metadata Filter 采用软策略：

1. 先执行 BM25 + Dense 候选召回；
2. 对高置信度候选进行优先排序或候选过滤；
3. 低置信度标签不做硬门槛；
4. 过滤后无结果时回退未过滤候选；
5. 记录过滤前后数量及回退原因。

## 4. RRF 融合设计

### 4.1 公式

对每个候选 `chunk_id`：

```text
RRF(chunk_id) = Σ 1 / (k + rank_i(chunk_id))
```

约定：

- rank 从 1 开始；
- 未出现在某路结果中的候选该路贡献为 0；
- `k` 默认 60，与现有 `app.retriever.py` 的纯函数基线一致；
- 结果按 RRF 分数降序；
- 分数相同使用稳定的候选来源顺序和 chunk_id 作为确定性 tie-break；
- 同一个 chunk_id 在融合结果中只保留一次。

### 4.2 输入输出

```text
输入：
  bm25 ranked chunk_id list
  dense ranked chunk_id list

输出：
  chunk_id
  rrf_score
  bm25_rank
  dense_rank
  retrieval_sources
```

RRF 只负责排序融合，不负责文本读取、Metadata 判断、向量生成或 Citation。

## 5. Reranker 接口设计

### 5.1 Provider 接口

建议接口：

```text
score(query, candidates) -> ordered scores
```

候选至少包含：

- chunk_id；
- chunk text；
- heading_path；
- Metadata；
- location。

实现边界：

- 继续使用现有 `bge-reranker-v2-m3` 能力；
- Provider 不负责 Qdrant/BM25；
- 支持 `disabled`、`ready`、`failed` 状态；
- `auto` 模式失败时返回预重排顺序；
- `on` 模式失败时报告明确错误；
- 记录模型、设备、耗时、候选数和失败原因。

### 5.2 重排位置

```text
BM25 + Dense
  -> RRF
  -> 去重
  -> 取候选 Top-N
  -> Reranker
  -> Final Top-K
```

Reranker 不应在全库运行，只对 RRF 后的有限候选运行，以控制延迟和显存/内存成本。

## 6. Citation 与 Context 设计

### 6.1 Context Builder

`context_builder.py` 负责：

1. 接收 final hits；
2. 对每个实际发送给 Answer Engine 的 Chunk 分配 `[S1]`、`[S2]`；
3. 生成结构化 Evidence；
4. 限制上下文总字符和单 Chunk 文本长度；
5. 保留来源顺序、检索分数和定位；
6. 返回 `context_text + allowed_sources`。

### 6.2 Citation 字段

每条 Citation 至少包含：

```text
source_id
file_name
source_path
file_type
heading_path
location
excerpt
chunk_id
document_id
```

不同格式的定位：

| 类型 | Citation 定位 |
|---|---|
| Markdown | line_start/line_end + heading_path |
| PPTX | slide + title |
| PDF | page |
| DOCX | paragraph_start/end 或 table |
| XLSX | sheet_name + row_start/end + header_row |

Citation 不根据模型答案猜测来源，不引用未发送给模型的 Chunk。来源标记校验失败时，答案不能被当作可信生成结果。

### 6.3 与现有 Answer 的关系

当前 `app/answer.py` 已有 `_context()`、`[S1]` 标记和 Citation validation。新 `context_builder.py` 应先以兼容输出为目标，待 Shadow 验证通过后再替换内部实现，避免改变现有 `/api/chat` 响应。

## 7. Retrieval Debug

每次检索建议记录：

```text
原问题
QueryAnalysis
关键词
Metadata 候选及置信度
BM25 命中数/Top IDs
Dense 命中数/Top IDs
RRF 候选及分数
去重结果
Reranker 是否使用、耗时和前后顺序
Metadata Filter 前后数量
是否回退全库
最终 Evidence/Citation
```

这些信息用于解释“为什么没有命中正确资料”，不应将内部调试信息全部发送给 LLM。

## 8. 与 Gold Question 评价体系结合

输入集：

```text
tests/gold_questions/golden_questions.yaml
```

当前包含 10 个问题，覆盖制度、案例、方法、模板和专业查询。

### 8.1 检索指标

第一阶段只做确定性 Retrieval 评价：

- Recall@1；
- Recall@3；
- Recall@5；
- MRR；
- expected_keywords 覆盖率；
- expected_metadata 命中率；
- Metadata Filter 前后变化；
- Reranker 前后 Top-K 变化；
- Citation location 完整率。

不在第一阶段使用 LLM-as-Judge，不用模型主观评价替代文件/Chunk 命中证据。

### 8.2 旧/新对照

每个 Gold Question 保存：

```text
question
category
expected_keywords
expected_metadata
expected_files（人工核验后）
old_baseline_hits
new_pipeline_hits
rerank_delta
citation_check
```

旧侧和新侧必须使用相同问题、相同 Top-K 和相同评价口径。当前 `RETRIEVAL_BASELINE.md` 的 BM25-only 结果只是准备阶段基线，不是最终 V1 指标。

## 9. 兼容迁移顺序

### 阶段 1：设计/纯函数验证

- 保留旧 `app/retriever.py`；
- 实现 Query Analysis、RRF、Citation 的独立单元测试；
- 使用 Gold Questions 和内存 BM25 进行无副作用测试。

### 阶段 2：Shadow Hybrid

- 新 Pipeline 生成 Chunk/Metadata；
- 使用 staging/index adapter 的计划数据；
- Dense 只连接独立测试 Qdrant 或 mock，不连接生产 collection；
- 与旧 Retriever 比较 Top-K、文件、Chunk ID 和 Citation。

### 阶段 3：兼容 API 适配

- 保持 `/api/chat` 请求/响应字段；
- 将新 Retriever 包装在 feature flag 后；
- 默认继续走旧 Retriever；
- Debug 模式下并行记录新结果，但不改变答案。

### 阶段 4：小范围切换

- 通过 Gold Recall、Citation、延迟和失败回退门槛；
- 先切换只读测试用户或离线评测；
- 保留旧 Retriever 和回滚开关。

### 阶段 5：正式替换评估

只有在新旧对照稳定、生产索引发布和回滚演练通过后，才考虑让新 Pipeline 成为默认检索链路。旧 Retriever 不应在第一轮迁移中删除。

## 10. 风险与控制

| 风险 | 控制措施 |
|---|---|
| Query Analysis 错判 | 低置信度不硬过滤，回退全库 |
| Metadata 错标零召回 | 软过滤 + 全库回退 + Debug 记录 |
| Dense 模型未加载 | 明确 degraded 状态，可退回 BM25 基线 |
| Reranker 失败 | `auto` 回退 RRF 顺序，保留告警 |
| Chunk ID 变化 | Shadow 对照、Chunk version、受控重建 |
| Citation 错位 | location Schema 校验和来源回查 |
| Qdrant Local 锁 | 生产发布前隔离 Server/Worker 生命周期 |
| 新链路影响问答 | 默认旧 Retriever，feature flag 小范围切换 |

## 11. TASK-009 边界确认

| 验收项 | 结果 |
|---|---|
| Query Analysis 设计 | 已完成 |
| Metadata 候选识别 | 已完成 |
| BM25/Dense Hybrid 设计 | 已完成 |
| RRF 算法设计 | 已完成 |
| Reranker 接口设计 | 已完成 |
| Citation/Context 设计 | 已完成 |
| Gold Question 评价结合 | 已完成 |
| 不替换现有问答链路 | 是 |
| 不删除旧 Retriever | 是 |
| 不接入生产 Qdrant | 是 |
| 未写完整检索代码 | 是 |

**TASK-009：架构设计完成。**
