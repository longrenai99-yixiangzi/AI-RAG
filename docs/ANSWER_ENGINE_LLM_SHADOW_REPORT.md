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
- 实际答案生成尝试：22。
- CUDA：True，GPU：NVIDIA GeForce RTX 4060 Laptop GPU。
- 查询向量耗时：4.825 秒。

| 指标 | 结果 |
|---|---:|
| 答案结构正确率 | 13.64% |
| Citation完整率 | 100.00% |
| Unsupported Claim 数量 | 0 |
| Claim Validation 有效率 | 100.00% |
| 制度/案例混淆率 | 0.00% |
| 人工可读性 | MANUAL_REVIEW_REQUIRED |

- Answer 状态：{"GENERATED": 22, "CLAIM_INVALID": 4, "LLM_ERROR": 1, "LLM_UNAVAILABLE": 73}。

## 3. LLM 服务状态

本次探针未通过，因此为避免重复发送失败请求，100 题未逐题调用 LLM；生成器对 100 题统一返回 LLM_UNAVAILABLE 状态。
错误摘要：LLMError: 生成模型请求失败；请检查内网连接、模型权限和服务状态。

这意味着本报告已经验证了 Shadow 检索、Evidence、Prompt/Generator 接口和失败回退，但不能把本次结果称为 100 个真实模型答案的质量评估。

## 4. Claim-Evidence 规则

1. 每个 Claim 必须包含至少一个 evidence_id。
2. evidence_id 必须存在于当前 Evidence Bundle。
3. 答案中的 [Sx] 只能引用当前 Evidence Bundle 的来源。
4. Claim 校验失败时不得把答案标记为确定性可信答案。
5. LLM 不得自行访问 Qdrant 或知识源，只能使用 Prompt 中提供的 Evidence。

## 5. 后续动作

1. 先恢复或配置可用的 LLM 服务，再重新运行本脚本完成 100 题真实生成评估。
2. 真实生成后人工抽查制度、案例、方法、模板和专业问题各类样本。
3. 在 Provider 可用前，不修改正式 Answer 链路，不把 evidence-only 结果伪装成 LLM 结论。

## 6. 边界确认

- 正式 Retriever：未修改。
- 8000 服务：未修改。
- 正式 Qdrant：未修改。
- LLM-as-Judge：未使用。

**TASK-015：Answer Engine + LLM Shadow Integration 接口与失败回退验证完成；真实模型批量生成受当前 LLM 服务不可用阻塞。**
