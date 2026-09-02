# Answer Output Protocol Final Report

> 本报告基于 100 题 Shadow 评估，使用 Minimal Answer Schema；不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. Minimal Answer Schema

LLM 只返回 claims、section_map、evidence_insufficient。后端根据已验证的 claim_text 和 section_map 生成 Section，根据 evidence_ids 生成 Citation。
Section Renderer 不总结、不扩展、不增加事实；未映射 Claim 不会被自动塞入回答。

## 2. 状态统计

| 状态 | 数量 |
|---|---:|
| GENERATED | 32 |
| PARTIAL_EVIDENCE | 34 |
| NO_EVIDENCE | 22 |
| STRUCTURE_INVALID | 12 |
| LLM_ERROR | 0 |

## 3. 质量指标

- 有效 Claim 覆盖率：100.00%（438/438）。
- 用户可见 Section 覆盖率：57.30%（267/466）。
- Citation Consistency（GENERATED）：100.00%。
- Citation Consistency（全部题目）：81.00%。
- Unsupported Claim：0。
- G 类：0。
- Repair 触发/成功/成功率：53/0/0.00%。

## 4. Provider 完整性诊断

- JSON 截断数量（初始输出）：0。
- 初始协议分类 A-E/F：{"VALID": 87, "E": 13, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}。
- finish_reason 分布：{"stop": 100}。
- 平均 completion tokens：1526.8。
- 瞬时 Provider 错误：4 题，4 次。
- HTTP 状态码：{"429": 3}。
- 每题记录 finish_reason、prompt_tokens、completion_tokens、total_tokens、max_tokens、response_length、elapsed_ms；Provider 未返回的值保持 null。

## 5. 失败样本

| Question ID | Status | Initial Protocol Category | Failure Category | finish_reason | completion_tokens |
|---|---|---|---|---|---:|
| FCQ-002 | NO_EVIDENCE | VALID | - | stop | 1121 |
| FCQ-003 | PARTIAL_EVIDENCE | VALID | I | stop | 1160 |
| FCQ-004 | STRUCTURE_INVALID | E | E | stop | 2129 |
| FCQ-005 | PARTIAL_EVIDENCE | VALID | I | stop | 2467 |
| FCQ-006 | NO_EVIDENCE | VALID | - | stop | 151 |
| FCQ-007 | PARTIAL_EVIDENCE | VALID | I | stop | 1572 |
| FCQ-009 | PARTIAL_EVIDENCE | VALID | I | stop | 1607 |
| FCQ-010 | PARTIAL_EVIDENCE | VALID | I | stop | 972 |
| FCQ-011 | NO_EVIDENCE | VALID | - | stop | 458 |
| FCQ-012 | PARTIAL_EVIDENCE | VALID | I | stop | 1050 |
| FCQ-013 | PARTIAL_EVIDENCE | VALID | I | stop | 1629 |
| FCQ-014 | PARTIAL_EVIDENCE | VALID | I | stop | 698 |
| FCQ-021 | PARTIAL_EVIDENCE | VALID | I | stop | 2465 |
| FCQ-022 | PARTIAL_EVIDENCE | VALID | I | stop | 1765 |
| FCQ-024 | NO_EVIDENCE | VALID | - | stop | 1088 |
| FCQ-025 | PARTIAL_EVIDENCE | VALID | I | stop | 1705 |
| FCQ-026 | NO_EVIDENCE | VALID | - | stop | 749 |
| FCQ-027 | NO_EVIDENCE | VALID | - | stop | 1309 |
| FCQ-028 | PARTIAL_EVIDENCE | VALID | I | stop | 1567 |
| FCQ-029 | NO_EVIDENCE | VALID | - | stop | 1579 |
| FCQ-030 | PARTIAL_EVIDENCE | VALID | I | stop | 1959 |
| FCQ-032 | STRUCTURE_INVALID | E | E | stop | 2078 |
| FCQ-033 | NO_EVIDENCE | VALID | - | stop | 353 |
| FCQ-034 | STRUCTURE_INVALID | E | E | stop | 1988 |
| FCQ-035 | NO_EVIDENCE | VALID | - | stop | 493 |
| FCQ-037 | PARTIAL_EVIDENCE | VALID | I | stop | 2357 |
| FCQ-038 | STRUCTURE_INVALID | E | E | stop | 1972 |
| FCQ-039 | STRUCTURE_INVALID | E | E | stop | 2747 |
| FCQ-040 | STRUCTURE_INVALID | E | E | stop | 1544 |
| FCQ-041 | PARTIAL_EVIDENCE | VALID | I | stop | 599 |
| FCQ-044 | PARTIAL_EVIDENCE | VALID | I | stop | 988 |
| FCQ-046 | PARTIAL_EVIDENCE | E | I | stop | 1664 |
| FCQ-048 | PARTIAL_EVIDENCE | VALID | I | stop | 1033 |
| FCQ-051 | PARTIAL_EVIDENCE | VALID | I | stop | 2174 |
| FCQ-053 | STRUCTURE_INVALID | E | E | stop | 2884 |
| FCQ-054 | PARTIAL_EVIDENCE | VALID | I | stop | 1468 |
| FCQ-055 | NO_EVIDENCE | VALID | - | stop | 400 |
| FCQ-058 | PARTIAL_EVIDENCE | VALID | I | stop | 2653 |
| FCQ-059 | PARTIAL_EVIDENCE | VALID | I | stop | 2661 |
| FCQ-061 | PARTIAL_EVIDENCE | VALID | I | stop | 650 |
| FCQ-062 | STRUCTURE_INVALID | E | E | stop | 904 |
| FCQ-063 | NO_EVIDENCE | VALID | - | stop | 211 |
| FCQ-064 | NO_EVIDENCE | VALID | - | stop | 161 |
| FCQ-065 | PARTIAL_EVIDENCE | VALID | I | stop | 2124 |
| FCQ-066 | NO_EVIDENCE | VALID | - | stop | 284 |
| FCQ-067 | NO_EVIDENCE | VALID | - | stop | 986 |
| FCQ-068 | NO_EVIDENCE | VALID | - | stop | 151 |
| FCQ-069 | PARTIAL_EVIDENCE | VALID | I | stop | 2263 |
| FCQ-074 | NO_EVIDENCE | VALID | - | stop | 189 |
| FCQ-075 | NO_EVIDENCE | VALID | - | stop | 498 |
| FCQ-077 | STRUCTURE_INVALID | E | E | stop | 822 |
| FCQ-078 | PARTIAL_EVIDENCE | VALID | I | stop | 2959 |
| FCQ-080 | NO_EVIDENCE | VALID | - | stop | 420 |
| FCQ-081 | PARTIAL_EVIDENCE | VALID | I | stop | 1543 |
| FCQ-082 | NO_EVIDENCE | VALID | - | stop | 657 |
| FCQ-083 | PARTIAL_EVIDENCE | VALID | I | stop | 1347 |
| FCQ-084 | NO_EVIDENCE | VALID | - | stop | 552 |
| FCQ-085 | PARTIAL_EVIDENCE | VALID | I | stop | 2255 |
| FCQ-086 | NO_EVIDENCE | VALID | - | stop | 1079 |
| FCQ-087 | PARTIAL_EVIDENCE | VALID | I | stop | 1705 |
| FCQ-088 | NO_EVIDENCE | VALID | - | stop | 211 |
| FCQ-091 | PARTIAL_EVIDENCE | VALID | I | stop | 3158 |
| FCQ-093 | STRUCTURE_INVALID | E | E | stop | 1960 |
| FCQ-094 | STRUCTURE_INVALID | E | E | stop | 1487 |
| FCQ-095 | PARTIAL_EVIDENCE | VALID | I | stop | 1784 |
| FCQ-097 | PARTIAL_EVIDENCE | VALID | I | stop | 1277 |
| FCQ-099 | PARTIAL_EVIDENCE | VALID | I | stop | 3099 |
| FCQ-100 | STRUCTURE_INVALID | E | E | stop | 2020 |

## 6. 验收结论

Citation Consistency、Unsupported Claim 和 G 类按确定性校验结果验收。
只有同时具备有效 Claim、用户可见 Section、通过 Claim Validation 和 Citation Render 的结果才标记 GENERATED。
STRUCTURE_INVALID 仅保留给 JSON/Schema/类型协议失败；证据不足归入 PARTIAL_EVIDENCE 或 NO_EVIDENCE。

逐题输出：D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant\answer_engine_minimal_stabilized_outputs.jsonl（100 条）。

**TASK-015.6：Answer Status Semantics & Minimal Output Protocol 完成。**
