# Fact Claim Citation Shadow Report

> TASK-016E-2B：将已确认的 BA-010 Structured Fact Result 转换为确定性 Claims、Citation 和最终回答。
> 本任务不调用 LLM，不接入正式 Answer Engine，不修改正式 Retriever、Evidence Selection 或正式 Qdrant。

## 1. FactAggregationResult

- query_id：`BA-010`
- target_project：`星谷科创中心`
- target_document：`方案比选与价值创造清单方案比选及价值创造.xlsx`
- target_sheet：`价值创造`
- business_rule：`{"benefit_semantics": "增加效益", "mapped_field": "利润", "operator": ">", "threshold": 0, "source": "business_owner_confirmation"}`
- total_rows：`80`
- increase_effect_count：`37`
- undetermined_profit_count：`43`
- aggregation_status：`PARTIAL_AGGREGATION`
- reconciliation_status：`37_CONFIRMED`
- evidence_ids：`['S1']`

## 2. Claims

| Claim ID | 类型 | 分组 | 数值 | 单位 | Source Rows | Evidence IDs |
|---|---|---|---:|---|---:|---|
| C1 | TOTAL_COUNT | - | 80 | 条 | 80 | S1 |
| C2 | GROUP_COUNT | 整体方案 | 4 | 条 | 4 | S1 |
| C3 | GROUP_COUNT | 桩基及支护 | 23 | 条 | 23 | S1 |
| C4 | GROUP_COUNT | 建筑 | 25 | 条 | 25 | S1 |
| C5 | GROUP_COUNT | 结构 | 14 | 条 | 14 | S1 |
| C6 | GROUP_COUNT | 给排水 | 4 | 条 | 4 | S1 |
| C7 | GROUP_COUNT | 暖通 | 3 | 条 | 3 | S1 |
| C8 | GROUP_COUNT | 电气 | 3 | 条 | 3 | S1 |
| C9 | GROUP_COUNT | 消防 | 4 | 条 | 4 | S1 |
| C10 | BENEFIT_COUNT | - | 37 | 条 | 37 | S1 |
| C11 | DATA_QUALITY_NOTE | - | 43 | 条 | 43 | S1 |

### Claim 文本

- **C1**：星谷科创中心设计价值创造清单共有80条有效明细。
- **C2**：整体方案共4条，其中利润大于0的增加效益条目为0条。
- **C3**：桩基及支护共23条，其中利润大于0的增加效益条目为12条。
- **C4**：建筑共25条，其中利润大于0的增加效益条目为12条。
- **C5**：结构共14条，其中利润大于0的增加效益条目为3条。
- **C6**：给排水共4条，其中利润大于0的增加效益条目为4条。
- **C7**：暖通共3条，其中利润大于0的增加效益条目为3条。
- **C8**：电气共3条，其中利润大于0的增加效益条目为1条。
- **C9**：消防共4条，其中利润大于0的增加效益条目为2条。
- **C10**：按已确认业务口径“增加效益 = 利润 > 0”，有效明细中共有37条增加效益记录。
- **C11**：有43条有效明细的利润字段为空或未判定；这些记录不能直接解释为没有效益。

## 3. Validator

- Fact Claim Validator：`VALID`
- Citation Validator：`VALID`
- Fact Claim errors：`无`
- Citation errors：`无`
- 第 88 行是否进入 Claim：否。
- 利润未判定记录是否被描述为无效益：否。

## 4. Final Answer

### 结论

星谷科创中心设计价值创造清单共有 **80 条有效明细**。按业务负责人确认口径“增加效益 = 利润 > 0”，其中有 **37 条增加效益记录**。

### 专业/原始分组统计

| 专业/原始分组 | 总条数 | 其中增加效益条数（利润 > 0） |
|---|---:|---:|
| 整体方案 | 4 | 0 |
| 桩基及支护 | 23 | 12 |
| 建筑 | 25 | 12 |
| 结构 | 14 | 3 |
| 给排水 | 4 | 4 |
| 暖通 | 3 | 3 |
| 电气 | 3 | 1 |
| 消防 | 4 | 2 |

### 口径说明

- 增加效益字段：`利润`；判断规则：`利润 > 0`。
- 有效明细中利润为空或未判定的记录：**43 条**。这些记录不能直接解释为没有效益。
- 第 88 行是公式汇总行，不属于有效明细，未计入上述统计。

## 5. Citation / Provenance

每个 Claim 的 `source_rows`、`source_locations` 和 `evidence_ids` 均保存在 `evaluation/fact_answers/BA-010.json`；统计 Claim 不只引用整个 Workbook。

## 6. 边界

- LLM 未参与统计或语言改写。
- 未将利润空值自动当成 0。
- 未执行 SUM，不输出总金额。
- 未接入正式 Answer Engine。
