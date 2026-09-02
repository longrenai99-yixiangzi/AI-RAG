# KNOWLEDGE GROWTH REVIEW WORKFLOW V1

1. 系统仅创建 `PROPOSED` 候选，并记录证据、失败类型与回归问题。
2. 审核人选择 `APPROVE`、`REJECT`、`DEFER` 或 `MERGE`，填写审核意见和已批准动作。
3. 审核记录字段：`reviewer`、`review_time`、`decision`、`comment`、`approved_action`；decision 仅可为 `APPROVE`、`REJECT`、`DEFER` 或 `MERGE`。
4. 只有 `APPROVED` 候选才可进入未来的受控知识发布流程；本版本不发布、不改知识库、不改正式索引。
5. 发布后必须回放 `regression_question_ids`，验证原问题是否真正解决。

不同候选的审核重点：来源范围缺口需确认知识根和所有者；冲突候选需确认版本、时间和指标口径；字段不足候选需确认应补充的正式表格字段；检索候选需先完成 Shadow 诊断，禁止直接改正式 Retriever。
