# KNOWLEDGE GROWTH SCHEMA V1

Growth Candidate 生命周期：`PROPOSED → REVIEWED → APPROVED → PUBLISHED`，或 `REJECTED / DEFERRED`。本版本只创建 `PROPOSED`。

核心字段：`candidate_id`、`candidate_fingerprint`、`source_query_id`、`question`、`failure_type`、`growth_type`、`priority`、`reason`、`current_answer_status`、受影响的 Document/Section/Evidence ID、缺口诊断、建议动作、`evidence_snapshot`、治理与审核状态、审核人/意见、来源标识、回归问题 ID 和 `schema_version`。

来源标识：`OWNER_CONFIRMED`、`SOURCE_DERIVED`、`AI_PROPOSED` 必须区分；本任务生成的候选为 `AI_PROPOSED`，其证据快照为 `SOURCE_DERIVED`。
