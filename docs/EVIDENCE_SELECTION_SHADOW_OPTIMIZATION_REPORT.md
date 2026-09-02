# Evidence Selection Shadow Optimization Report

> TASK-016D-2B：仅在 Shadow 环境对 BA-007、BA-010 进行 Evidence Selection A/B 验证。
> 未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF 参数、Reranker 或 Answer Engine。
> 未调用 LLM 做最终答案质量判断。

## 1. 优化边界

- Baseline：直接读取 `evaluation/traces/BA-007.json`、`BA-010.json`，不覆盖原文件。
- Optimized：读取同一份 RRF Top20，在 Shadow Selector 内增加软相关性、Fact Type、角色顺序、目标文件保护和动态 Chunk 配额。
- RRF：只读取 D-2A 结果，不重算、不调 RRF 参数。
- Reranker：未启用。

## 2. A/B 指标

| 问题 | 版本 | Target File in RRF Top20 | Target File in Selection Input | Target File in Final Evidence | Target Chunk 数量 | Intent Role Top-1 | Fact Type 匹配 | Workbook Sheet 覆盖 | Location 完整 |
|---|---|---|---|---|---:|---|---|---|---|
| BA-007 | Baseline | True | True | True | 1 | 管理指南 | ['DATE_FACT'] | - | True |
| BA-007 | Optimized | True | True | True | 2 | 管理指南 | ['DATE_FACT'] | - | True |
| BA-010 | Baseline | True | True | False | 0 | 标准模板 | ['AMOUNT_FACT', 'COUNT_FACT', 'SCOPE_FACT'] | - | True |
| BA-010 | Optimized | True | True | True | 6 | 标准模板 | ['AMOUNT_FACT', 'COUNT_FACT', 'SCOPE_FACT'] | 价值创造, 方案比选, 方案比选 (2) | True |

## 3. BA-007 对比

### Baseline

- 目标 PDF RRF ranks：`[1, 11]`
- 目标 PDF Selection Input ranks：`[1, 11]`
- Final Evidence target Chunk：`1`
- 基线只把 RRF Top10 送入 Evidence Selection，目标 PDF 的后续相关 Chunk 无法参与选择。

### Optimized

- 目标 PDF RRF ranks：`[1, 11]`
- Final Evidence target Chunk：`2`
- Target File No Direct Evidence：`False`
- 优化后把目标 PDF 保护在 Evidence 中，并允许其相关 Chunk 在目标配额内共同保留；这只改善证据选择，不代表答案结构已经修复。

## 4. BA-010 对比

### Baseline

- 目标 Workbook RRF ranks：`[9, 12, 15, 16, 18, 20]`
- 目标 Workbook Selection Input ranks：`[9, 12, 15, 16, 18, 20]`
- Final Evidence target Chunk：`0`
- 目标 Workbook 虽然在 RRF Top20 和基线 Selection Input 中出现，但被角色多样性与 Evidence 名额挤出。

### Optimized

- 目标 Workbook RRF ranks：`[9, 12, 15, 16, 18, 20]`
- Final Evidence target Chunk：`6`
- Sheet 覆盖：`['价值创造', '方案比选', '方案比选 (2)']`
- Fact Type 匹配：`['AMOUNT_FACT', 'COUNT_FACT', 'SCOPE_FACT']`
- Target File No Direct Evidence：`False`
- 优化后目标 Workbook 获得动态配额，并优先保留有效 Sheet；不允许其他项目的价值创造案例替代目标 Workbook。

## 5. Selector 决策事件

每个优化候选均保存以下字段：

- `pre_selection_score`
- `relevance_score`
- `role_score`
- `authority_score`
- `fact_type_score`
- `target_file_bonus`
- `final_selection_score`
- `selected`
- `decision_reason`

`decision_reason` 由本 Shadow Selector 在实际选择时写入，不是报告阶段对结果的事后猜测。

## 6. 最小方案验证结论

1. 目标文件保护可以解决“目标文件已在 RRF Top20，但没有进入最终 Evidence”的问题。
2. 文件名、路径、项目实体、年份、Sheet 和正文短语软评分可以把目标证据从通用案例中区分出来。
3. Fact Type 可以防止项目案例中的金额、条数被当作公司级或目标项目事实。
4. 清单/数量问题需要动态 Chunk 配额；固定单文档 2 Chunk 不适合多 Sheet Workbook。
5. 本任务只验证 Evidence 层，不判断 LLM 最终回答是否正确。

## 7. 下一步

建议先审阅 BA-007、BA-010 的 optimized trace，再决定是否进入 TASK-016D-2C：扩展到 BA-001～BA-010 并执行 Shadow A/B 统计。通过业务审核前，不进入正式 Evidence Selection。
