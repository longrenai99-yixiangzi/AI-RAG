# Provider Runtime Guard Report

> TASK-017E-2.1 仅在 Shadow 环境执行。未修改 Retriever、Evidence Selection、Scope、Policy Facet、Preflight、Router、OPTION_QUERY、Fact Path、正式 Qdrant 或 8000 服务。
> TASK-017E-2 的 Retry Taxonomy 未修改；本任务只增加持久化预算与跨请求 Circuit Breaker。

## 1. Budget Persistence

- `provider_budget.json`：`max_real_requests=40`，`used_real_requests=60`，`remaining_real_requests=0`，`status=EXHAUSTED`。
- 历史实际调用计数：`60`；本任务新增真实 HTTP 请求：`0`。
- 每次请求在调用底层 Provider 前先做持久化 reserve；预算不足直接返回 `PROVIDER_TEST_BUDGET_EXHAUSTED` 与 `TEST_EXECUTION_GUARD`，不发 HTTP。

## 2. Crash / Restart Test

| Test | Used after restart | Remaining after restart | HTTP after reserve | Result |
|---|---:|---:|---|---|
| BUDGET-CRASH-RESTART | `1` | `0` | `True` | PASS |
| BUDGET-ZERO-NO-HTTP | `-` | `-` | `False` | PASS |

## 3. Circuit State Transition / Fault Injection

- 阈值：连续5个 Question-level 最终临时失败；cooldown=60秒；HALF_OPEN 只允许一个 Probe。单个 Question 内部仍最多3次尝试。

| Test | Final Status | Attempt Count | HTTP Requests | Before | After | Expected |
|---|---|---:|---:|---|---|---|
| CIRCUIT-1-FINAL-5XX | `PROVIDER_TEMPORARY_FAILURE` | 3 | 3 | `CLOSED` | `CLOSED` | `` |
| CIRCUIT-2-FINAL-5XX | `PROVIDER_TEMPORARY_FAILURE` | 3 | 3 | `CLOSED` | `CLOSED` | `` |
| CIRCUIT-3-FINAL-5XX | `PROVIDER_TEMPORARY_FAILURE` | 3 | 3 | `CLOSED` | `CLOSED` | `` |
| CIRCUIT-4-FINAL-5XX | `PROVIDER_TEMPORARY_FAILURE` | 3 | 3 | `CLOSED` | `CLOSED` | `` |
| CIRCUIT-5-FINAL-5XX | `PROVIDER_TEMPORARY_FAILURE` | 3 | 3 | `CLOSED` | `OPEN` | `` |
| CIRCUIT-OPEN-NEXT-QUESTION | `PROVIDER_CIRCUIT_OPEN` | 0 | 0 | `OPEN` | `OPEN` | `0` |
| COOLDOWN-HALF-OPEN-PROBE-SUCCESS | `GENERATION_READY` | 1 | 1 | `HALF_OPEN` | `CLOSED` | `OPEN -> HALF_OPEN -> CLOSED` |
| HALF-OPEN-PROBE-FAILURE | `PROVIDER_TEMPORARY_FAILURE` | 1 | 1 | `HALF_OPEN` | `OPEN` | `OPEN -> HALF_OPEN -> OPEN` |
| RETRY-AFTER-PRESERVED | `GENERATION_READY` | 2 | 2 | `CLOSED` | `CLOSED` | `` |

- Circuit 计数按 Question-level 最终失败，不按单次 attempt 计数；第5个最终5xx后 OPEN，后续普通请求 0 HTTP attempts。
- OPEN 时仍保留 Evidence、Preflight、Retrieval 上下文；OPEN 只阻止 Provider 请求。

## 4. HTTP Calls Prevented

- Circuit OPEN 阻止的 HTTP 调用：`1` 个验证场景。
- 预算耗尽阻止的 HTTP 调用：`1` 个验证场景。

## 5. Deterministic Path / Preflight

Circuit OPEN 不应污染确定性路径；Preflight 安全拒答不应触发 Provider。以下使用既有持久化结果做兼容性检查，不重新检索、不发真实请求。

| 类别 | 问题 | 既有状态 | Provider Calls | HTTP Requests | Result |
|---|---|---|---:|---:|---|
| deterministic | BA-002 | `GENERATED` | 0 | 0 | PASS |
| deterministic | BA-004 | `GENERATED` | 0 | 0 | PASS |
| deterministic | BA-008 | `GENERATED` | 0 | 0 | PASS |
| deterministic | BA-010 | `FACT_RESULT` | 0 | 0 | PASS |
| preflight | BA-003 | `NO_EVIDENCE` | 0 | 0 | PASS |
| preflight | BA-005 | `NO_EVIDENCE` | 0 | 0 | PASS |

## 6. Telemetry and Privacy

- `runtime_guard_telemetry.jsonl` 保存 budget_id、budget_before/after、circuit_state_before/after、circuit_reason、http_request_sent、attempt_count，以及 Provider 状态。
- 输出中不保存 API Key、Bearer Token、Authorization Header、密码或 Secret。

## 7. 验收结论

- Budget Persistence / Crash Restart：`PASS`。
- Circuit / Fault Injection：记录 `9` 个场景；具体状态转换见上表。
- Deterministic Path：`PASS`。
- Preflight：`PASS`。
- 本任务没有继续 Live Provider 压力测试，也没有进入正式 8000 服务。
- 由于 TASK-017E-2 已留下累计60次真实调用，主预算持久化为 EXHAUSTED；后续必须由人工明确开启新的预算任务，不能重启脚本自动恢复40次额度。
