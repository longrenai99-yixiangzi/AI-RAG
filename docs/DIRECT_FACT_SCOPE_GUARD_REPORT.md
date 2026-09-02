# Direct Fact Scope Guard Report

> TASK-017C-1：在 Shadow 中增加通用 Query Scope、Scope Probe、Scope Compatibility 和 Claim Scope Guard。
> 未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF、Reranker 或 BA-010 Fact Path。

## 1. Scope 设计

- Query Scope：organization_scope、time_scope、entity_scope、metric_scope、aggregation_scope。
- Candidate Scope：document_scope、subject_scope、time_scope、metric_scope。
- Scope Probe 只增加候选，不替换 BM25、Dense、RRF。候选来源标记为 `SCOPE_PROBE`。
- `SCOPE_CONFLICT` 候选只能作为上下文，不能成为 DIRECT Claim 主证据。
- Scope Guard 对 Claim 的 Evidence 范围和 Claim 文本做确定性校验；不匹配时返回安全的 `NO_EVIDENCE`，不放宽现有 Validator。

## 2. 回归总览

- BA-001～BA-010：10 题。
- DIRECT_FACT 题：2 题。
- 最终状态分布：`{"GENERATED": 3, "NO_EVIDENCE": 4, "STRUCTURE_INVALID": 2, "FACT_RESULT": 1}`
- Scope Guard 通过：1/2（含无 Claim 的安全结果）。
- 所有业务负责人评价仍为 `PENDING_REVIEW`，技术状态不等于业务验收通过。

## 3. BA-008 修复前后对比

### 修复前

- 技术状态：`GENERATED`
- 原回答使用了华师南湖训练馆项目金额 2594.70 万元，属于项目级事实，不符合公司年度问题范围。
- 正确的 `2025年饶淇述职.md` 未进入原有效 RRF/Evidence。

### Scope Guard 后

- Query Scope：`{"organization_scope": "COMPANY", "time_scope": "YEAR", "time_value": "2025", "entity_scope": "ORGANIZATION_TOTAL", "metric_scope": "DESIGN_VALUE_CREATION_AMOUNT", "aggregation_scope": "DIRECT_REPORTED_FACT", "project_terms": []}`
- Final Status：`GENERATED`
- Scope Probe 是否发现公司年度候选：`True`
- Scope Claim Validation：`{"valid": true, "errors": []}`
- 公司级年度候选以 `candidate_origin=SCOPE_PROBE` 进入 Shadow Evidence；项目级金额不再作为主证据。

## 4. BA-008 Scope Probe 候选

| Rank | Root | 文件 | document_scope | subject_scope | year | metric | compatibility | score |
|---:|---|---|---|---|---|---|---|---:|
| 1 | Root-001 | 2025年饶淇述职.md | COMPANY | ORGANIZATION_TOTAL | 2025 | DESIGN_VALUE_CREATION_AMOUNT | EXACT_SCOPE_MATCH | 1.69 |
| 2 | Root-001 | 2025年年度总结.md | COMPANY | ORGANIZATION_TOTAL | 2025 | DESIGN_VALUE_CREATION_AMOUNT | EXACT_SCOPE_MATCH | 1.34 |
| 3 | Root-001 | 2025年任慧军述职.md | COMPANY | ORGANIZATION_TOTAL | 2025 | DESIGN_VALUE_CREATION_AMOUNT | EXACT_SCOPE_MATCH | 1.04 |
| 4 | Root-001 | 2025年半年总结.md | COMPANY | ORGANIZATION_TOTAL | 2025 | DESIGN_VALUE_CREATION_AMOUNT | EXACT_SCOPE_MATCH | 1.02 |
| 5 | Root-001 | 2024年度总结2.md | COMPANY | ORGANIZATION_TOTAL | 2024 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.74 |
| 6 | Root-001 | 02大冶人民医院（华中）.pptx | COMPANY | ORGANIZATION_TOTAL | 2018 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.68 |
| 7 | Root-002 | 2026年二季度半年运营会资料汇编（隐藏版）.pdf | COMPANY | ORGANIZATION_TOTAL | 2026 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.68 |
| 8 | Root-001 | 大冶人民医院（华中）.md | COMPANY | ORGANIZATION_TOTAL | 2023 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.68 |
| 9 | Root-002 | 设计管理总结（哈密15万风电）(1).docx | COMPANY | ORGANIZATION_TOTAL | 2024 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.68 |
| 10 | Root-001 | 2025年设计管理总结.md | UNKNOWN | UNKNOWN | 2025 | DESIGN_VALUE_CREATION_AMOUNT | COMPATIBLE_SCOPE | 0.63 |

## 5. BA-001～BA-010 回归结果

| BA | fact_mode | route | baseline status | new status | scope result | 主证据来源 |
|---|---|---|---|---|---|---|
| BA-001 | NONE | CLAIM_ANSWER_PATH | GENERATED | GENERATED | `True` | Root-001:设计任务书.md, Root-001:设计任务书.md, Root-002:《项目设计管理手册》.pdf |
| BA-002 | NONE | CLAIM_ANSWER_PATH | NO_EVIDENCE | NO_EVIDENCE | `True` | Root-002:EPC设计管理经验总结（光谷实验中学）.docx, Root-002:EPC设计管理经验总结（光谷实验中学）.docx, Root-002:2026年二季度半年运营会资料汇编（隐藏版）.pdf |
| BA-003 | NONE | CLAIM_ANSWER_PATH | STRUCTURE_INVALID | STRUCTURE_INVALID | `True` | Root-002:《项目设计管理手册》.pdf, Root-002:《项目设计管理手册》.pdf, Root-001:产品线设计方案比选典型案例汇编（厂房）.md |
| BA-004 | NONE | CLAIM_ANSWER_PATH | STRUCTURE_INVALID | STRUCTURE_INVALID | `True` | Root-001:设计方案比选提示清单7.23.xlsx, Root-001:设计方案比选提示清单7.23.xlsx, Root-002:《项目设计管理手册》.pdf |
| BA-005 | NONE | CLAIM_ANSWER_PATH | NO_EVIDENCE | NO_EVIDENCE | `True` | Root-002:EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx, Root-002:EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx, Root-002:EPC设计管理经验总结(涟水第三水厂建设项目3.17).docx |
| BA-006 | DIRECT_FACT | CLAIM_ANSWER_PATH | NO_EVIDENCE | NO_EVIDENCE | `False` | 无 |
| BA-007 | NONE | CLAIM_ANSWER_PATH | GENERATED | GENERATED | `True` | Root-002:关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf, Root-002:关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf, Root-002:2026年二季度半年运营会资料汇编（隐藏版）.pdf |
| BA-008 | DIRECT_FACT | CLAIM_ANSWER_PATH | GENERATED | GENERATED | `True` | Root-001:2025年饶淇述职.md |
| BA-009 | NONE | CLAIM_ANSWER_PATH | NO_EVIDENCE | NO_EVIDENCE | `True` | Root-002:关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf, Root-001:AI_存量知识库分类框架_系统生成.md, Root-001:AI_存量知识库分类框架_系统生成.md |
| BA-010 | DERIVED_FACT | FACT_ANSWER_PATH | FACT_RESULT | FACT_RESULT | `True` | Root-002:方案比选与价值创造清单方案比选及价值创造.xlsx, Root-002:方案比选与价值创造清单方案比选及价值创造.xlsx, Root-002:中船哈密15万项目设计管理(1).pptx |

## 6. 负向测试

| Case | 问题范围 | Router fact_mode/route | 精确 Scope 候选数 | 项目问题未被公司保护误伤 |
|---|---|---|---:|---|
| N-001 | COMPANY + ORGANIZATION_TOTAL + DESIGN_VALUE_CREATION_AMOUNT | DIRECT_FACT / CLAIM_ANSWER_PATH | 4 | True |
| N-002 | UNKNOWN + PROJECT + DESIGN_VALUE_CREATION_AMOUNT | DIRECT_FACT / CLAIM_ANSWER_PATH | 1 | True |
| N-003 | COMPANY + ORGANIZATION_TOTAL + COUNT | NONE / CLAIM_ANSWER_PATH | 0 | True |
| N-004 | UNKNOWN + PROJECT + COUNT | DERIVED_FACT / FACT_ANSWER_PATH | 0 | True |
| N-005 | COMPANY + ORGANIZATION_TOTAL + TARGET | DIRECT_FACT / CLAIM_ANSWER_PATH | 0 | True |
| N-006 | UNKNOWN + PROJECT + RATE | DIRECT_FACT / CLAIM_ANSWER_PATH | 0 | True |

## 7. 结论

1. BA-008 的根因是公司/年度/总体范围没有在原有候选排序中生效；Scope Probe 能从既有 Shadow payload 找到公司年度候选，并阻止项目金额成为主 Claim。
2. 直接事实的数量、金额、比例等词不再单独决定范围；必须同时匹配组织、实体、时间和指标。
3. 公司级保护没有改变项目级 Scope 的识别规则；项目查询仍保留 PROJECT 候选。
4. BA-010 继续使用 `DERIVED_FACT → FACT_ANSWER_PATH`，复用已确认 80/37/43 结果，未重新计算。
5. 本报告只证明 Shadow Scope Guard 的技术行为，BA-008 的最终业务正确性仍需业务负责人确认。

## 8. 边界确认

- 未修改正式系统和正式索引；
- 未重新生成全库 Embedding；
- 未扫描新的 Root-002 目录；
- 未修改 Router V1.1 和 BA-010 Fact Answer Path；
- 所有输出 JSON 保存在 `evaluation/direct_fact_scope_guard/`。
