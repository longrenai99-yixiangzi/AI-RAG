# Direct Fact Scope Guard Hardening Report

> TASK-017C-1.1：通用化 Direct Fact Scope Guard，并验证 Scope Probe 与原 BM25/Dense/RRF 候选融合。
> 本次只在 Shadow 运行；未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF、Reranker 或 BA-010 Fact Path。

## 1. 修复前后 Architecture

### 修复前

`DIRECT_FACT → Scope Probe → exact[:1] → Claim Path`。Scope Probe 会绕过原 RRF 候选；项目名称使用固定枚举；文档正文中的“公司”可能覆盖项目文件；Scope Guard 只覆盖 Router 标记为 DIRECT_FACT 的问题。

### 修复后

`Original BM25/Dense/RRF Candidates + Scope Probe Candidates → Candidate Fusion/Dedup → Scope Compatibility → Finality/Conflict Check → Optimized Evidence Selection → Claim Scope Guard → Claim Answer`。

- Project Entity 从 Catalog 的文件名、路径、Document Scope 和“XX项目/工程/中心”语言结构提取，不使用固定项目名枚举。
- 文件路径/文件名优先，其次 Document Role/Metadata，正文组织词只作为弱信号；项目复盘文件不会因正文出现“公司总部”而变成 COMPANY。
- Candidate Origin 支持并合并 `BM25`、`DENSE`、`RRF`、`SCOPE_PROBE`，同一候选不重复进入池。
- 多个 Exact Scope 候选全部进入一致性和冲突检查，不再使用 `exact[:1]`。
- FULL_YEAR 优先于 HALF_YEAR；FORECAST 不覆盖 FINAL；同一 Scope、同一 Period、同一 Finality 的不同数值返回 `DIRECT_FACT_CONFLICT`。
- Scope Guard 对明显的 Claim Path 单值组织事实也启用，但不改变 Router route。

## 2. 回归总览

- BA-001～BA-010：10 题。
- Scope Guard Enabled：2 题。
- Final Status 分布：`{"GENERATED": 3, "NO_EVIDENCE": 4, "STRUCTURE_INVALID": 2, "FACT_RESULT": 1}`
- Root-001 Chunk：4747；Root-002 Chunk：1847。
- BA-010 保持 FACT_RESULT，未重新计算 80/37/43。
- 所有业务负责人评价仍为 `PENDING_REVIEW`。

## 3. Candidate Fusion Trace

### BA-008

| Rank | Root | 文件 | Scope Compatibility | Candidate Origin | Fusion Score | Reporting Period | Finality |
|---:|---|---|---|---|---:|---|---|
| 1 | Root-001 | 2025年饶淇述职.md | EXACT_SCOPE_MATCH | SCOPE_PROBE | 2.89 | FULL_YEAR | FINAL |
| 2 | Root-001 | 2025年年度总结.md | EXACT_SCOPE_MATCH | SCOPE_PROBE | 2.54 | FULL_YEAR | FORECAST |
| 3 | Root-001 | 2025年任慧军述职.md | EXACT_SCOPE_MATCH | SCOPE_PROBE | 2.24 | FULL_YEAR | FORECAST |
| 4 | Root-001 | 2024年度总结2.md | COMPATIBLE_SCOPE | SCOPE_PROBE | 1.54 | FULL_YEAR | FORECAST |
| 5 | Root-001 | 2025年半年总结.md | COMPATIBLE_SCOPE | SCOPE_PROBE | 1.42 | HALF_YEAR | FORECAST |
| 6 | Root-002 | 关于优化公司总部部门及设置“四大中心”的通知.pdf | COMPATIBLE_SCOPE | SCOPE_PROBE | 1.42 | FULL_YEAR | FORECAST |
| 7 | Root-001 | 2025年设计管理总结.md | COMPATIBLE_SCOPE | SCOPE_PROBE | 1.38 | FULL_YEAR | FORECAST |
| 8 | Root-002 | 设计策划评审意见表(1).xlsx | COMPATIBLE_SCOPE | SCOPE_PROBE | 0.76 | FULL_YEAR | FORECAST |
| 9 | Root-001 | 2025年设计管理总结.md | COMPATIBLE_SCOPE | RRF,BM25 | 0.614706 | FULL_YEAR | FORECAST |
| 10 | Root-001 | 公司公路市政产品线设计创效案例汇编模板（案例示例） - 成果.pptx | PARTIAL_SCOPE_MATCH | SCOPE_PROBE | 0.58 | FULL_YEAR | FINAL |
| 11 | Root-001 | 公司学校产品线设计创效案例汇编模板（案例示例） - 成果.pptx | PARTIAL_SCOPE_MATCH | SCOPE_PROBE | 0.58 | UNKNOWN | FORECAST |
| 12 | Root-002 | 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf | PARTIAL_SCOPE_MATCH | SCOPE_PROBE | 0.58 | FULL_YEAR | FORECAST |

说明：BA-008 的 `2025年饶淇述职.md` 同时保留 Scope Probe 来源；原始 RRF 候选、项目级冲突候选仍在 Trace 中，但不作为公司级主 Claim。

## 4. Document Scope 误分类修复

| 检查对象 | document_scope | subject_scope | document_role | 结论 |
|---|---|---|---|---|
| 02大冶人民医院（华中）.pptx | PROJECT | PROJECT | 项目案例 | 项目文件保持 PROJECT，不因正文组织词升级为 COMPANY |
| 设计管理复盘（哈密15万风电）.md | PROJECT | PROJECT | 项目案例 | 项目文件保持 PROJECT，不因正文组织词升级为 COMPANY |
| 设计管理总结（哈密15万风电）(1).docx | PROJECT | PROJECT | 项目案例 | 项目文件保持 PROJECT，不因正文组织词升级为 COMPANY |

## 5. Project Entity 通用测试

从当前 Catalog 动态提取的项目实体样本（未在脚本中写死）：河北科技师范学院滨海技术应用实训基地建设, 关于召开应城市东马坊园区智汇港等, 04公安玉湖及淤泥湖水生态修复, 广西体育高等专科学校相思湖校区, 01河津科创园道路管网epc。

| Case | Query Entity | Scope | Router | Project Guard 未阻断 |
|---|---|---|---|---|
| N-PROJECT-01 | 河北科技师范学院滨海技术应用实训基地建设, 河北科技师范学院 | PROJECT | DIRECT_FACT / CLAIM_ANSWER_PATH | True |
| N-PROJECT-02 | 关于召开应城市东马坊园区智汇港等 | PROJECT | DIRECT_FACT / CLAIM_ANSWER_PATH | True |
| N-PROJECT-03 | 04公安玉湖及淤泥湖水生态修复, 公安玉湖及淤泥湖水生态修复 | PROJECT | DIRECT_FACT / CLAIM_ANSWER_PATH | True |
| N-PROJECT-04 | 广西体育高等专科学校相思湖校区 | PROJECT | DIRECT_FACT / CLAIM_ANSWER_PATH | True |
| N-PROJECT-05 | 01河津科创园道路管网epc, 河津科创园道路管网epc, epc | PROJECT | DIRECT_FACT / CLAIM_ANSWER_PATH | True |

## 6. FULL_YEAR / HALF_YEAR 测试

| Query | Query Period | Top Candidate Period | Finality | Compatibility |
|---|---|---|---|---|
| 2025年公司设计创效金额是多少？ | FULL_YEAR | FULL_YEAR | FINAL | EXACT_SCOPE_MATCH |
| 2025年半年公司设计创效金额是多少？ | HALF_YEAR | FULL_YEAR | FINAL | PARTIAL_SCOPE_MATCH |

## 7. Conflict Test

BA-008 Scope Resolution：`{"status": "RESOLVED_BY_SCOPE_AND_FINALITY", "preferred_finality": "FINAL", "profiles": [{"file_name": "2025年饶淇述职.md", "knowledge_root_id": "Root-001", "reporting_period": "FULL_YEAR", "finality": "FINAL", "values": [{"raw": "创效金额约4.45亿", "value_yuan": 445000000.0, "unit": "亿", "is_approximate": true, "metric_scope": "DESIGN_VALUE_CREATION_AMOUNT"}], "candidate_origin": ["SCOPE_PROBE"]}, {"file_name": "2025年年度总结.md", "knowledge_root_id": "Root-001", "reporting_period": "FULL_YEAR", "finality": "FORECAST", "values": [], "candidate_origin": ["SCOPE_PROBE"]}, {"file_name": "2025年任慧军述职.md", "knowledge_root_id": "Root-001", "reporting_period": "FULL_YEAR", "finality": "FORECAST", "values": [{"raw": "创效金额6.9亿", "value_yuan": 690000000.0, "unit": "亿", "is_approximate": false, "metric_scope": "DESIGN_VALUE_CREATION_AMOUNT"}], "candidate_origin": ["SCOPE_PROBE"]}], "all_values_yuan": [445000000.0, 690000000.0], "raw_value_conflict": true, "conflicting_values_yuan": [445000000.0], "conflict": false, "conflict_resolved_by_finality": true}`

冲突规则：同一 organization/entity/year/metric/reporting_period/finality 下出现不同直接数值时，必须返回 `DIRECT_FACT_CONFLICT`，不得依靠 Probe 分数选择一个。FINAL 与 FORECAST 不视为同一 Finality；FULL_YEAR 与 HALF_YEAR 不视为同一 Reporting Period。

## 8. BA-008 最终业务答案验收

### 最终回答正文

```text
## evidence_summary
- 2025年公司设计创效金额约为4.45亿元 [S1]
## evidence_boundary
- 2025年公司设计创效金额约为4.45亿元 [S1]

（源文档原值：创效金额约4.45亿；按 1 亿元 = 100,000,000 元确定性换算：约 445,000,000 元。）
```

### Atomic Claim

```json
[
  {
    "claim_id": "C1",
    "claim_text": "2025年公司设计创效金额约为4.45亿元",
    "evidence_ids": [
      "S1"
    ]
  }
]
```

### 原始来源与 Citation

- `S1`：2025年饶淇述职.md，Root=`Root-001`，location=`{'line_start': 5, 'line_end': 7}`；excerpt：，合计3. 05亿元，钢筋平均创效率9. 66%，11个项目钢筋内外结算量效益超16% 。 设计管理创效 健全设计支持体系 ，优化了两级设计支持中心架构，公司设计中心配置岩土、园林等8名设计工程师，分公司各中心配置建筑、土木等22名设计工程师，形成了重点EPC项目公司赋能，一般EPC项目分公司牵头的设计支持体系。 开展设计创效， 全年服务项目78个，提出创效项1340条，入图1151条，创效金额约4. 45亿元； 支 持 老谷南项目， 梳理设计策划58项， 设计人员协同项目驻点 落实 入图策划27 项 ，完成创效1. 32亿元 。 设计竞优逐强 ，公司 参加局设计竞赛6项作品，最终 2项 管理案例进入 决赛 轮 。

### BA-008 Scope Validation

`{"valid": true, "errors": []}`

验收要点：最终主 Claim 来自公司年度证据；保留“约4.45亿元”；若用户要求元，Shadow 输出按 1 亿元 = 100,000,000 元确定性换算，并保留“约”。Section Map 修复只重排已验证 Claim，不增加事实。

## 9. BA-001～BA-010 回归

| BA | direct_scope_guard | baseline status | new status | route | Scope Result |
|---|---|---|---|---|---|
| BA-001 | DISABLED | GENERATED | GENERATED | CLAIM_ANSWER_PATH | True |
| BA-002 | DISABLED | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | True |
| BA-003 | DISABLED | STRUCTURE_INVALID | STRUCTURE_INVALID | CLAIM_ANSWER_PATH | True |
| BA-004 | DISABLED | STRUCTURE_INVALID | STRUCTURE_INVALID | CLAIM_ANSWER_PATH | True |
| BA-005 | DISABLED | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | True |
| BA-006 | ENABLED | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | True |
| BA-007 | DISABLED | GENERATED | GENERATED | CLAIM_ANSWER_PATH | True |
| BA-008 | ENABLED | GENERATED | GENERATED | CLAIM_ANSWER_PATH | True |
| BA-009 | DISABLED | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | True |
| BA-010 | DISABLED | FACT_RESULT | FACT_RESULT | FACT_ANSWER_PATH | True |

### 目标外题目回归

BA-002、BA-003、BA-004、BA-006、BA-009 未被本任务改写为新的答案路径；其既有状态保持，后续仍需按 TASK-017B 优先级单独处理。

## 10. 边界确认

- 未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务或正式 Qdrant；
- 未重新生成全库 Embedding，未启用 Reranker，未调整 RRF；
- 未修改 BA-010 Fact Path；
- 未针对 BA 编号、具体项目名或具体正确文件名写路由特判；
- 每题 JSON 和动态负向测试保存在 `D:\AI智能体\AI设计管理RAG-V1\evaluation\direct_fact_scope_guard_hardening`。
