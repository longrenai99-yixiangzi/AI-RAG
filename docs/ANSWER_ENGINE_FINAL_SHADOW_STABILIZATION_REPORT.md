# Answer Engine Final Shadow Stabilization Report

> 本报告基于本次 100 题 Shadow 原始输出，执行确定性 Schema、Claim 与 Citation 重放。
> 重放不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. 确定性规则

1. Claim 的 evidence_ids 是 Citation 的唯一来源。
2. 后端依据 evidence_ids 自动渲染 [S1]、[S2]，忽略模型正文自行书写的 Citation。
3. claim_id 只做确定性格式归一化，不增加事实或 Evidence。
4. Evidence ID 不存在、Claim 无 Evidence、Schema 缺字段或额外字段仍然失败。
5. Repair 最多一次，只允许格式、Schema 和已有引用修复，不允许增加事实或 Evidence。

## 2. 基线与最终结果

| 指标 | TASK-015.3 基线 | TASK-015.5 最终重放 |
|---|---:|---:|
| Generated Final Answer Rate | 94.00% | 70.00% |
| Answer Structure Correct Rate（全部题目） | 32.98% | 70.00% |
| Answer Structure Correct Rate（最终生成答案） | 未单独记录 | 100.00% |
| Claim Validation Pass Rate | 未单独记录 | 100.00% |
| Citation Consistency Rate（最终生成答案） | 未单独记录 | 100.00% |
| Citation Consistency Rate（全部题目） | 未单独记录 | 70.00% |
| CLAIM_INVALID（最终未通过题数） | 6 | 30 |
| Unsupported Claim | 1 | 0 |
| G 类 Citation mismatch | 12 | 0 |
| Repair 触发 | 未记录 | 59 |
| Repair 成功率 | 未记录 | 49.15% |

## 3. 最终状态与 G/D/I 分类

- PARTIAL_EVIDENCE：0。
- STRUCTURE_INVALID：30。
- 最终 LLM_ERROR：0。
- 瞬时 Provider 错误记录：5 题，错误事件 6 次。
- HTTP 状态码记录：{}。
- 最终失败分类：{"A": 70, "D": 30}。
- I 类：0；G 类：0。

## 4. G/D/I 失败样本重放

| Question ID | Final Status | Category | Repair Triggered | Repair Success | Provider Errors |
|---|---|---|---|---|---|
| FCQ-004 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-008 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-013 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-016 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-018 | STRUCTURE_INVALID | D | 是 | 否 | 1 |
| FCQ-025 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-030 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-034 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-037 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-040 | STRUCTURE_INVALID | D | 是 | 否 | 2 |
| FCQ-042 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-043 | STRUCTURE_INVALID | D | 是 | 否 | 1 |
| FCQ-045 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-046 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-049 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-050 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-051 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-052 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-056 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-057 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-060 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-065 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-070 | STRUCTURE_INVALID | D | 是 | 否 | 1 |
| FCQ-076 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-078 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-087 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-095 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-098 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-099 | STRUCTURE_INVALID | D | 是 | 否 | 0 |
| FCQ-100 | STRUCTURE_INVALID | D | 是 | 否 | 0 |

## 5. 原始输出持久化

- 稳定化输出：D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant\answer_engine_stabilized_outputs.jsonl。
- 记录数量：100。
- 每题保存 question_id、intent、evidence_bundle、raw_llm_response、parsed_response、repair_response、final_status、claim_validation_result、citation_render_result。

## 6. 验收结论

Citation Consistency 以确定性渲染和 Claim 校验为准；本次最终生成答案为 100%，G 类为 0，Unsupported Claim 为 0。
仍有 30 题 STRUCTURE_INVALID，说明技术性 Schema/Provider 输出问题尚未达到进入正式 Answer 链路的条件。
瞬时 Provider 错误已与最终 LLM_ERROR 分开统计；本次有错误事件但最终没有遗留 LLM_ERROR。
TASK-015.3 的逐题原始输出未持久化，无法对历史 6 个 CLAIM_INVALID 逐题回放；本报告使用本次 100 题持久化输出作为可复核基线。

**TASK-015.5：Claim-Citation Deterministic Rendering & Final Shadow Stabilization 完成。**
