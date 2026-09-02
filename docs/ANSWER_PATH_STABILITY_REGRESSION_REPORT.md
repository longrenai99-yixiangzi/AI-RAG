# Answer Path Stability & Final Business Regression Report

> TASK-016E-3：验证 BA-007 普通知识问答路径与 BA-010 结构化事实统计路径。
> 仅在 Shadow 环境执行；未修改正式 Retriever、Answer Engine、8000 服务或正式 Qdrant。
> BA-010 未调用 LLM，所有数字来自冻结 Fact Result 和 Atomic Claims。

## 1. BA-007 普通知识问答路径

- Evidence：固定使用 `evaluation/traces_optimized/BA-007.json` 的同一 Bundle。
- 回放次数：10
- 状态分布：`{"GENERATED": 9, "STRUCTURE_INVALID": 1}`
- Claim Validator 通过：10/10
- Citation Validator 通过：9/10
- Unsupported Claim：0
- Invalid Evidence ID：0
- STRUCTURE_INVALID：1
- BA007 稳定性结论：**BA007_UNSTABLE**

### BA-007 失败阶段分布

| Primary Root Cause | 次数 |
|---|---:|
| D SECTION_MAPPING_FAILURE | 1 |
| J OTHER | 9 |

失败样本：`evaluation/answer_stability/BA-007/run_05.json`。

- LLM 原始 JSON 可解析；
- Schema 失败：`section_map references unknown claim_id`；
- 原因：`section_map.evidence` 使用了 Evidence ID `S1`，而该字段要求 Claim ID；
- Repair 已触发但未修复；
- Claim Validator 初步通过，但 Citation Renderer 因 `S1` 不是 Claim ID 而失败；
- Provider HTTP 状态为 200，不属于 Provider/网络失败。

## 2. BA-010 结构化事实统计路径

- 路径：冻结 Fact Result → Atomic Claims → Fact Claim Validator → Citation Validator → Deterministic Answer Renderer。
- 回放次数：10
- Fact Claim Validator 通过：10/10
- Citation Validator 通过：10/10
- 80 一致率：10/10
- 37 一致率：10/10
- 43 一致率：10/10
- 专业分组一致率：10/10
- source_rows 一致率：10/10
- BA-010 稳定性结论：**BA010_STABLE**

## 3. BA-010 最终答案检查

- 总有效明细：80 条；
- 分组：整体方案、桩基及支护、建筑、结构、给排水、暖通、电气、消防；
- 每组总条数和利润 > 0 条数均来自 Atomic Claims；
- 总增加效益：37 条；
- 业务口径：增加效益 = 利润 > 0；
- 利润为空/未判定：43 条，不描述为无效益；
- 第 88 行汇总公式未进入明细 Claim；

## 4. 业务路径结论

- 普通知识问答路径：不稳定，需先诊断失败样本。
- Fact Answer Path：可以进入下一阶段 Shadow 路由集成。
- 本次没有进入正式 Answer Engine。
