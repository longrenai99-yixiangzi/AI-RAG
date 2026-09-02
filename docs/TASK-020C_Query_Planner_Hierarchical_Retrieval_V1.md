# TASK-020C

## Query Planner + Hierarchical Retrieval V1
### Document → Section → Evidence Candidate Generation

项目：`D:\AI智能体\AI设计管理RAG-V1`

前置：

- `TASK-020A = COMPLETE`
- `TASK-020B = COMPLETE`
- 020A Controlled Baseline：`020A.3-controlled-20260829T103749`
- Document Intelligence Schema：`document_intelligence.v2`

---

## 一、任务目标

当前已建立：

```text
Document
→ Heading Tree
→ Section
→ Paragraph/Table
→ Atomic Evidence
```

本 TASK 第一次让检索真正使用这些结构。

目标从：

```text
Question → 全库 Chunk 直接竞争
```

升级成：

```text
Question
→ Query Planner
→ Document Retrieval
→ Section Retrieval
→ Evidence Candidate Retrieval
```

同时保留 `Global Rescue`，形成：

```text
Hierarchical First + Global Rescue
```

本 TASK 重点回答：

> 能不能先找到正确 Document，再进入正确 Section，最后找到正确 Evidence？

不是最终 Answer 质量优化。

---

## 二、020A 基线问题

020A.3 已确认，在 Runtime 可评价题中：

```text
Document Recall@5 = 20%
Section Hit Rate = 20%
Gold Evidence Recall@10 = 40%
Gold Evidence Recall@20 = 60%
Selected Gold Evidence Rate = 40%
```

真实失败：

```text
BA-002：DOCUMENT_MISSED
BA-008：DOCUMENT_MISSED
BA-004：SECTION_MISSED
BA-010：SOURCE_LINEAGE_FAILURE
```

本 TASK 必须围绕这些真实失败验证，但禁止针对 BA 问题写 hardcode。

---

## 三、任务性质

本 TASK 允许：

- 新增 Shadow Retrieval 模块
- 新增 Document Index
- 新增 Section Index
- 新增 Query Planner
- 新增 Hierarchical Trace
- 新增 A/B Evaluation

本 TASK 禁止替换正式 Retriever。

所有实现必须：`Shadow Only`。

---

## 四、严格禁止

1. 不修改正式 `app/retriever.py` 行为；
2. 不修改正式 8000；
3. 不修改正式 Qdrant；
4. 不修改正式 Collection；
5. 不修改现有 Answer Engine；
6. 不修改 Fact Path；
7. 不修改 Claim/Citation Validator；
8. 不修改 Scope Guard 正式逻辑；
9. 不修改 Preflight；
10. 不调用 Live Provider；
11. 不创建 Provider Budget；
12. 不扫描 Root-003；
13. 不刷新整个 Root-002；
14. 不把 Root-002 改为 APPROVED；
15. 不重新训练 Embedding；
16. 不更换 BGE-M3；
17. 不更换 bge-reranker-v2-m3；
18. 不为了 Gold 命中加入 BA 专用关键词；
19. 不把 Gold 文件名注入运行 Query；
20. 不直接跳到 020D 复杂 Fusion；
21. 不重构 Answer Router。

---

## 五、使用 020B 结构

输入：

```text
data\shadow\document_intelligence_v2\
```

至少使用：

- documents
- headings
- sections
- paragraphs
- tables
- table_rows
- atomic_evidence
- lineage

不得另造与 020B 平行的 Document Schema。

---

## 六、Query Planner V1

建立 `QueryPlan`，至少包含：

```text
query_id
original_question
normalized_question
query_type
entities
organization
project
year
specialty
metric
document_type_hint
document_role_hint
authority_requirement
scope_constraints
subquestions
structured_query_hint
comparison_plan
aggregation_plan
planner_confidence
```

---

## 七、Query Type

至少支持：

```text
SINGLE_FACT
MULTI_FACT
POLICY_QUERY
METHOD_QUERY
OPTION_QUERY
CASE_QUERY
AGGREGATION_QUERY
COMPARISON_QUERY
MULTI_HOP_QUERY
STRUCTURED_QUERY
SOURCE_LOOKUP
```

本 TASK 不使用 LLM Planner，优先：

```text
规则 + 实体解析 + 现有 Intent 能力
```

以后再考虑 LLM Planner。

---

## 八、Planner 不得成为硬过滤器

Planner 输出只能作为 Hint / Soft Constraint，例如：

```text
year=2026
organization=公司
```

主要用于加权与诊断。

不能因 Planner 漏识别而直接删除正确 Document。

原则：

```text
Planner guides retrieval, not hard deletes retrieval.
```

---

## 九、Subquestion Decomposition

对明显多问题 Query 建立 Sub Questions。

BA-010：

```text
SQ1：有哪些专业？
SQ2：每个专业多少条？
SQ3：增加效益多少条？
```

BA-009：识别为“土木公司 + 全部督办事项”，而不是只返回第一条。

本 TASK 只建立 subquestion representation，最终 Answer Coverage 留给后续任务。

---

## 十、Document Search Representation

每个 Document 建立 `document_search_text`，至少由以下内容组成：

- title
- file_name
- profile_text
- document_type
- document_role
- organization
- project
- specialty
- year
- metrics
- heading 摘要

正文全文不得无脑全部拼入 Document Search Text。

Document Retrieval 的目标是找到“哪份文件最可能回答”，不是再次制造超长 Chunk。

---

## 十一、Document Index

建立 Shadow：

```text
Document BM25 Index
Document Dense Index
```

Dense 继续使用 BGE-M3，不更换 Embedding。

存储建议：

```text
data\shadow\hierarchical_retrieval_v1\document_index\
```

不得写正式 Qdrant。

---

## 十二、Document Retrieval

至少产生：

```text
document_bm25_candidates
document_dense_candidates
```

每个候选保存：

```text
document_id
source_path
bm25_rank
bm25_score
dense_rank
dense_score
metadata_match
planner_match
document_role
authority
scope
```

本 TASK 允许简单 RRF 用于 Document candidate generation，但复杂多源 Fusion 留给 020D。

---

## 十三、Document 候选范围

Document TopK 至少记录：Top1 / Top3 / Top5 / Top10 / Top20。

推荐进入 Section 的 Document 数量：Top10。

不要一开始硬锁 Top3。

---

## 十四、Metadata Soft Boost

允许对以下字段 soft boost：

- organization
- project
- year
- specialty
- document_type
- document_role
- metric

所有 boost 必须有 Trace。

禁止：

```text
metadata mismatch → hard delete
```

除非已有明确治理 Scope 禁止。

---

## 十五、Authority 处理

Authority 只在同 Scope 候选中参与软排序。

禁止高 Authority 错误 Scope 覆盖正确项目/组织/年份 Document。

---

## 十六、Registration Page

`REGISTER_PAGE` 允许进入 Document Discovery 候选，但需要 `role_penalty`，避免压过正文。

同时保留 `REGISTER_POINTS_TO` Lineage Hint。

本 TASK 不得完全过滤 Registration Page，因为未来仍用于 Discovery / Navigation。

---

## 十七、Section Search Representation

每个 Section 建立 `section_search_text`，至少包含：

- document title
- heading
- heading_path
- section_text 摘要
- table titles
- parent heading

必须保留 `document_id`。

---

## 十八、Section Retrieval

主路径只在 Top Document Candidates 范围内检索 Section。

建立：

```text
Section BM25
Section Dense
```

输出：

```text
section_id
document_id
heading
heading_path
bm25_rank
dense_rank
local_rank
global_rank
location
```

---

## 十九、Section Parent Context

Section 检索不能只用 `section_text`。

至少同时考虑：

- Document Title
- Parent Heading
- Current Heading

避免正文脱离业务章节。

---

## 二十、Global Section Rescue

必须保留 `Global Section Rescue`。

原因：Document Retrieval 仍可能漏掉正确 Document。

路径：

```text
Hierarchical Sections
+
Global Section Candidates
```

最终进入 Evidence Candidate Generation。

候选需记录：

```text
candidate_origin = HIERARCHICAL | GLOBAL_RESCUE
```

---

## 二十一、Evidence Candidate Retrieval

在 Top Documents + Top Sections 范围内检索 Atomic Evidence。

允许使用：

- 现有 BM25
- 现有 Dense
- Atomic Exact

但本 TASK 不重设复杂 Fusion。

输出：

```text
evidence_id
document_id
section_id
candidate_origin
rank
location
evidence_type
```

---

## 二十二、Structured Table Route

如果 Planner 判断：

```text
STRUCTURED_QUERY
或
AGGREGATION_QUERY
```

先产生 Table Candidate，而不是让所有 Table Row 与文本 Chunk 全库竞争。

路径：

```text
Question
→ Document
→ Section/Table
→ Structured Table Candidate
```

本 TASK 只负责找到 Table，具体聚合复用现有 Fact 逻辑或留后续处理。

---

## 二十三、Table Semantic Retrieval

使用 020B 的 Table Semantic Representation。

至少利用：

- table_title
- header
- semantic_summary
- business_fields
- sheet_name
- document context

输出：

```text
table_id
document_id
section_id
sheet
table_score
```

---

## 二十四、Source Scope 先判断

在 Retriever 评价前，先判断：

```text
Gold Runtime Source Available?
```

若 Governance 不允许，或 Source 不在当前 Runtime Artifact，记录：

```text
SOURCE_SCOPE_MISSING
```

不要为了提高 Recall 偷偷加载它。

---

## 二十五、Root-002 规则

Root-002 保持：`PENDING_APPROVAL`。

只能使用当前已有 Frozen Shadow Artifact 以及 020A/020B 既有兼容结构。

不得 refresh、scan new directories、自动发现。

Hierarchical Retrieval 可以在现有 Frozen Shadow 数据上测试，但不等于正式审批。

---

## 二十六、Lineage Safety

Retrieval Candidate 必须携带 `lineage_status`。

若候选属于：

```text
LINEAGE_PARTIAL
LINEAGE_NOT_CONFIRMED
```

本 TASK 不得自动 Join。

BA-010 必须继续 `NO_AUTO_JOIN`。

---

## 二十七、Retrieval Trace

每个 Query 完整保存：

- query_plan
- document_candidates
- section_candidates
- table_candidates
- atomic_candidates
- global_rescue_candidates
- Gold Document Rank
- Gold Section Rank
- Gold Evidence Rank

并明确 Gold 是由 Document Hierarchical 还是 Global Rescue 命中。

---

## 二十八、A/B Baseline

A：`020A.3 现有 Chunk-first Baseline`

B：`020C Hierarchical Candidate Generation`

比较的是 Candidate Recall，不是最终 Answer。

---

## 二十九、核心指标

至少输出：

```text
Document Recall@1
Document Recall@3
Document Recall@5
Document Recall@10

Section Recall@1
Section Recall@3
Section Recall@5
Section Recall@10

Gold Evidence Recall@5
Gold Evidence Recall@10
Gold Evidence Recall@20

Table Hit Rate
Global Rescue Usage Rate
Global Rescue Recovery Rate
Registration Page Dominance Rate
Lineage Unsafe Join Count
```

---

## 三十、分母规则

Retriever Recall 只在 `Runtime Source Available = True` 的题中计算。

`SOURCE_SCOPE_GOLD` 不处罚 Retriever。

Partial Gold 只评价已确认部分。

BA-010 SQ3 不进入“Gold evidence 必须命中”分母。

---

## 三十一、BA-002 专项

020A：`DOCUMENT_MISSED`

Gold Document：`《项目设计管理手册》.pdf`

Gold Section：`17.3 / 17.3.2`

检查：Document Rank、Section Rank、Evidence Rank。

成功标准不是最终回答公式，而是正确 Document 和 Section 能稳定进入候选。

---

## 三十二、BA-008 专项

020A：`DOCUMENT_MISSED`

Gold：`2025年饶淇述职.md`

Document Profile：

```text
organization=公司
year=2025
```

检查查询：`2025年公司设计创效金额是多少元？`

要求公司年度述职 Document 能进入前列，项目级创效案例不得长期压过公司级 Document。

---

## 三十三、BA-004 专项

020A：`SECTION_MISSED`

必须验证：

```text
设计方案比选提示清单7.23.xlsx
→ Sheet1
→ 对应Table/Region
→ Row89
```

Section/Table 层级是否稳定命中。

---

## 三十四、BA-009 专项

Gold 是同一表格中的两条土木公司记录。

本 TASK 检查正确 Workbook、Sheet、Table 能否进入候选。

不要求本 TASK 生成两条最终回答，回答完整性留给 Answer 阶段。

---

## 三十五、BA-010 专项

Gold：`DOCX Table11`，已确认 34 条。

目标：正确 DOCX、Section、Table11 进入候选。

历史 XLSX 即使命中，也必须标 `LINEAGE_PARTIAL`，不得 Join。

---

## 三十六、Planner 质量评价

对 Gold 题对照：

- Query Type Accuracy
- Entity Extraction Accuracy
- Year Accuracy
- Organization Accuracy
- Project Accuracy
- Specialty Accuracy
- Subquestion Coverage

Planner 错不应自动造成 Retriever 失败。

报告要区分 `PLANNER_FAILURE` 与 `RETRIEVAL_FAILURE`。

---

## 三十七、Failure 分类

本 TASK 使用：

```text
PLANNER_FAILURE
DOCUMENT_MISSED
SECTION_MISSED
TABLE_MISSED
EVIDENCE_MISSED
GLOBAL_RESCUE_RECOVERED
SOURCE_SCOPE_MISSING
LINEAGE_SAFETY_BLOCK
NO_FAILURE
```

不要进入 Answer Failure。

---

## 三十八、020C 成功门槛

相对 020A.3：

Document Recall@5 必须显著提升。

最低：`>= 60%`

目标：`>= 80%`

Section Recall@5 最低：`>= 60%`

Gold Evidence Recall@10 不得低于 020A.3 的 40%，目标：`>= 70%`

若 Document Recall 仍低，不要开始 020D，先报告 Root Cause。

---

## 三十九、Global Rescue 门槛

Global Rescue 必须能救回部分 Document-stage 漏召回，但不能成为主路径。

若：

```text
>50%的Gold命中依赖Global Rescue
```

必须标记：

```text
HIERARCHICAL_DOCUMENT_STAGE_WEAK
```

不能宣称 020C 成功。

---

## 四十、Registration Page 门槛

统计 REGISTER_PAGE 进入 Document Top5 的比例。

若 Registration Page 频繁压过正文，标记：

```text
REGISTRATION_PAGE_DOMINANCE
```

本 TASK 只报告，不继续调 020D 复杂权重。

---

## 四十一、性能

记录：

- Document Retrieval latency
- Section Retrieval latency
- Evidence Candidate latency
- Total Retrieval latency

当前数据量不大，不能出现每题数十秒。

---

## 四十二、Shadow Storage

写入：

```text
data\shadow\hierarchical_retrieval_v1\
```

建议：

```text
document_search_index
section_search_index
table_search_index
query_plans.jsonl
retrieval_traces.jsonl
candidate_results.jsonl
```

不得覆盖 `document_intelligence_v2`。

---

## 四十三、输出

```text
docs\QUERY_PLANNER_V1_REPORT.md

docs\HIERARCHICAL_RETRIEVAL_V1_REPORT.md

docs\HIERARCHICAL_RETRIEVAL_AB_REPORT.md


evaluation\hierarchical_retrieval_v1\

query_planner_metrics.json

document_retrieval_metrics.json

section_retrieval_metrics.json

evidence_candidate_metrics.json

table_retrieval_metrics.json

global_rescue_metrics.json

registration_page_analysis.json

lineage_safety_validation.json

ba_retrieval_matrix.json

retrieval_traces.jsonl
```

---

## 四十四、测试

新增测试至少覆盖：

- single fact planner
- policy query planner
- aggregation planner
- comparison planner
- multi fact decomposition
- document BM25
- document dense
- document profile boost
- section BM25
- section dense
- parent heading context
- global rescue
- table semantic retrieval
- registration page penalty
- scope unavailable behavior
- lineage partial no auto join

禁止通过 BA 问题字符串 hardcode 测试。

---

## 四十五、安全验收

必须确认：

```text
formal Retriever modified = false
formal 8000 modified = false
formal Qdrant write = 0
provider HTTP requests = 0
Root-002 refresh = 0
Root-003 scan = 0
Gold runtime injection = 0
BA-specific runtime hardcoding = 0
```

---

## 四十六、TASK 完成标准

TASK-020C 不要求问答正确，而是要求证明：

1. 系统能够先找到正确 Document；
2. 能够在 Document 内找到正确 Section/Table；
3. 能够从 Section 进入正确 Evidence Candidate；
4. Document 级失败和 Section 级失败可以单独诊断；
5. Global Rescue 可以补漏但不是主路径；
6. Lineage 不安全来源不会自动拼接。

---

## 四十七、完成后停止

完成后停止。

不要：

- 进入 020D
- 修改 Answer Engine
- 修改正式 Retriever
- 切 8010 正式路径

输出：

```text
TASK-020C = COMPLETE
```

等待架构评审。
