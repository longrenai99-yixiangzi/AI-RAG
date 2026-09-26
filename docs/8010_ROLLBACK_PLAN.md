# 8010 Rollback Plan（GATED）

状态：真实 `V1 → V2.6.2 → V1` 演练已于 2026-09-16 在 8010 完成并通过。候选三题 Smoke 均为 `ANSWERED` 且有引用，V1 配置快照已恢复；8000 未启动、未写入。详见 `evaluation/knowledge_os_v2_6/v2_6_2_8010_rollback_drill.json`。

最新候选重验（2026-09-26）：候选 `823d3b32…a74b73a` 的 8010 T6 `PASS`，3/3 Smoke 和 10/10 Canary 均 `ANSWERED`；V1 恢复 Smoke 为 1 `ANSWERED`、2 `PARTIAL_ANSWER`。配置起止 SHA-256 均为 `a09ec730071d9b77909bdfbf2db73eb90682e63e2cede4d2f522a9384188f680`，8000 未监听。V1 恢复 Smoke 仅证明恢复路径可用，不代表 V1 答案质量全通过；T6 不等于 8000 Release。该次演练后 8010/8000 服务进程均已停止，见当前 [交接状态](V2_6_2_HANDOFF_20260920.md)。

回滚原则：只恢复 versioned config、versioned index pointer 和 V1 runtime package，不重新 Parse、Chunk、Embedding、建 Index，也不人工改数据库。

触发器：

- 服务无法启动
- 连续 Runtime Error
- Index Load Failure
- Citation 失效
- 错误 Source Version
- 明显跨项目/跨年份串答
- 无依据回答
- Critical Smoke Failure

恢复顺序：

1. 停止 V2.5 active pointer。
2. 恢复 V1 config、V1 index pointer、V1 runtime package。
3. 确认 V1 index hash 与 config hash 等于 T00 snapshot。
4. 运行同一组固定 Smoke Queries。
5. 记录无数据损坏、无正式 8000 影响后关闭演练。
