# Fact Aggregator Shadow Report

> TASK-016E-2A：只对 BA-010 的 Optimized Evidence 目标 Workbook 执行确定性表格事实聚合。
> 未调用 LLM；未修改 Retriever、Evidence Selection、Answer Engine、8000 服务、原始 Excel 或正式 Qdrant。

## 1. Query Analysis

- Query ID：`BA-010`
- Target Project：`星谷科创中心`
- Target Workbook：`方案比选与价值创造清单方案比选及价值创造.xlsx`
- Target Sheet：`价值创造`
- Operations：`GROUP_BY(专业类别)` → `COUNT(每组)` → `FILTER(效益字段 > 0)` → `COUNT(满足条件记录)`
- SUM：未执行；问题没有要求总金额。

## 2. Workbook 版本控制

- 检测到同名 Workbook：`2` 个。
- 权威版本：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\星谷科创项目设计管理策划+设计示范项目打造方案\方案比选与价值创造清单方案比选及价值创造.xlsx`
- 选择依据：Source Discovery 登记链指向“设计示范项目打造方案”目录下的版本。
- 其他同名版本未参与计算，防止跨版本混算。

## 3. Table Extraction

- Header 行：`3`
- Header：`["专业类别", "价值创造策划点", "策划点类别", "价值创造分析", "成本分析", "涉及金额", "利润", "责任人", "完成时限", "力争/确保", "", "", "精益建造类", "便于支模、节省工期"]`
- 原始有效候选行：`86`
- 纳入统计行：`80`
- 排除行：`6`
- 排除原因：`{"no_description_or_fact_fields": 5, "summary_row_not_detail": 1}`

## 4. 专业分组统计

| 专业/原始分组值 | 条目数 | 源行号 | Evidence ID |
|---|---:|---|---|
| 整体方案 | 4 | 4, 8, 9, 10 | S1 |
| 桩基及支护 | 23 | 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 | S1 |
| 建筑 | 25 | 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59 | S1 |
| 结构 | 14 | 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73 | S1 |
| 给排水 | 4 | 74, 75, 76, 77 | S1 |
| 暖通 | 3 | 78, 79, 80 | S1 |
| 电气 | 3 | 81, 82, 83 | S1 |
| 消防 | 4 | 84, 85, 86, 87 | S1 |

> 分组值按表格原始‘专业类别’字段保留；没有把‘整体方案’、‘桩基础支护’等原始值擅自改写成建筑/结构等标准专业。

## 5. 增加效益字段检查

| 字段 | 是否存在 | 非空行 | 数值行 | 正数行 | 解析失败 | 是否作为增加效益字段 |
|---|---|---:|---:|---:|---:|---|
| 涉及金额 | True | 60 | 60 | 60 | 0 | False |
| 利润 | True | 38 | 38 | 38 | 0 | False |

- 精确目标字段 `效益对比（万元）`：`不存在`。
- 增加效益条数：`未计算（字段缺失）`
- 规则：只有真实存在的目标效益字段才允许执行 `numeric > 0`；本次没有把‘涉及金额’或‘利润’替代为目标字段。

## 6. FactAggregationResult

- aggregation_status：`PARTIAL_AGGREGATION`
- count_result：`{"by_professional": {"整体方案": 4, "桩基及支护": 23, "建筑": 25, "结构": 14, "给排水": 4, "暖通": 3, "电气": 3, "消防": 4}, "increase_effect_count": null, "increase_effect_rows": [], "increase_effect_field": null, "increase_effect_rule": null}`
- sum_result：`null`
- evidence_ids：`['S1']`
- source_rows：`80` 条，逐行保存在 `evaluation/fact_aggregation/BA-010.json`。

## 7. Provenance 验收

- 每条纳入统计记录保存 workbook、sheet、row_number、values、source_location、source_id 和 evidence_id。
- 每个专业分组保存参与统计的原始 row_number 和 Evidence ID。
- 结果没有只引用“整个 Excel”，可以逐行回查。
- 未接入正式 Answer Engine；当前只输出 Structured Fact Result。

## 8. 结论

本次状态为 `PARTIAL_AGGREGATION`：专业分组和条目计数已由真实 SourceBlock 行确定性完成；由于目标 Sheet 没有明确的‘效益对比（万元）’字段，增加效益条数未擅自计算，需业务负责人确认‘涉及金额’或‘利润’是否具有该业务含义后，再设计下一步聚合规则。
