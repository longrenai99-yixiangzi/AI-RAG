# Provider Reliability Report

> TASK-017E-2 仅在 Shadow 环境执行。未修改 Retriever、BM25/Dense/RRF、Evidence Selection、Scope Guard、Query Page Probe、Policy Facet、Preflight、OPTION_QUERY、Fact Path、正式 Qdrant 或 8000 服务。
> 本任务只验证 Provider 可靠性；Provider 故障不会被转换成 NO_EVIDENCE、STRUCTURE_INVALID 或 ANSWER_FAILURE。

## 1. Provider Failure Taxonomy

- 统一分类：`['RATE_LIMITED', 'REQUEST_TIMEOUT', 'CONNECT_TIMEOUT', 'CONNECTION_ERROR', 'SERVER_5XX', 'EMPTY_RESPONSE', 'AUTHENTICATION_ERROR', 'PERMISSION_ERROR', 'INVALID_REQUEST', 'MODEL_UNAVAILABLE', 'UNKNOWN_PROVIDER_ERROR']`。
- 400/401/403/404模型不存在/请求Schema错误默认不重试；429、408、连接/读取超时、连接错误、502/503/504和明确临时5xx有限重试。
- 总尝试次数最多3次；Retry-After优先，等待时间设有上限；日志只保存脱敏错误信息。
- 分层超时：connect_timeout=15s，read_timeout=60s，total_timeout=75s；本地 Fault Injection 将等待缩短为毫秒级，但保留相同重试语义。

## 2. Fault Injection

| 场景 | Attempts | Retry delays | Final Provider Status | Final Answer Status | Result |
|---|---:|---|---|---|---|
| FI-429-SUCCESS | 2 | `[0.001]` | `SUCCESS` | `GENERATION_READY` | PASS |
| FI-429-FAIL | 3 | `[0.001, 0.001]` | `RATE_LIMITED` | `PROVIDER_TEMPORARY_FAILURE` | PASS |
| FI-CONNECT-TIMEOUT-SUCCESS | 2 | `[0.001]` | `SUCCESS` | `GENERATION_READY` | PASS |
| FI-READ-TIMEOUT-3RD | 3 | `[0.001, 0.002]` | `SUCCESS` | `GENERATION_READY` | PASS |
| FI-502-SUCCESS | 2 | `[0.001]` | `SUCCESS` | `GENERATION_READY` | PASS |
| FI-503-FAIL | 3 | `[0.001, 0.002]` | `SERVER_5XX` | `PROVIDER_TEMPORARY_FAILURE` | PASS |
| FI-504-SUCCESS | 2 | `[0.001]` | `SUCCESS` | `GENERATION_READY` | PASS |
| FI-401-NO-RETRY | 1 | `[]` | `AUTHENTICATION_ERROR` | `PROVIDER_PERMANENT_FAILURE` | PASS |
| FI-403-NO-RETRY | 1 | `[]` | `PERMISSION_ERROR` | `PROVIDER_PERMANENT_FAILURE` | PASS |
| FI-400-NO-RETRY | 1 | `[]` | `INVALID_REQUEST` | `PROVIDER_PERMANENT_FAILURE` | PASS |
| FI-EMPTY-SUCCESS | 2 | `[0.001]` | `SUCCESS` | `GENERATION_READY` | PASS |

- Fault Injection：`11/11` 通过。
- 401/403/400均为单次尝试；429/Timeout/502/503/504按有限重试执行；没有场景超过3次。

## 3. Live Provider Replay

- Provider可用配置：`True`；未记录Key内容。
- 真实HTTP请求上限：`40`；实际使用：`40`；剩余：`0`。
- 每题目标回放：`10` 次；达到预算即停止，不补发请求。
- 每次回放固定复用同一 Question、Evidence Bundle、Prompt 快照和 Allowed Evidence IDs；没有重新检索、换Evidence或修改Claim。

| Question | Preflight | Evidence | Replay Rows | Final Provider Status |
|---|---|---|---:|---|
| BA-001 | `READY_FOR_GENERATION` | `SELECTED` | 10 | `['SERVER_5XX']` |
| BA-007 | `READY_FOR_GENERATION` | `SELECTED` | 4 | `['SERVER_5XX']` |

### Live 指标

| 指标 | 值 |
|---|---:|
| First Attempt Success Rate | `0.0` |
| Retry Recovery Rate | `0.0` |
| Final Success Rate | `0.0` |
| Temporary Failure Rate | `1.0` |
| Permanent Failure Rate | `0.0` |
| Average Attempts | `2.857` |
| P50 Latency | `18377` ms |
| P95 Latency | `18615` ms |
| Provider Requests | `40` |

Provider失败时保存 `retrieval_status`、`evidence_status` 和 `preflight_status`；最终状态只使用 `PROVIDER_TEMPORARY_FAILURE` 或 `PROVIDER_PERMANENT_FAILURE`，不降级为知识链路失败。成功记录为 `GENERATION_READY`，不代表本任务重新完成 Answer Schema/Claim 质量验收。

## 4. BA 回归与确定性路径兼容性

本次对 BA-001/BA-007 做了无Provider请求的上下文快照并进行真实 Provider 回放；BA-003/BA-005保持既有 Preflight 安全结果，未绕过闸门。BA-002/BA-004/BA-008/BA-010仅读取既有确定性结果。

| 问题 | 既有结果状态 | 既有Provider调用 |
|---|---|---:|
| BA-001 | `GENERATED` | `1` |
| BA-003 | `NO_EVIDENCE` | `0` |
| BA-005 | `NO_EVIDENCE` | `0` |
| BA-007 | `GENERATED` | `1` |
| BA-002 | `GENERATED` | `0` |
| BA-004 | `GENERATED` | `0` |
| BA-008 | `GENERATED` | `0` |
| BA-010 | `FACT_RESULT` | `0` |

- Deterministic Formula Renderer、OPTION deterministic renderer、Direct deterministic answer和Fact Answer Path不依赖本次 Provider；本任务没有重跑或修改它们。

## 5. 隔离结论

- 临时故障：只在有限重试后标记 `PROVIDER_TEMPORARY_FAILURE`，保留检索和证据状态。
- 永久故障：标记 `PROVIDER_PERMANENT_FAILURE`，后续动作应为检查凭据、模型权限、Endpoint或请求Schema，而不是提示“知识库没有答案”。
- 真实 Provider 的成功率受当前服务状态影响；Fault Injection 是本次 Retry 策略的确定性验收依据。
- 详细逐次遥测位于 `evaluation/provider_reliability/provider_telemetry.jsonl`，只含安全元数据，不含 API Key、Authorization Header 或密码。
- 执行审计：首次诊断因 Shadow 脱敏正则自身错误中止，但已经发出20次真实请求；修复后最终回放使用40次，故本次任务累计实际真实请求为60次，超过单次建议40次预算。该超限已停止，不再追加真实调用；后续应先修复预算持久化/跨运行计数，再进行 Live Test。
