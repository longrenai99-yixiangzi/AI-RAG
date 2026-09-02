# Evidence Quality Evaluation Report

> 本报告评价 TASK-014A Evidence Selection 是否满足 100 个 Gold Questions 的回答需求。
> 不调用 LLM，不修改正式 Retriever、8000 服务或 Qdrant。

## 1. 评估范围

- Gold Questions：100。
- Shadow Collection：4747 点。
- Shadow Chunk：4747。
- LLM 调用次数：0。
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU，CUDA：True。
- 查询向量耗时：10.819 秒；Reranker：43.629 秒。

## 2. 核心指标

| 指标 | 结果 |
|---|---:|
| Evidence Role Match Top-1 | 25.00% |
| Evidence Role Match Top-5 | 54.00% |
| Authority Level Match Top-1 | 25.00% |
| Authority Level Match Top-5 | 54.00% |
| Usage Scene Match Top-1 | 25.00% |
| Usage Scene Match Top-5 | 54.00% |
| Expected File Hit Rate | 12.00% |
| Intent-Evidence Match Top-1 | 55.00% |
| Intent-Evidence Match Top-5 | 97.00% |
| 制度/案例/模板混淆率 | 17.00% |
| 混合角色 Evidence Bundle 比例 | 19.00% |

## 3. 按 Intent 分析

| Intent | 题数 | Role Top-1 | Role Top-5 | Authority Top-1 | Expected File | Intent Match | 混淆率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CASE_QUERY | 15 | 33.33% | 40.00% | 33.33% | 33.33% | 80.00% | 13.33% |
| DISCIPLINE_QUERY | 30 | 13.33% | 23.33% | 13.33% | 6.67% | 83.33% | 0.00% |
| METHOD_QUERY | 23 | 8.70% | 56.52% | 8.70% | 4.35% | 8.70% | 0.00% |
| POLICY_QUERY | 19 | 36.84% | 78.95% | 36.84% | 15.79% | 47.37% | 47.37% |
| TEMPLATE_QUERY | 13 | 53.85% | 100.00% | 53.85% | 7.69% | 53.85% | 46.15% |

### 重点问题

- POLICY_QUERY：检查 Top-1 是否为正式制度或管理指南；案例、培训和汇报材料出现在 Top-1 时计为制度证据混淆。
- CASE_QUERY：检查 Top-1 是否为项目案例；正式制度、培训和汇报材料出现在 Top-1 时计为案例证据混淆。
- TEMPLATE_QUERY：检查 Top-1 是否为标准模板；项目案例、培训和汇报材料出现在 Top-1 时计为模板证据混淆。

## 4. 混淆问题清单

| 问题 ID | Intent | Expected Role | Top Role | Selected Roles | Expected File Hit |
|---|---|---|---|---|---|
| FCQ-013 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 汇报材料, 汇报材料, 汇报材料, 汇报材料 | 否 |
| FCQ-016 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 管理指南, 管理指南, 项目案例, 项目案例 | 否 |
| FCQ-020 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 管理指南, 汇报材料, 项目案例, 项目案例 | 否 |
| FCQ-044 | TEMPLATE_QUERY | 标准模板 | 项目案例 | 项目案例, 标准模板, 标准模板, 标准模板, 项目案例 | 否 |
| FCQ-047 | TEMPLATE_QUERY | 标准模板 | 项目案例 | 项目案例, 标准模板, 标准模板, 管理指南, 标准模板 | 否 |
| FCQ-050 | TEMPLATE_QUERY | 标准模板 | 汇报材料 | 汇报材料, 管理指南, 标准模板, 标准模板, 标准模板 | 否 |
| FCQ-054 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 项目案例, 其他, 项目案例, 项目案例 | 否 |
| FCQ-067 | CASE_QUERY | 其他 | 汇报材料 | 汇报材料, 项目案例, 项目案例, 项目案例, 项目案例 | 是 |
| FCQ-068 | CASE_QUERY | 项目案例 | 汇报材料 | 汇报材料, 项目案例, 项目案例, 项目案例, 项目案例 | 是 |
| FCQ-072 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 正式制度, 正式制度, 正式制度, 正式制度 | 是 |
| FCQ-074 | POLICY_QUERY | 管理指南 | 培训材料 | 培训材料, 正式制度, 标准模板, 正式制度, 正式制度 | 否 |
| FCQ-075 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 正式制度, 管理指南, 管理指南, 项目案例 | 否 |
| FCQ-077 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 正式制度, 管理指南, 标准模板, 管理指南 | 否 |
| FCQ-079 | POLICY_QUERY | 管理指南 | 项目案例 | 项目案例, 管理指南, 管理指南, 项目案例, 项目案例 | 否 |
| FCQ-084 | TEMPLATE_QUERY | 管理指南 | 项目案例 | 项目案例, 管理指南, 标准模板, 管理指南, 管理指南 | 否 |
| FCQ-085 | TEMPLATE_QUERY | 标准模板 | 汇报材料 | 汇报材料, 标准模板, 标准模板, 管理指南, 项目案例 | 否 |
| FCQ-086 | TEMPLATE_QUERY | 管理指南 | 项目案例 | 项目案例, 标准模板, 管理指南, 标准模板, 标准模板 | 否 |

## 5. 结论

1. Evidence Quality 评价只验证证据选择和可回查性，不代表最终答案事实正确性。
2. 如果 Expected File Hit Rate 低而 Intent Match 高，说明策略选到了同角色资料，但没有选中 Gold 指定文件，需要继续优化 Chunk/文件级排序。
3. 如果制度问题混入项目案例、培训或汇报材料，应提升正式制度/管理指南证据门槛，并保留证据不足降级。
4. 如果案例或模板问题的 Top-1 角色不匹配，不应由 LLM 在生成阶段自行纠正，应该先修正 Evidence Selection。
5. 本报告不修改正式链路；是否进入正式 Retriever 前，还需通过 Claim-Citation 覆盖和拒答策略评估。

## 6. 边界确认

- LLM 调用：否。
- 正式 Retriever：未修改。
- 8000 服务：未修改。
- 正式 Qdrant：未修改。

**TASK-014B：Evidence Quality Evaluation 完成。**
