# VERIFIED ANSWER SCHEMA V2

`VerifiedAnswer` 仅由一次新鲜运行构建的 `VerifiedEvidenceBundle` 生成。

- `answer_status`：`ANSWERED`、`PARTIAL_ANSWER`、`CONFLICTING_ANSWER`、`INSUFFICIENT_EVIDENCE`、`SOURCE_SCOPE_MISSING`、`LINEAGE_BLOCKED` 或 `CITATION_INVALID`。
- `claims[]`：每条业务断言包含 `claim_id`、`claim_text`、`claim_type`、`subquestion_id`、`evidence_ids` 与 `citation_ids`。
- `claim_evidence_map[]`：Claim 到 Evidence 的唯一映射；DIRECT Claim 只能绑定 DIRECT Evidence。
- `citations[]`：由代码生成，保留 `document_id`、文件名、来源路径与页码/表格/工作表/行号等位置字段。
- `answer_trace`：记录 Bundle 状态、校验错误与 `gold_runtime_injection=0`。

不调用 Provider；不由模型补事实、计算数值或裁决冲突。
