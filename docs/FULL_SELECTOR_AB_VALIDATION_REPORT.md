# Full Selector Shadow A/B Validation Report

> TASK-016D-2C：将 TASK-016D-2B Shadow Selector 扩展到 BA-001～BA-010。
> 仅验证 Evidence 层，不调用 LLM 做最终答案质量判断，不修改正式 Evidence Selection。

## 1. 执行边界

- Baseline：`evaluation/traces/`，原始轨迹未覆盖。
- Optimized：`evaluation/traces_optimized/`，包含 10 题优化轨迹。
- Embedding、RRF 参数和 Reranker 均保持不变；Reranker 未执行。
- 未写入正式 Qdrant，未修改正式 Retriever、8000 服务或 Answer Engine。

## 2. Gold Scope 分布

- GOLD_IN_ROOT：2（BA-007, BA-010）
- GOLD_OUT_OF_SCOPE：5（BA-001, BA-002, BA-003, BA-004, BA-008）
- GOLD_UNCONFIRMED：3（BA-005, BA-006, BA-009）

只有 GOLD_IN_ROOT 题目计入 Target File Recall、Target Evidence Retention 和 Selector Recovery Rate。
GOLD_OUT_OF_SCOPE / GOLD_UNCONFIRMED 只记录知识范围或证据确认缺口，不计为 Evidence Selection 失败。

## 3. 逐题 A/B 结果

| 问题 | Intent | Gold Scope | Target File | BM25 | Dense | RRF | Selection Input Before/After | Final Evidence Before/After | Chunk Before/After | Role Top-1 Before/After | Fact Type After | Sheet After | Location Before/After | 错误标记 |
|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|
| BA-001 | TEMPLATE_QUERY | GOLD_OUT_OF_SCOPE | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 标准模板/标准模板 | - | - | True/True | 无 |
| BA-002 | METHOD_QUERY | GOLD_OUT_OF_SCOPE | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 项目案例/项目案例 | - | - | True/True | 无 |
| BA-003 | CASE_QUERY | GOLD_OUT_OF_SCOPE | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 管理指南/项目案例 | - | - | True/True | 无 |
| BA-004 | METHOD_QUERY | GOLD_OUT_OF_SCOPE | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 管理指南/管理指南 | - | - | True/True | 无 |
| BA-005 | DISCIPLINE_QUERY | GOLD_UNCONFIRMED | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 项目案例/项目案例 | - | - | True/True | 无 |
| BA-006 | POLICY_QUERY | GOLD_UNCONFIRMED | 范围外/待确认 | True | True | True | True/True | False/True | 0/1 | 管理指南/管理指南 | COUNT_FACT, DATE_FACT, SCOPE_FACT | - | True/True | 无 |
| BA-007 | POLICY_QUERY | GOLD_IN_ROOT | 是 | True | True | True | True/True | True/True | 1/2 | 管理指南/管理指南 | DATE_FACT | - | True/True | 无 |
| BA-008 | CASE_QUERY | GOLD_OUT_OF_SCOPE | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 项目案例/项目案例 | - | - | True/True | 无 |
| BA-009 | DISCIPLINE_QUERY | GOLD_UNCONFIRMED | 范围外/待确认 | False | False | False | False/False | False/False | 0/0 | 项目案例/管理指南 | - | - | True/True | 无 |
| BA-010 | TEMPLATE_QUERY | GOLD_IN_ROOT | 是 | False | True | True | True/True | False/True | 0/6 | 标准模板/标准模板 | AMOUNT_FACT, COUNT_FACT, SCOPE_FACT | 价值创造, 方案比选, 方案比选 (2) | True/True | 无 |

> 注：上表 Selection Input Before/After 的第二个值表示优化版目标文件是否进入优化 Selection Input；优化版固定读取 RRF Top20。

## 4. Gold_IN_ROOT 核心指标

| 指标 | Baseline | Optimized |
|---|---:|---:|
| Target File Final Evidence 命中率 | 1/2 (50.0%) | 2/2 (100.0%) |
| Target Chunk 平均数量 | 0.50 | 4.00 |
| Selector Recovery Rate | 1/2 (50.0%) | 2/2 (100.0%) |
| Evidence Location 完整率 | 2/2 (100.0%) | 2/2 (100.0%) |

## 5. 全量排序回归指标

| 指标 | Baseline | Optimized |
|---|---:|---:|
| Intent Role Top-1 符合率 | 8/10 (80.0%) | 9/10 (90.0%) |
| Fact Type 匹配率（GOLD_IN_ROOT适用题） | 2/2 (100.0%) | 2/2 (100.0%) |
| Fact Type 覆盖率（全量诊断，不计失败） | 7/7 (100.0%) | 3/7 (42.9%) |
| Location 完整率 | 10/10 (100.0%) | 10/10 (100.0%) |
| 错误 Target Protection | N/A | 0 |
| ROLE_ORDER_REGRESSION | N/A | 0 |
| FACT_SCOPE_MISMATCH | N/A | 0 |
| NO_DIRECT_EVIDENCE_PROTECTED | N/A | 0 |

## 6. 误提升专项检查

- 仅因年份相同误提升：本版年份只作为软评分组件，未单独触发 Target Protection。
- 仅因“价值创造”“设计管理”等通用词误判：Target Protection 只对 BA-007、BA-010 的明确目标文件生效；通用词只参与 relevance_score。
- 项目级金额误当公司级金额：BA-008 标记为 GOLD_OUT_OF_SCOPE，并保留 FACT_SCOPE_MISMATCH 检查，不计入 Root-002 Selector Recovery。
- 案例误当正式制度、模板误当项目事实：角色排序作为软评分，不做硬过滤；逐题 role_top1 和决策事件已保存。
- Target File Protection 锁住无答案文件：BA-007、BA-010 均 `target_file_no_direct_evidence=false`；错误保护数量应为 0。

## 7. 重点验收

### BA-007

- 目标 PDF 未回退，仍进入优化 Final Evidence。
- 优化版保留两个目标 PDF Chunk，其中包含直接示范项目/年份相关证据的 Chunk。
- Location 完整，未启用 Reranker，未调整 RRF。

### BA-010

- 目标 Workbook 未回退，进入优化 Final Evidence。
- 优化版保留 6 个目标 Workbook Chunk，覆盖价值创造、方案比选、方案比选 (2) Sheet。
- 目标 Workbook 的 COUNT_FACT、AMOUNT_FACT、SCOPE_FACT 均有匹配记录。
- 其他项目价值创造案例没有替代目标 Workbook。

## 8. 结论

本次 Shadow A/B 验证表明，优化版对 GOLD_IN_ROOT 的 BA-007、BA-010 均未回退，并改善了目标 Chunk 保留与 Workbook Sheet 覆盖。GOLD_OUT_OF_SCOPE / GOLD_UNCONFIRMED 题目未被计入 Selector 失败。

本结果只证明 Evidence Selection 层的 Shadow 改善，不代表最终答案质量已验证，也不授权进入正式链路。
