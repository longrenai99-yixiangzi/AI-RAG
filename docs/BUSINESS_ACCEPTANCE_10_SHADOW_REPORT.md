# Answer Output Protocol Final Report

> 本报告基于 100 题 Shadow 评估，使用 Minimal Answer Schema；不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. Minimal Answer Schema

LLM 只返回 claims、section_map、evidence_insufficient。后端根据已验证的 claim_text 和 section_map 生成 Section，根据 evidence_ids 生成 Citation。
Section Renderer 不总结、不扩展、不增加事实；未映射 Claim 不会被自动塞入回答。

## 2. 状态统计

| 状态 | 数量 |
|---|---:|
| GENERATED | 1 |
| PARTIAL_EVIDENCE | 2 |
| NO_EVIDENCE | 6 |
| STRUCTURE_INVALID | 1 |
| LLM_ERROR | 0 |

## 3. 质量指标

- 有效 Claim 覆盖率：100.00%（9/9）。
- 用户可见 Section 覆盖率：19.57%（9/46）。
- Citation Consistency（GENERATED）：100.00%。
- Citation Consistency（全部题目）：90.00%。
- Unsupported Claim：0。
- G 类：0。
- Repair 触发/成功/成功率：3/0/0.00%。

## 4. Provider 完整性诊断

- JSON 截断数量（初始输出）：0。
- 初始协议分类 A-E/F：{"VALID": 9, "E": 1, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}。
- finish_reason 分布：{"stop": 10}。
- 平均 completion tokens：456.7。
- 瞬时 Provider 错误：0 题，0 次。
- HTTP 状态码：{}。
- 每题记录 finish_reason、prompt_tokens、completion_tokens、total_tokens、max_tokens、response_length、elapsed_ms；Provider 未返回的值保持 null。

## 5. 失败样本

| Question ID | Status | Initial Protocol Category | Failure Category | finish_reason | completion_tokens |
|---|---|---|---|---|---:|
| BA-001 | PARTIAL_EVIDENCE | VALID | I | stop | 1112 |
| BA-002 | NO_EVIDENCE | VALID | I | stop | 337 |
| BA-003 | NO_EVIDENCE | VALID | I | stop | 348 |
| BA-004 | STRUCTURE_INVALID | E | E | stop | 756 |
| BA-005 | NO_EVIDENCE | VALID | I | stop | 280 |
| BA-006 | NO_EVIDENCE | VALID | I | stop | 405 |
| BA-007 | NO_EVIDENCE | VALID | I | stop | 287 |
| BA-009 | NO_EVIDENCE | VALID | I | stop | 344 |
| BA-010 | PARTIAL_EVIDENCE | VALID | I | stop | 552 |

## 6. 验收结论

Citation Consistency、Unsupported Claim 和 G 类按确定性校验结果验收。
只有同时具备有效 Claim、用户可见 Section、通过 Claim Validation 和 Citation Render 的结果才标记 GENERATED。
STRUCTURE_INVALID 仅保留给 JSON/Schema/类型协议失败；证据不足归入 PARTIAL_EVIDENCE 或 NO_EVIDENCE。

逐题输出：D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant\business_acceptance_10_outputs.jsonl（10 条）。

**TASK-015.6：Answer Status Semantics & Minimal Output Protocol 完成。**
