# Evidence Ranking Diagnosis & Optimization Report

> TASK-016D-1：基于 TASK-016C-3 Regression Report，对 Shadow Root-002 的 Evidence Ranking / Selection 失败进行诊断和最小修改方案设计。
>
> 本任务只输出方案，不修改正式 Retriever、Answer Engine、8000 服务或正式 Qdrant。

## 1. 结论摘要

当前主要问题不是“没有召回候选”，而是候选进入 Evidence Bundle 前发生了三类偏差：

1. Evidence Selection 按文档角色、文档分数和多样性排序，但没有把“问题对应的答案片段”作为第一优先级。
2. 角色优先级没有严格落实到最终顺序。例如模板问题中，案例 Chunk 可能排在管理指南之前；案例问题中，管理指南可能压过案例。
3. 同一目标文件最多只保留两个 Chunk，并执行角色/文档多样性。这会把 BA-010 这类“清单统计”问题的同一目标 Excel 片段挤出 Evidence。

另一个事实是：C-3 实际运行没有使用 Reranker，持久化结果中的 `reranker_used=false`。因此不能把 C-3 的失败归因于“Reranker 排序错误”；当前证据只支持“RRF 后的候选进入 Evidence Selection 时发生偏差”。

## 2. 当前排序链路

### 2.1 设计链路

```text
问题
  ↓
Query Intent
  ↓
BM25 Top-20 ─────┐
                  ├─ RRF 融合
BGE-M3 Dense Top-20 ┘
  ↓
Reranker
  ↓
Evidence Selection
  ├─ 文件级聚合
  ├─ document_score
  ├─ document_role / authority_level
  ├─ Evidence Diversity
  └─ 最多 5 个 Evidence、单文档最多 2 个 Chunk
  ↓
Evidence Bundle
  ↓
Answer Engine
```

### 2.2 C-3 实际执行链路

| 环节 | C-3 实际情况 |
|---|---|
| BM25 | 每题返回 20 个候选 |
| Dense | BGE-M3，每题返回 20 个候选 |
| RRF | 已执行；融合候选数为 32～40 |
| Reranker | 未执行，`reranker_used=false` |
| Evidence Selection | 已执行文件级聚合、角色多样性和最多 5 条 Evidence |
| Answer Engine | 使用当前 Shadow Answer Engine，不修改代码 |

### 2.3 当前 Evidence Selection 的结构性偏差

现有 `select_evidence_optimized` 的主要排序因素是：

- 最高检索分数；
- 文档角色是否在 Answer Policy 的 preferred_roles；
- 同一文档命中的 Chunk 数；
- 角色多样性。

缺少以下排序因素：

- 文件名是否直接命中问题中的项目、年份、清单或制度名称；
- Heading / Sheet / Page 是否命中问题实体；
- Chunk 是否包含问题所需的数值、专业、措施或条款片段；
- Gold Evidence 是否属于当前 Knowledge Root；
- 目标文件已经被召回时，是否应该优先保留该文件的多个连续证据片段。

因此，当前的“角色正确”不能等同于“答案证据正确”。

## 3. 数据完整性限制

C-3 持久化了：

- BM25 命中数量；
- Dense 命中数量；
- RRF 融合数量；
- `reranker_used`；
- 最终 S1～S5 Evidence；
- Source、Location、Excerpt 和 Answer Status。

C-3 没有持久化：

- BM25 Top-20 的 Chunk ID 与排名；
- Dense Top-20 的 Chunk ID 与排名；
- RRF 后每个 Chunk 的分数与排名；
- Reranker Top-N 的分数与排名。

因此，本报告中“Top20 候选”只能准确记录为：

> Top20 具体条目未持久化；已知 BM25=20、Dense=20、RRF 融合数，以及最终 Evidence S1～S5。不能把 S1～S5 反推为 Top20。

后续任何声称“某 Chunk 在 BM25/Dense/RRF 排名第几”的结论，都必须先补充检索轨迹持久化。

## 4. 六题逐题诊断

### BA-001：设计任务书需要包含哪些内容？

- Query Intent：`TEMPLATE_QUERY`
- C-3 状态：`PARTIAL_EVIDENCE`
- C-3 候选轨迹：BM25 20、Dense 20、RRF 32、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1/S2：之寓保税区人才公寓设计管理经验总结，标准模板 / 项目案例；
  - S3：`《项目设计管理手册》.pdf`，管理指南，L2；
  - S4/S5：河北科技师范学院项目经验总结，标准模板 / 项目案例。
- Gold Evidence：`D:\设计管理\wiki\concepts\设计支持\设计任务书.md`，位于 Root-001，不在本次 Root-002 Shadow 范围。
- Root-002 可用支撑：`《项目设计管理手册》.pdf` 第 17 页，包含项目概况、工作范围、工作要求、设计技术要点等内容。

差异：

1. Gold 主证据不属于 Root-002，不能把本题完全恢复归因于 Root-002。
2. 在当前 Evidence 内，模板 S1 后面出现了案例 S2，再出现指南 S3；不符合“模板 > 制度 > 案例”的严格顺序。
3. 本题应优先保留管理手册中的制度化定义，再用项目案例作为补充，而不是让多个项目案例占用 Evidence 名额。

诊断：`ROOT_SCOPE_MISMATCH + TEMPLATE_ROLE_ORDER_FAILURE`。

### BA-002：设计效益增量的计算方式？

- Query Intent：`METHOD_QUERY`
- C-3 状态：`NO_EVIDENCE`
- C-3 候选轨迹：BM25 20、Dense 20、RRF 34、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1/S2：光谷实验中学项目经验总结；
  - S3：半年运营会资料；
  - S4：河北科技师范学院 EPC 总结；
  - S5：华师南湖训练馆项目经验总结。
- Gold Evidence：`D:\设计管理\wiki\queries\设计创效价值创造问答.md`，位于 Root-001，不在 Root-002。

差异：

1. 最终 Evidence 以项目案例为主，没有稳定的方法指南或计算口径文件。
2. 结果中有“效益率增量”“创效金额”等事实，但没有形成可复用的计算方法证据。
3. `METHOD_QUERY` 应优先方法指南、制度化计算口径，再使用项目案例说明示例。

诊断：`ROOT_SCOPE_MISMATCH + METHOD_ROLE_ORDER_FAILURE`。

### BA-003：厂房产品线的方案比选案例包含哪些专业？

- Query Intent：`CASE_QUERY`
- C-3 状态：`GENERATED`，但业务回归判定仍失败。
- C-3 候选轨迹：BM25 20、Dense 20、RRF 40、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1/S2：项目设计管理手册，管理指南；
  - S3：设计与技术支持中心联动方案，被治理为项目案例；
  - S4：应城智汇港设计管理策划书，标准模板；
  - S5：星谷科创中心设计管理策划书，标准模板。
- Gold Evidence：厂房产品线案例汇编的外部 DOCX；Root-001 登记页为 `REGISTERED_ONLY`，不在本次 Root-002 批准范围。

差异：

1. 这是案例问题，但最终 Evidence 首位是管理指南，且没有命中厂房案例正文。
2. S4/S5 是策划书模板，不是厂房产品线案例，容易造成“模板代替案例”。
3. Root-002 中仅有一处弱关键词匹配，不足以证明厂房案例答案存在。

诊断：`SOURCE_SCOPE_MISSING + CASE_ROLE_ORDER_FAILURE + TEMPLATE_AS_CASE_CONFUSION`。

### BA-007：2026 年设计示范项目的打造要求是什么？

- Query Intent：`POLICY_QUERY`
- C-3 状态：`STRUCTURE_INVALID`
- C-3 候选轨迹：BM25 20、Dense 20、RRF 37、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1：`关于印发中建三局2026年设计与技术工作计划的通知.pdf`，管理指南，L2；
  - S2/S3：公司复盘 EPC 项目管理台账，项目案例，L4；
  - S4/S5：第二建设公司 2026 年设计与技术（科技）工作计划 PDF，管理指南，L2。
- Gold Evidence：S1 对应的 2026 年设计与技术工作计划 PDF，属于 Root-002，源文件、解析、Chunk、Embedding 均已完成。

差异：

1. 目标 PDF 已被召回，但最终 Evidence 没有体现“示范项目打造要求”的精确章节/页面；同一目标文件的相关片段没有形成连续证据。
2. S2/S3 案例占用了两个 Evidence 名额，削弱了制度/工作计划证据的集中度。
3. `POLICY_QUERY` 应执行“制度 > 指南 > 案例”；当前治理字段只有“管理指南”，没有把正式计划文件提升为更高的制度优先级。
4. 最终失败状态是结构异常，不应掩盖前面的 Evidence Span 选择不足。

诊断：`TARGET_FILE_RECALLED_BUT_SPAN_NOT_SELECTED + POLICY_ROLE_ORDER_FAILURE + ANSWER_STRUCTURE_FAILURE`。

### BA-008：2025 年公司设计创效金额是多少元？

- Query Intent：`CASE_QUERY`
- C-3 状态：`NO_EVIDENCE`
- C-3 候选轨迹：BM25 20、Dense 20、RRF 39、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1：华师南湖训练馆项目经验总结，项目案例；
  - S2：2025 年设计管理工作计划，管理指南；
  - S3/S4：丰台崔村旧改项目 PPT，项目案例；
  - S5：泸州垃圾焚烧发电项目经验总结，项目案例。
- Gold Evidence：TASK-016A 使用的 2025 年设计管理总结/述职类资料，主要位于 Root-001；Root-002 的 2025 工作计划不是同一事实源。

差异：

1. CASE_QUERY 的角色顺序大体偏向案例，但没有确保“公司级金额事实”来自公司级汇总文件。
2. 项目案例中的单项目金额、创效率可能被误当成公司年度总额。
3. 该问题必须增加“公司级 / 年度 / 金额”事实约束，不能仅以“创效”关键词排序。

诊断：`FACT_SCOPE_MISMATCH + COMPANY_TOTAL_VS_PROJECT_CASE_CONFUSION`。

### BA-010：星谷科创中心设计价值创造清单包含哪些专业、多少条、增加效益多少？

- Query Intent：`TEMPLATE_QUERY`
- C-3 状态：`NO_EVIDENCE`
- C-3 候选轨迹：BM25 20、Dense 20、RRF 36、Reranker 未运行；Top20 具体条目未持久化。
- 最终 Evidence：
  - S1：华师南湖训练馆价值创造实施清单，标准模板 / 案例；
  - S2：设计支持管理细则，管理指南；
  - S3：星谷设计策划评审意见表，管理指南；
  - S4/S5：哈密项目设计管理 PPT，项目案例。
- Gold Evidence：Root-002 中的 `方案比选与价值创造清单方案比选及价值创造.xlsx`，重点 Sheet 为“价值创造”；关联的 `设计管理策划书-星谷科创中心项目.docx` 也属于批准范围。

差异：

1. 目标 Excel 已进入 Root-002 Shadow，但没有进入最终 Evidence；最终证据停留在“价值创造相关”的通用案例、制度和评审意见。
2. 这是清单统计问题，需要同一目标 Workbook 的多个 Sheet / 多个 Chunk 协同回答；当前“单文档最多 2 Chunk + 角色多样性”会主动削弱目标 Workbook。
3. `TEMPLATE_QUERY` 的角色排序本身没有完全错误，主要失败在缺少“目标文件名 / Sheet 名 / 项目实体”的强锚定。
4. LLM 返回 `NO_EVIDENCE` 是安全结果，不应通过放宽 Claim Validator 解决。

诊断：`TARGET_WORKBOOK_NOT_SELECTED + ENTITY_FILE_ANCHOR_MISSING + MULTI_CHUNK_QUOTA_TOO_STRICT`。

## 5. Evidence 角色排序规则

以下规则只作为 Shadow 软排序规则，不作为硬过滤规则。任何角色不匹配的候选仍可保留为回退证据，但不能压过首选角色的直接证据。

### 5.1 TEMPLATE_QUERY

```text
目标模板 / 清单 / 任务书
  > 制度或管理指南
  > 项目案例 / 复盘
```

重点：优先目标文件、表格结构、字段定义和 Sheet 名；项目案例只能作为使用示例。

### 5.2 POLICY_QUERY

```text
正式制度
  > 管理指南 / 工作计划
  > 标准模板
  > 项目案例 / 复盘
```

重点：按发布机关、文件标题、年份、制度/计划章节提升权威性；案例不得覆盖制度原文。

### 5.3 CASE_QUERY

```text
目标项目案例
  > 项目复盘 / 经验总结
  > 标准模板
  > 管理指南
```

重点：项目名称、产品线、专业、措施、效果和创效数字必须与问题实体一致；模板不能代替案例。

### 5.4 METHOD_QUERY

```text
方法指南 / 流程 / 手册
  > 标准模板 / 方法表单
  > 项目案例
```

重点：先选能给出步骤、计算口径、检查点的资料，再用案例解释落地方式。

### 5.5 DISCIPLINE_QUERY

```text
对应专业资料 / 专业图审要点 / 专业标准
  > 对应专业项目案例
  > 通用管理指南
```

重点：专业实体、设备/系统名称、设计阶段和适用环境必须共同匹配；仅包含“电气”“结构”等单一词不能算专业命中。

## 6. 最小修改方案（只设计，不编码）

### P0-1：补齐逐阶段检索轨迹

下一轮 Shadow 评估必须逐题保存：

- BM25 Top20：Chunk ID、文件名、分数、排名；
- Dense Top20：Chunk ID、文件名、分数、排名；
- RRF：融合分数、排名、来源列表；
- Reranker：是否执行、分数、排名；
- Evidence Selection：被选中/被淘汰原因。

没有这份轨迹，不能可靠判断是 BM25、Dense、RRF、Reranker 还是 Evidence Selection 造成失败。

### P0-2：增加“答案相关性”软排序层

在角色排序之前增加可解释的 Evidence Relevance：

1. 问题实体与文件名/路径匹配；
2. 问题实体与标题、Heading、Sheet 名匹配；
3. 问题关键短语与 Chunk 正文匹配；
4. 年份、单位、数值类型、专业名、项目名共同匹配；
5. 目标文件存在但片段不匹配时，只提升文件候选，不直接生成结论。

该层必须是软加权，不能因为 Metadata 缺失或单个关键词不匹配直接删除候选。

### P0-3：把 Gold Evidence 纳入 Shadow 对账

每题明确三种状态：

- `GOLD_IN_ROOT`：Gold Evidence 在当前 Root；
- `GOLD_OUT_OF_SCOPE`：Gold Evidence 在其他 Root 或尚未批准 Root；
- `GOLD_UNCONFIRMED`：资料存在性和答案片段尚未人工确认。

只有 `GOLD_IN_ROOT` 的问题，才用于评价当前 Root 的排序恢复率；其他问题只能作为范围缺口记录，不能误判为排序失败。

### P1-1：落实 Intent 角色优先级

将角色排序作为明确的软优先级，并保留当前结果作为回退：

- `TEMPLATE_QUERY`：模板 > 制度/指南 > 案例；
- `POLICY_QUERY`：制度 > 指南/工作计划 > 案例；
- `CASE_QUERY`：案例 > 复盘/经验总结 > 模板；
- `METHOD_QUERY`：方法指南/流程/手册 > 模板 > 案例；
- `DISCIPLINE_QUERY`：专业资料/专业图审资料 > 专业案例 > 通用管理指南。

角色归一化必须先完成。例如“管理指南”“工作计划”“制度性通知”不能全部简单视为同一角色；要保留 `document_role` 与 `authority_level` 两个维度。

### P1-2：调整同文档 Chunk 配额

当前“单文档最多 2 Chunk”不适合清单、台账和统计表问题。

建议：

- 普通解释型问题：单文档最多 2 Chunk；
- 清单/台账/数量/金额问题：目标 Workbook 或目标文档最多 4～6 个相关 Chunk；
- 多 Sheet 统计问题：允许同一 Workbook 的多个有效 Sheet 同时进入 Evidence；
- 只有当目标文件已被确认命中后，才执行 Evidence Diversity。

### P1-3：目标文件保护机制

如果文件名、路径或实体页明确命中问题目标：

- 目标文件至少保留 1 个 Evidence 名额；
- 目标文件内最高相关 Chunk 至少保留 1 个；
- 不得被角色多样性规则替换；
- 若目标文件没有答案片段，应保留“目标文件已命中但证据不足”的状态。

### P2-1：增加事实类型约束

对“多少、金额、数量、占比、上传数量”等问题，增加事实类型标记：

- `COUNT_FACT`：条数、数量；
- `AMOUNT_FACT`：金额、万元、元；
- `RATE_FACT`：比例、效益率；
- `DATE_FACT`：年份、月份、会议日期；
- `SCOPE_FACT`：公司级、项目级、专业级。

事实类型不匹配时，候选只能作为相关背景，不能提升为直接 Evidence。

## 7. 下一轮 Shadow 验证方案

不进入正式链路前，使用以下 A/B 对比：

| 指标 | 当前基线 | 优化后目标 |
|---|---|---|
| Gold 文件 Top-5 命中 | 逐题记录 | 不低于基线，重点题明显提升 |
| Gold Chunk Top-5 命中 | 未持久化 | 必须可计算 |
| Intent-Role Top-1 | 逐题记录 | 五类 Intent 均符合角色顺序 |
| Target File 保留率 | 未记录 | 目标文件命中时 100% 保留至少 1 条 |
| 目标 Workbook 多 Sheet 覆盖 | 未记录 | 清单/台账问题按 Sheet 记录 |
| Evidence Location 完整率 | 已有 | 保持 100% |
| Unsupported Claim | 已由 Validator 控制 | 保持 0 |
| Root Scope 误判 | 当前存在风险 | `GOLD_OUT_OF_SCOPE` 不计入排序失败 |

重点先验证 BA-007、BA-010；BA-001、BA-002、BA-003、BA-008 要先标记 Root Scope，避免把源文件缺口混成 Evidence Ranking 失败。

## 8. 最终建议

最小实施顺序是：

1. 先持久化 BM25/Dense/RRF/Reranker Top-K 轨迹；
2. 再增加目标文件、标题/Sheet、事实类型的软相关性；
3. 再落实五类 Intent 的角色排序；
4. 最后调整同文档 Chunk 配额和多样性策略；
5. 用 BA-007、BA-010 做 Shadow A/B 验证，通过后再考虑进入正式 Evidence Selection。

本任务不建议先调 RRF 常数、Embedding 模型或 Reranker 参数。当前最明确的问题在 Evidence Selection 的目标证据保护、角色顺序和轨迹缺失，而不是模型环境本身。

