# Atomic Fact Claim Validation Report

> TASK-016E-2B.1：将 BA-010 的复合分组事实拆分为原子化、独立可验证 Claim。
> 不重新计算 Excel，不调用 LLM，不修改业务规则、Retriever、Evidence Selection、正式 Qdrant 或 Answer Engine。

## 1. 冻结事实

- total_rows：80
- increase_effect_count：37
- undetermined_profit_count：43
- reconciliation_status：`37_CONFIRMED`
- business_rule：增加效益 = 利润 > 0

## 2. Claim 数量

- Claim 总数：**19**
- TOTAL_COUNT：1
- GROUP_COUNT：8
- BENEFIT_COUNT：9（8 个分组 + 1 个总体）
- DATA_QUALITY_NOTE：1

## 3. 原子 Claim 对账

| Claim ID | 类型 | Group | Core Value | Source Rows | Evidence IDs |
|---|---|---|---:|---:|---|
| C1 | TOTAL_COUNT | - | 80 | 80 | S1 |
| C2 | GROUP_COUNT | 整体方案 | 4 | 4 | S1 |
| C3 | GROUP_COUNT | 桩基及支护 | 23 | 23 | S1 |
| C4 | GROUP_COUNT | 建筑 | 25 | 25 | S1 |
| C5 | GROUP_COUNT | 结构 | 14 | 14 | S1 |
| C6 | GROUP_COUNT | 给排水 | 4 | 4 | S1 |
| C7 | GROUP_COUNT | 暖通 | 3 | 3 | S1 |
| C8 | GROUP_COUNT | 电气 | 3 | 3 | S1 |
| C9 | GROUP_COUNT | 消防 | 4 | 4 | S1 |
| C10 | BENEFIT_COUNT | 整体方案 | 0 | 0 | S1 |
| C11 | BENEFIT_COUNT | 桩基及支护 | 12 | 12 | S1 |
| C12 | BENEFIT_COUNT | 建筑 | 12 | 12 | S1 |
| C13 | BENEFIT_COUNT | 结构 | 3 | 3 | S1 |
| C14 | BENEFIT_COUNT | 给排水 | 4 | 4 | S1 |
| C15 | BENEFIT_COUNT | 暖通 | 3 | 3 | S1 |
| C16 | BENEFIT_COUNT | 电气 | 1 | 1 | S1 |
| C17 | BENEFIT_COUNT | 消防 | 2 | 2 | S1 |
| C18 | BENEFIT_COUNT | - | 37 | 37 | S1 |
| C19 | DATA_QUALITY_NOTE | - | 43 | 43 | S1 |

复合显示仍可在用户界面合并，例如“建筑：25条，其中增加效益12条”，但后台分别来自一个 GROUP_COUNT Claim 和一个 BENEFIT_COUNT Claim。

## 4. Validator

- Fact Claim Validator：`VALID`
- Citation Validator：`VALID`
- Validator errors：`无`
- GROUP_COUNT 总和：80
- 分组 BENEFIT_COUNT 总和：37
- 总体 BENEFIT_COUNT：37
- DATA_QUALITY_NOTE：43
- 第 88 行进入 Claim：否

## 5. Citation

每个 GROUP_COUNT 引用该分组全部有效明细行；每个分组 BENEFIT_COUNT 只引用该分组利润 > 0 的行；总体 BENEFIT_COUNT 引用 37 条利润 > 0 行。
所有 Claim 的 source_locations 和 evidence_ids 保存在 `evaluation/fact_answers/BA-010.json`。

## 6. 结论

原子 Claim 验证通过。数字事实没有被合并成不可独立验证的 Claim，利润未判定的 43 条也没有被描述为未增加效益。
