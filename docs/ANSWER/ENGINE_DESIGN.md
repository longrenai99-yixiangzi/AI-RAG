# AI 设计管理知识库 V1.0 Answer Engine 设计

> 任务：TASK-013 Answer Engine Architecture Design  
> 正式目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：仅完成架构设计，不修改正式 Retriever、8000 服务或 Qdrant

## 1. 设计目标与现状

Answer Engine 不负责扩大检索范围，也不负责生成向量。它接收已经完成检索和 Citation 定位的 Evidence，负责：

1. 根据 Query Intent 选择回答结构；
2. 从候选证据中选择能够直接支持结论的材料；
3. 将事实、依据、推断和建议分开表达；
4. 为每个重要结论组织可回查的 `[S1]` 引用；
5. 在证据不足、证据冲突或生成服务不可用时稳定拒答或降级。

当前旧链路的主要问题：

- `app/answer.py` 使用一个通用提示词，不能根据制度、案例、方法、模板问题切换回答结构；
- 当前提示词虽然要求输出“结论、制度依据、实施建议、案例参考、来源”，但没有独立的 Answer Policy 和证据选择层；
- 当前 Citation validation 主要校验 `[Sx]` 是否存在，尚未校验“具体结论是否被对应证据支持”；
- 不同文档角色可能同时进入 Context，模型容易把项目案例写成制度要求，或把培训材料写成正式依据；
- 生成模型不可用时，系统可以返回证据，但缺少稳定的“证据不足”结构化表达。

## 2. 目标架构

```text
用户问题
   ↓
Query Intent
   ↓
Answer Policy
   ↓
Evidence Selection
   ↓
Evidence Bundle + Citation Map
   ↓
Structured Draft
   ↓
Citation Validation
   ↓
Final Answer / Evidence-only Fallback
```

Answer Engine 与 Retriever 的边界：

| 模块 | 负责 | 不负责 |
|---|---|---|
| Retriever | 召回、融合、重排候选 Chunk | 组织最终答案 |
| Evidence Selection | 从候选中选择支持当前意图的证据 | 修改 Qdrant 或重新 Embedding |
| Answer Policy | 决定回答章节、证据门槛和拒答策略 | 生成事实 |
| LLM Provider | 根据受限 Evidence 生成草稿 | 自行搜索知识库 |
| Citation Validator | 检查来源标记和 Evidence 映射 | 判断法规效力的最终法律结论 |

第一阶段采用独立 Shadow Answer Engine 验证。正式 `/api/chat` 仍保持当前链路，直到 Gold 评估和回退演练通过。

## 3. Query Intent 到回答策略映射

Query Intent 来源于 Query Analyzer。Intent 不仅决定检索排序，也决定答案章节和证据类型。

### 3.1 策略总表

| Intent | 主要回答目标 | 必须输出 | 首选证据角色 | 禁止混淆 |
|---|---|---|---|---|
| `POLICY_QUERY` | 回答“制度要求是什么” | 结论、管理要求、依据 | 正式制度、管理指南、流程文件 | 不把案例经验写成制度条款 |
| `CASE_QUERY` | 回答“项目发生了什么、怎么做、效果如何” | 背景、措施、效果、经验 | 项目案例、复盘、经验总结 | 不把单个项目做法泛化为强制要求 |
| `METHOD_QUERY` | 回答“应该如何执行” | 流程、步骤、注意事项 | 管理指南、方法手册、标准模板 | 不用述职或汇报材料代替方法依据 |
| `TEMPLATE_QUERY` | 回答“模板怎么用” | 模板用途、字段说明、使用方法 | 标准模板、任务书、表单、清单 | 不只返回模板文件名而不解释字段 |
| `DISCIPLINE_QUERY` | 回答专业设计问题 | 专业结论、适用条件、检查点、依据 | 专业指南、项目案例、标准资料 | 不把单一专业案例扩大为全专业规则 |
| `GENERAL_QUERY` | 在无法可靠分类时给出证据摘要 | 已检索信息、证据边界、待补充项 | 多角色证据，按权威等级排序 | 不强行套用某一种答案结构 |

### 3.2 POLICY_QUERY

回答结构：

```text
结论
管理要求
依据
适用范围/例外（只有证据明确时输出）
```

规则：

1. “结论”只写 Evidence 直接支持的要求，不由模型补造条款编号、发布机关或日期；
2. “管理要求”按动作、责任、输入、输出或检查点拆分；
3. “依据”优先引用正式制度和管理指南；
4. 案例、培训材料只能作为“补充参考”，不能放在正式依据之前；
5. 如果命中的主要是项目总结、述职或培训材料，必须标注“参考材料，不等同于正式制度”；
6. 如果不同制度文件存在版本或要求冲突，必须并列列出版本/来源并标记“需要确认适用版本”。

### 3.3 CASE_QUERY

回答结构：

```text
背景
措施
效果
经验
局限/可迁移条件（证据明确时输出）
```

规则：

1. 背景包括项目、阶段、问题和约束；
2. 措施只描述案例中实际记录的做法；
3. 效果必须有材料依据，没有量化证据时不得编造数字；
4. 经验应区分“案例原文结论”和“基于案例的可迁移建议”；
5. 最终建议必须说明适用前提，不能把一个项目方案表述为企业统一制度。

### 3.4 METHOD_QUERY

回答结构：

```text
流程
步骤
注意事项
输入与输出
检查点（证据有记录时输出）
```

规则：

1. 优先使用管理指南、方法手册、流程文件和任务书；
2. 将连续正文改写为编号步骤时，不得改变原有顺序和责任关系；
3. 缺少前置条件时，明确写“当前证据未说明”；
4. 案例中的步骤可以作为实践示例，但必须标注为案例做法；
5. 不能因为问题包含“如何”就把所有召回结果都强行改写成流程。

### 3.5 TEMPLATE_QUERY

回答结构：

```text
模板用途
字段说明
使用方法
填写/提交注意事项
模板依据与版本
```

规则：

1. 优先返回标准模板、任务书、表单、清单的结构化内容；
2. 字段说明必须保留字段与用途的对应关系；
3. 如果只有案例中出现的表格，必须标注为“案例表格”，不能称为正式模板；
4. 模板文件缺失或内容为空时，只返回可核查的替代资料和缺口，不生成虚构模板字段；
5. 对模板版本、适用项目和责任人信息，只引用证据中明确出现的内容。

### 3.6 DISCIPLINE_QUERY

建议结构：

```text
专业结论
适用条件
专业控制点/检查点
相关案例或方法
依据与边界
```

专业问题应同时检查 discipline、project_stage、building_type 和 document_role。若专业标签不确定，只作为排序信号，不进行硬过滤。

## 4. Evidence Selection 规则

Evidence Selection 位于 Retriever 和 LLM 之间。它不是再次检索，而是从已召回候选中构造“可回答证据集”。

### 4.1 证据排序维度

候选 Evidence 的综合排序建议包含：

```text
evidence_score =
    retrieval_relevance
  + intent_match
  + document_role_match
  + authority_level_match
  + usage_scene_match
  + location_completeness
  - duplicate_penalty
  - contradiction_penalty
```

所有加权均为软排序，不因单个 Metadata 不匹配直接删除候选。具体权重由 Shadow Gold 评估确定，不在本设计阶段固化为正式生产数值。

### 4.2 按 Intent 选择证据

#### POLICY_QUERY

证据优先顺序：

```text
正式制度 > 管理指南/流程 > 标准资料 > 项目案例 > 培训材料 > 汇报材料
```

选择要求：

- 至少保留一条可以直接支持结论的正式或管理指导证据；
- 正式制度和案例不得在同一层级混写；
- 同一文件的相邻 Chunk 可以合并，但必须保留完整 location；
- 同一文档最多保留有限数量的 Chunk，避免单个文件挤占全部 Context；
- 如果没有正式/管理指导证据，降级为“参考性回答”，不能输出确定性制度结论。

#### CASE_QUERY

证据优先顺序：

```text
目标项目案例/复盘 > 同类项目案例 > 方法/指南 > 培训和汇报材料
```

选择要求：

- 尽量覆盖背景、措施、效果三个不同证据段；
- 不能用多个项目的措施拼成一个不存在的项目；
- 如果只找到措施、没有效果证据，明确标记效果缺失；
- 相似项目可以并列比较，但每个事实必须绑定自己的 Citation。

#### METHOD_QUERY

证据优先顺序：

```text
方法/指南/流程 > 标准模板/任务书 > 经验证据 > 培训材料
```

选择要求：

- 优先选择包含动作顺序、责任关系和输入输出的 Chunk；
- 证据只有原则没有步骤时，不应生成过细的操作流程；
- 对互相冲突的流程，保留版本和来源，不静默合并。

#### TEMPLATE_QUERY

证据优先顺序：

```text
标准模板 > 任务书/表单/清单 > 模板使用指南 > 案例表格
```

选择要求：

- 优先保留表头、字段、行列关系和使用说明；
- XLSX 证据必须携带 Sheet、表头和行列定位；
- 案例表格不能自动升级为标准模板。

### 4.3 去重与多样性

Evidence Selection 应执行：

1. `chunk_id` 去重；
2. 同一 `document_id` 的重复段落去重；
3. 相同或高度相似的摘要只保留一份；
4. 在不牺牲高权威证据的前提下，保留不同文档角色或不同项目的必要对照；
5. 版本冲突不得通过去重隐藏，应进入“版本冲突”区域。

### 4.4 证据状态

每条证据进入 Answer Engine 前标记：

| 状态 | 含义 |
|---|---|
| `DIRECT` | 直接回答问题或支持结论 |
| `SUPPORTING` | 提供背景、解释或补充 |
| `CONTEXT_ONLY` | 可帮助理解，但不能单独支持结论 |
| `CONFLICTING` | 与其他证据存在版本、口径或事实冲突 |
| `INSUFFICIENT` | 相关但不足以形成确定性回答 |

LLM 只能把 `DIRECT` 和经过说明的 `SUPPORTING` 用于回答；`CONTEXT_ONLY` 不得被写成结论依据。

## 5. Citation 组织方式

### 5.1 Citation 数据模型

Answer Engine 内部维护“主张—证据”映射：

```json
{
  "claim_id": "C1",
  "claim": "设计评审需要形成问题闭环",
  "evidence_ids": ["S1", "S3"],
  "support_level": "DIRECT",
  "citation_required": true
}
```

Evidence 至少保留：

- `source_id`：如 `S1`；
- `chunk_id`、`document_id`；
- `file_name`、`source_path`；
- `heading_path`；
- `location`；
- `excerpt`；
- `document_role`、`authority_level`、`usage_scene`（存在时）。

### 5.2 面向用户的引用

1. 每个重要事实或管理结论紧邻放置 `[Sx]`；
2. 一个句子包含多个不同来源的事实时，分别放置多个来源标记；
3. 章节末尾可提供“依据”列表，但不能用列表替代正文中的主张关联；
4. 来源标记只能使用实际发送给模型的 Evidence ID；
5. Citation 展示文件名、章节和页/行/页码/Sheet 等定位，不展示无法回查的模糊来源；
6. 不因文件名相似而合并 Citation。

### 5.3 Citation 校验层

校验分三层：

| 层级 | 校验内容 | 失败处理 |
|---|---|---|
| 语法层 | `[S1]` 格式和 ID 是否存在 | 触发修复或拒答 |
| 证据层 | Citation 是否属于发送给模型的 Evidence | 删除无效引用并拒绝对应主张 |
| 覆盖层 | 重要主张是否至少关联一条 Evidence | 标记证据不足，不输出确定性结论 |

现有 `app/answer.py` 的来源标记校验可作为兼容基线；未来增加 Claim-Evidence 对账，但不改变当前 API 响应字段。

## 6. 拒答与证据不足策略

### 6.1 需要拒答或降级的情况

- 没有任何有效命中；
- 命中内容为空、定位缺失或全部为 `CONTEXT_ONLY`；
- 没有证据支持问题要求的核心对象；
- 制度问题只有案例、培训或汇报材料；
- 不同版本或来源对核心要求存在未解决冲突；
- LLM 输出引用不存在、引用覆盖不足或无法通过校验；
- 用户问题超出当前知识库范围。

### 6.2 拒答等级

| 等级 | 输出策略 |
|---|---|
| `NO_EVIDENCE` | 明确说明当前知识库未检索到足够依据，建议缩小问题或补充资料 |
| `PARTIAL_EVIDENCE` | 只回答已被证据支持的部分，列出未覆盖问题 |
| `CONFLICTING_EVIDENCE` | 并列展示冲突来源、版本和差异，不替用户裁决 |
| `GENERATION_UNAVAILABLE` | 返回结构化可核查证据，不伪装成模型生成结论 |
| `CITATION_INVALID` | 不返回未通过引用校验的生成答案 |

### 6.3 事实、推断、建议分离

最终答案建议使用明确标签：

- `知识库结论`：Evidence 直接支持；
- `依据`：对应来源和定位；
- `基于证据的建议`：模型或规则的归纳建议；
- `待核实`：证据不足、版本不明或需要业务负责人确认。

案例经验不能自动写成“公司规定”；缺少正式文件时必须保留这一边界。

## 7. 未来 LLM 调用接口设计

### 7.1 Answer Engine 接口

建议保留与现有 `/api/chat` 兼容的外部调用，同时在内部引入结构化接口：

```text
AnswerEngine.answer(AnswerRequest) -> AnswerResponse
```

`AnswerRequest`：

```text
question
intent
intent_confidence
answer_policy
evidence_bundle
conversation_context（可选）
request_id
```

`AnswerResponse`：

```text
status
answer_text
sections
claims
citations
citation_valid
evidence_status
refusal_reason
model_info
latency
```

### 7.2 Generation Provider

未来 LLM Provider 只接收受限 Evidence，不允许 Provider 自行访问 Qdrant 或本地知识源：

```text
GenerationProvider.generate(
    system_instruction,
    user_question,
    answer_policy,
    evidence_bundle,
    response_schema,
) -> GenerationResult
```

Provider 需要支持：

- 未配置、超时、认证失败、限流和模型错误状态；
- 结构化 JSON 输出或等价 Schema 约束；
- 最大输出长度和超时；
- request_id、model、耗时和错误类别；
- 不输出 API Key，不改变 Citation ID。

### 7.3 两阶段生成

建议采用：

```text
Evidence Selection
   ↓
结构化 Answer Draft
   ↓
Claim-Citation 对账
   ↓失败
Citation Repair / Evidence-only Fallback
```

Citation Repair 只能修复引用和表述，不能增加 Evidence 中不存在的事实。修复仍失败时，返回 `CITATION_INVALID` 或 `PARTIAL_EVIDENCE`。

## 8. 兼容迁移顺序

### 阶段 1：纯规则验证

- 不改变 `app/answer.py`；
- 用 100 题 Gold 验证 Intent 到 Answer Policy 的映射；
- 用 Shadow Evidence 生成结构化回答草稿，不调用正式服务；
- 验证不同文档角色是否被正确分区。

### 阶段 2：Evidence Selection Shadow

- 复用现有 Shadow Retrieval 结果；
- 记录选择前后的文件角色、权威等级、使用场景；
- 比较“直接使用 Top-K”与“按 Answer Policy 选择 Evidence”的 Citation 覆盖；
- 证据不足时只生成降级回答，不改变正式问答。

### 阶段 3：LLM Provider Shadow

- 使用独立 Provider 配置；
- 固定 Evidence Bundle 和 Response Schema；
- 对生成内容执行 Citation validation 和 Claim-Evidence 对账；
- 不把失败请求自动发送到未经批准的外部模型。

### 阶段 4：兼容 API 适配

- 保持当前 `/api/chat` 响应字段；
- 新增字段只能向后兼容地追加；
- 使用 feature flag 控制 Answer Engine；
- 默认保留旧 Answer 路径和 evidence-only 回退。

### 阶段 5：正式切换门槛

只有同时满足以下条件，才考虑进入正式链路：

1. Intent 分层 Gold 评估不低于当前基线；
2. 重要主张 Citation 覆盖率和有效率达到预设门槛；
3. 制度、案例、模板混淆率有可重复的下降证据；
4. 证据不足和 LLM 失败时能够稳定降级；
5. 现有 API、响应和回滚路径通过验证；
6. 内容负责人确认正式制度、管理指南、案例和模板的权威边界。

## 9. 评估指标

Answer Engine 第一阶段不使用 LLM-as-Judge 作为唯一依据，优先使用可确定性检查：

- Intent-specific answer section completeness；
- Claim-Citation coverage；
- Citation ID validity；
- Citation location completeness；
- Unsupported claim count；
- 制度/案例/模板角色混淆率；
- `NO_EVIDENCE`、`PARTIAL_EVIDENCE` 和 `CONFLICTING_EVIDENCE` 的正确触发率；
- 生成失败后的 evidence-only 可用率；
- 端到端延迟和 Token/模型成本。

## 10. 风险控制

| 风险 | 控制 |
|---|---|
| 模型生成强结论 | Answer Policy 限定章节，Claim-Citation 对账 |
| 案例被写成制度 | document_role/authority_level 分层，制度证据门槛 |
| 模板被当作规定 | TEMPLATE_QUERY 专用策略和角色标记 |
| 引用存在但不支持结论 | 覆盖层校验，失败即降级 |
| LLM 不可用 | evidence-only Fallback，不阻塞检索 |
| 版本冲突 | 并列来源、标记待核实，不静默合并 |
| 新链路影响现网 | Shadow、feature flag、旧 Answer 回退 |

## 11. TASK-013 边界确认

| 验收项 | 结果 |
|---|---|
| Query Intent 到回答策略映射 | 已完成 |
| Evidence Selection 规则 | 已完成 |
| Citation 组织方式 | 已完成 |
| 拒答与证据不足策略 | 已完成 |
| 未来 LLM 调用接口 | 已完成 |
| 不修改正式 Retriever | 是 |
| 不修改 8000 服务 | 是 |
| 不修改 Qdrant | 是 |
| 未实现 Answer Engine 代码 | 是 |

**TASK-013：Answer Engine 架构设计完成。**
