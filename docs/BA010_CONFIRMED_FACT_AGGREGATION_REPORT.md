# BA-010 Confirmed Fact Aggregation Report

> TASK-016E-2A.2：基于业务负责人确认的“利润 > 0”口径，对 BA-010 执行 Shadow 确定性聚合。
> 不调用 LLM，不修改原始 Excel、Retriever、Evidence Selection、Answer Engine、8000 服务或正式 Qdrant。

## 1. 已确认业务规则

```yaml
benefit_semantics: 增加效益
mapped_field: 利润
operator: '>'
threshold: 0
business_rule_source: business_owner_confirmation
```

缺失值、`/`、文本或无法解析的利润值不视为 0；它们单独归入“利润未判定”。

## 2. 目标范围

- Workbook：`方案比选与价值创造清单方案比选及价值创造.xlsx`
- Sheet：`价值创造`
- 权威路径：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\星谷科创项目设计管理策划+设计示范项目打造方案\方案比选与价值创造清单方案比选及价值创造.xlsx`
- Evidence IDs：`['S1']`
- 未使用其他 Sheet 的“效益”字段，也未使用其他项目案例。

## 3. 总体统计

| 指标 | 数量 |
|---|---:|
| 总有效条目数 | 80 |
| 增加效益条目数（利润 > 0） | 37 |
| 确定未增加效益条目数（利润 <= 0） | 0 |
| 利润未判定条目数 | 43 |

## 4. 按专业/原始分组统计

| 专业/原始分组值 | 专业总条数 | 增加效益条数 | 确定未增加效益 | 利润未判定 | 增加效益源行号 |
|---|---:|---:|---:|---:|---|
| 整体方案 | 4 | 0 | 0 | 4 | - |
| 桩基及支护 | 23 | 12 | 0 | 11 | 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 24, 30 |
| 建筑 | 25 | 12 | 0 | 13 | 39, 40, 42, 43, 44, 45, 48, 51, 52, 53, 54, 55 |
| 结构 | 14 | 3 | 0 | 11 | 60, 64, 73 |
| 给排水 | 4 | 4 | 0 | 0 | 74, 75, 76, 77 |
| 暖通 | 3 | 3 | 0 | 0 | 78, 79, 80 |
| 电气 | 3 | 1 | 0 | 2 | 82 |
| 消防 | 4 | 2 | 0 | 2 | 84, 87 |

## 5. 未判定利润行

| 行号 | 分组 | 原始利润值 | 原因 | Evidence ID |
|---:|---|---|---|---|
| 4 | 整体方案 | `` | empty_or_placeholder | S1 |
| 8 | 整体方案 | `` | empty_or_placeholder | S1 |
| 9 | 整体方案 | `` | empty_or_placeholder | S1 |
| 10 | 整体方案 | `` | empty_or_placeholder | S1 |
| 22 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 23 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 25 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 26 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 27 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 28 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 29 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 31 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 32 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 33 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 34 | 桩基及支护 | `` | empty_or_placeholder | S1 |
| 35 | 建筑 | `` | empty_or_placeholder | S1 |
| 36 | 建筑 | `` | empty_or_placeholder | S1 |
| 37 | 建筑 | `` | empty_or_placeholder | S1 |
| 38 | 建筑 | `` | empty_or_placeholder | S1 |
| 41 | 建筑 | `` | empty_or_placeholder | S1 |
| 46 | 建筑 | `` | empty_or_placeholder | S1 |
| 47 | 建筑 | `` | empty_or_placeholder | S1 |
| 49 | 建筑 | `` | empty_or_placeholder | S1 |
| 50 | 建筑 | `` | empty_or_placeholder | S1 |
| 56 | 建筑 | `` | empty_or_placeholder | S1 |
| 57 | 建筑 | `` | empty_or_placeholder | S1 |
| 58 | 建筑 | `` | empty_or_placeholder | S1 |
| 59 | 建筑 | `` | empty_or_placeholder | S1 |
| 61 | 结构 | `` | empty_or_placeholder | S1 |
| 62 | 结构 | `` | empty_or_placeholder | S1 |
| 63 | 结构 | `` | empty_or_placeholder | S1 |
| 65 | 结构 | `` | empty_or_placeholder | S1 |
| 66 | 结构 | `` | empty_or_placeholder | S1 |
| 67 | 结构 | `` | empty_or_placeholder | S1 |
| 68 | 结构 | `` | empty_or_placeholder | S1 |
| 69 | 结构 | `` | empty_or_placeholder | S1 |
| 70 | 结构 | `` | empty_or_placeholder | S1 |
| 71 | 结构 | `` | empty_or_placeholder | S1 |
| 72 | 结构 | `` | empty_or_placeholder | S1 |
| 81 | 电气 | `` | empty_or_placeholder | S1 |
| 83 | 电气 | `` | empty_or_placeholder | S1 |
| 85 | 消防 | `` | empty_or_placeholder | S1 |
| 86 | 消防 | `` | empty_or_placeholder | S1 |

## 6. Provenance

- 每一条源行均保留 workbook、sheet、row_number、values、source_location、source_id 和 evidence_id。
- 增加效益判断只读取 `利润` 单元格，未读取或替代为“涉及金额”“收入”“效益”。
- 参与计算的原始行号保存在 `evaluation/fact_aggregation/BA-010.json` 的 `source_rows` 和各分组字段中。

## 7. 聚合状态

- aggregation_status：`PARTIAL_AGGREGATION`
- 由于存在利润空值/占位符未判定行，当前状态为 `PARTIAL_AGGREGATION`；这不是计算失败，而是对缺失业务数据的保守标记。
- 如业务负责人进一步确认空利润按 0 处理，才可在后续任务中重新定义未增加效益统计；本次不自行推断。
