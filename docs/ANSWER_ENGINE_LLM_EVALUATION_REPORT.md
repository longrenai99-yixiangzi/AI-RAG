# Answer Engine LLM Shadow Report

> 本报告验证 Query Understanding → Document Profile Retrieval → Hybrid/Chunk Retrieval → Evidence Ranking → Answer Policy → LLM Provider → Claim-Evidence Validation。
> 本次使用 Shadow 环境，不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. 实现模块

- app/answer_engine/llm/llm_provider.py：OpenAI-compatible Shadow Provider，复用现有 LLM 配置。
- app/answer_engine/llm/prompt_builder.py：按 Intent 和 Evidence Bundle 生成受约束 Prompt。
- app/answer_engine/llm/answer_generator.py：调用 Provider、解析结构化回答并触发 Claim 校验。
- app/answer_engine/llm/claim_validator.py：校验 Claim 的 Evidence ID 和答案中的 Citation。

## 2. 评估结果

- Gold Questions：100。
- Shadow Collection：4747 点；Chunk：4747。
- Evidence 条目数：492。
- Profile expected_file 覆盖率：44.00%。
- LLM 探针：通过。
- LLM 探针调用次数：1。
- 实际答案生成尝试：100。
- CUDA：True，GPU：NVIDIA GeForce RTX 4060 Laptop GPU。
- 查询向量耗时：4.907 秒。

| 指标 | 结果 |
|---|---:|
| 答案结构正确率 | 32.98% |
| Citation完整率 | 100.00% |
| Unsupported Claim 数量 | 1 |
| Claim Validation 有效率 | 100.00% |
| 制度/案例混淆率 | 6.38% |
| 人工可读性 | MANUAL_REVIEW_REQUIRED |

- Answer 状态：{"GENERATED": 94, "CLAIM_INVALID": 6}。

## 3. LLM 服务状态

100题中完成模型生成尝试 100 题，其中 6 题未通过最终 Claim 结果校验。
错误摘要：无

本次报告将 GENERATED、CLAIM_INVALID、LLM_ERROR 和 LLM_UNAVAILABLE 分开统计；只有 GENERATED 才进入答案结构和 Citation 质量分母。

## 4. Claim-Evidence 规则

1. 每个 Claim 必须包含至少一个 evidence_id。
2. evidence_id 必须存在于当前 Evidence Bundle。
3. 答案中的 [Sx] 只能引用当前 Evidence Bundle 的来源。
4. Claim 校验失败时不得把答案标记为确定性可信答案。
5. LLM 不得自行访问 Qdrant 或知识源，只能使用 Prompt 中提供的 Evidence。

## 5. 后续动作

### 人工抽样评价

以下抽样用于人工复核，脚本不自动给出主观分数；当前状态必须由业务人员确认。

| 抽样问题 | 结论明确性 | 专业可信度 | 可直接使用程度 |
|---|---|---|---|
| FCQ-001 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-031 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-061 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-081 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-091 | 待人工复核 | 待人工复核 | 待人工复核 |

1. 先分析 Provider 失败题和限流/超时原因，再决定是否重跑失败题。
2. 真实生成后人工抽查制度、案例、方法、模板和专业问题各类样本。
3. 在 Provider 可用前，不修改正式 Answer 链路，不把 evidence-only 结果伪装成 LLM 结论。

## 6. 边界确认

- 正式 Retriever：未修改。
- 8000 服务：未修改。
- 正式 Qdrant：未修改。
- LLM-as-Judge：未使用。

**TASK-015.3：Answer Engine LLM Shadow Evaluation 完成。**
