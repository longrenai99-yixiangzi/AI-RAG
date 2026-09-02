# AI设计管理知识库：组合式检索与问答下一阶段方案

## 1. 结论

四个开源项目的方式可以组合，但不应直接替换当前系统，也不应复制其中任何一个完整工程。

适合本项目的组合是：

```text
LightRAG 的结构化切分
        ↓
agentic-rag 的文本/结构化双路径检索
        ↓
verified-citations 的逐条证据验证
        ↓
regulated-rag 的生成前门禁与明确降级
```

最终链路：

```text
Question
  ↓
Query Analysis：项目、年份、指标、字段、Intent、Fact Mode
  ↓
Candidate Fusion：BM25 + Dense + Atomic Exact + Document Profile
  ↓
Soft Ranking：RRF + Reranker + Metadata + Scope + Authority
  ↓
Evidence Builder：正文原子证据 + 必要局部上下文 + 精确位置
  ↓
Evidence Verification：支持性、冲突、完整性、引用有效性
  ↓
Answer Router
  ├─ CLAIM_ANSWER_PATH
  ├─ DIRECT_FACT_PATH
  ├─ DERIVED_FACT_PATH
  └─ SAFE_REFUSAL / EVIDENCE_ONLY
```

## 2. 四个项目分别解决什么

| 借鉴来源 | 本项目采用能力 | 不直接采用内容 |
|---|---|---|
| [LightRAG Paragraph Semantic Chunking](https://github.com/HKUDS/LightRAG/blob/main/docs/ParagraphSemanticChunking.md) | 标题层级、父级标题、段落边界、表格行边界、表头保留 | 不替换现有 Document Engine，不整体引入 LightRAG |
| [Rohianon agentic-rag](https://github.com/Rohianon/agentic-rag) | 文本检索与结构化表格检索分路、过召回后软约束、可解释候选 | 不引入其 ChromaDB、OpenAI Embedding 或 Vision LLM 依赖 |
| [agentic-rag-verified-citations](https://github.com/deepeshgupta12/agentic-rag-verified-citations) | 原子引用、行级表格引用、逐 Claim 校验、冲突与证据缺口 | 不复制其业务领域 Prompt 和评分数据 |
| [regulated-rag](https://github.com/RZ-Logic/regulated-rag) | 生成前证据门禁、生成后引用检查、Typed Refusal | 不复制其监管领域规则和语料结构 |

## 3. 已有基础

当前已经完成：

- Markdown、PDF、DOCX、PPTX、XLSX Loader；
- SourceBlock、Chunk、Metadata、Document Profile；
- BM25、Dense、RRF、Reranker Shadow；
- Root-001 与选择性 Root-002 Shadow；
- Query Intent、Fact Mode、Answer Router；
- Claim Validator、Citation Validator、Section Mapping；
- DIRECT_FACT 与 DERIVED_FACT 路径；
- BA-010 确定性表格统计；
- 原子证据 29,027 条及精确 location；
- 项目、年份、指标、字段约束的 Shadow 原子检索；
- 8010 Internal Trial、日志与业务反馈。

当前主要缺口：

1. BA-001～BA-010 的 `expected_files` 和 `expected_locations` 尚未正式确认；
2. Root-002 已批准资料尚未统一转换为原子证据；
3. 原子精确检索尚未与 BM25、Dense、RRF 的候选池正式融合；
4. 登记页、正文、表格事实、案例和制度之间仍可能互相干扰；
5. Evidence Bundle 尚缺统一的支持性、冲突和覆盖度判断；
6. Provider 关闭时，普通问题只能返回 Evidence，不能形成完整自然语言答案。

## 4. 下一阶段任务

### TASK-020A：Business Gold Evidence Confirmation

目标：建立可计算、可人工复核的真实业务 Gold。

实施：

- 逐题确认 BA-001～BA-010 的正确文件；
- 记录正确页、段、行、Sheet、字段和表格行；
- 增加 `expected_locations`、`expected_fields`、`expected_fact_mode`；
- 区分 `GOLD_IN_ROOT`、`GOLD_OUT_OF_SCOPE`、`GOLD_UNCONFIRMED`；
- 不使用候选排名自动替业务负责人确认 Gold。

验收：

- 10题均有明确 Gold Scope；
- 已确认题均有文件和位置；
- Gold 中不包含登记页或链接页作为正文证据。

### TASK-020B：Multi-Root Atomic Evidence Closure

目标：让批准的 Root-002 文件也能按行、段、页、Sheet 精确检索。

实施：

- 只处理已批准的 Root-002 P0/P1 范围；
- 复用现有 `atomic_evidence.py`；
- 每条证据增加 `knowledge_root_id`、`source_status`、`approval_status`；
- Excel 保留表头、单元格、公式/缓存值和行号；
- Root-001、Root-002 分别生成 JSONL，不混写源文件；
- 用统一只读 Candidate Pool 查询两个 Root。

验收：

- 原子证据 location 完整率 100%；
- Root 边界和审批状态完整率 100%；
- BA-003、BA-006、BA-007、BA-009、BA-010 的目标外部正文可追溯；
- 不写正式 Qdrant。

### TASK-020C：Hybrid Candidate Fusion V1

目标：把“语义召回”和“精确事实定位”真正融合。

候选来源：

```text
BM25
Dense
RRF
Document Profile
Atomic Exact Search
Structured Table Candidate
```

实施：

- 各来源先过召回，进入统一 Candidate Pool；
- 按 `document_id + evidence_id/chunk_id` 去重；
- 保留 `candidate_origin` 和各阶段排名；
- 项目、年份、指标、字段、Scope、Role、Authority 全部软加权；
- 不因 Metadata 缺失删除候选；
- 目标文件存在但无直接证据时返回诊断，不强行回答。

验收：

- 已确认 Gold 题目标文件 Top-5 不低于当前最佳基线；
- BA-004、BA-007、BA-008、BA-010 不回退；
- 登记页不得成为最终 Evidence；
- 仍失败题能够区分 Source、Retrieval、Ranking 或 Evidence Failure。

### TASK-020D：Verified Evidence Bundle V1

目标：从“找到候选”升级为“证据能够支持回答”。

实施：

- 原子证据按文档和事实聚合；
- 为每条 Evidence 标记能力：`DEFINITION`、`FORMULA`、`DIRECT_FACT`、`METHOD`、`EXAMPLE`、`TABLE_ROW`；
- 文本证据保留局部上下文窗口，但 Citation 指向原子位置；
- 表格行始终携带表头；
- 检查 Evidence 是否覆盖问题要求的各个 Facet；
- 同范围数值冲突时标记 `EVIDENCE_CONFLICT`；
- 证据不完整时标记缺失字段，不送 LLM 猜测。

验收：

- Citation location 完整率 100%；
- Invalid Evidence ID = 0；
- 登记页/标题页作为事实证据 = 0；
- 冲突数值不得自动择一；
- 每个最终 Claim 均能反查原文。

### TASK-020E：Answer Router & Safety Gate Integration

目标：根据问题性质选择正确回答方式。

路由：

- 普通制度、方法、案例：`CLAIM_ANSWER_PATH`；
- 原文直接存在的金额、日期、数量：`DIRECT_FACT_PATH`；
- 需要分组、求和、筛选、去重：`DERIVED_FACT_PATH`；
- 结构化来源或业务口径缺失：`FACT_PATH_UNAVAILABLE`；
- Evidence 不足：`EVIDENCE_ONLY` 或 `SAFE_REFUSAL`；
- Provider 故障：`PROVIDER_TEMPORARY_FAILURE`，不得伪装成知识不足。

实施：

- 生成前执行 Evidence Sufficiency Gate；
- LLM 只生成原子 Claim，不负责 Citation 和表格计算；
- Citation 由后端根据 Evidence ID 确定性渲染；
- Claim Validator 和 Citation Validator 保持严格；
- Provider 关闭时保留可核查 Evidence 与明确提示。

验收：

- Unsupported Claim = 0；
- Citation Consistency = 100%；
- DIRECT_FACT 不误进表格聚合；
- DERIVED_FACT 不允许 LLM 心算；
- Provider Failure 与业务拒答严格区分。

### TASK-020F：Internal Trial A/B Business Acceptance

目标：在 8010 上比较旧 Shadow 与组合式新链路。

实施：

- 每题同时保存 Baseline 和 Combined 结果；
- 记录候选、Evidence、路由、回答状态和引用；
- 业务负责人评价：是否回答问题、结论是否明确、证据是否合适、是否可直接使用；
- 反馈保存为 Gold 修订建议，不自动写回知识库。

验收：

- 先通过 BA-001～BA-010；
- 再扩展到不少于50道已确认 Gold；
- 检索指标不得回退；
- 人工验收确认后，才提出正式链路切换计划。

## 5. 推荐执行顺序

```text
020A Gold确认
  ↓
020B Root-002原子证据闭环
  ↓
020C 候选融合
  ↓
020D Evidence验证
  ↓
020E Answer路由与安全门禁
  ↓
020F 8010业务A/B验收
```

不得跳过 020A。没有正确文件和位置，后续任何 Recall、MRR 或“准确率提升”都不可信。

## 6. 本阶段明确不做

- 不替换 BGE-M3；
- 不替换现有 Qdrant；
- 不重写 Document Engine；
- 不引入新的向量数据库；
- 不重新训练模型；
- 不让 LLM 计算表格数字；
- 不把 Root-002 未批准目录纳入检索；
- 不直接修改正式 8000 服务。

## 7. 正式链路准入条件

只有同时满足以下条件，才讨论进入正式 Retriever：

1. Gold 文件和位置已经由业务确认；
2. Shadow 检索指标不低于当前基线；
3. 引用位置完整率 100%；
4. Unsupported Claim = 0；
5. Fact 计算可逐行复核；
6. Provider 故障不影响确定性事实回答；
7. 业务人工验收达到可用标准；
8. 正式索引具备回滚方案。
