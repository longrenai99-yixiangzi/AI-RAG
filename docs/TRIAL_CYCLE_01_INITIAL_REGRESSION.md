# TRIAL-CYCLE-01 初始回归

> Business Gold严格验收；Trial Questions仅记录运行现象，不作为准确率分母。全程只使用8010 Shadow，Provider HTTP Requests=0。

## 结果

- Business Gold：3/3 通过。
- Trial Questions：12 题，仅观察。
- 运行状态分布：`{'ANSWERED': 7, 'CONFLICTING_ANSWER': 1, 'PARTIAL_ANSWER': 1, 'SOURCE_SCOPE_MISSING': 6}`。

## 明细

| ID | Set | Runtime | Strict Result | Source Hit | Missing Facts |
|---|---|---|---|---|---|
| BA-001 | TRIAL_QUESTION | ANSWERED | OBSERVED_ONLY | None | - |
| BA-002 | TRIAL_QUESTION | ANSWERED | OBSERVED_ONLY | None | - |
| BA-003 | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |
| BA-004 | TRIAL_QUESTION | ANSWERED | OBSERVED_ONLY | None | - |
| BA-005 | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |
| BA-006 | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |
| BA-007 | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |
| BA-008 | TRIAL_QUESTION | CONFLICTING_ANSWER | OBSERVED_ONLY | None | - |
| BA-009 | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |
| BA-010 | TRIAL_QUESTION | PARTIAL_ANSWER | OBSERVED_ONLY | None | - |
| TQ-001 | BUSINESS_GOLD | ANSWERED | PASSED | True | - |
| TQ-002 | BUSINESS_GOLD | ANSWERED | PASSED | True | - |
| TQ-003 | BUSINESS_GOLD | ANSWERED | PASSED | True | - |
| TF_b2ec20e2e77a5cda | TRIAL_QUESTION | ANSWERED | OBSERVED_ONLY | False | - |
| TF_a57f372a2496545c | TRIAL_QUESTION | SOURCE_SCOPE_MISSING | OBSERVED_ONLY | None | - |

## 解释

- Trial题的失败不自动归咎于Retriever；必须先进入Failure Diagnosis与Source Closure。
- Source Scope Missing是治理状态，不等价于文件不存在。
- 本报告不触发任何正式知识发布。
