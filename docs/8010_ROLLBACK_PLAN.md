# 8010 Rollback Plan（GATED）

状态：真实 `V1 → V2.6.2 → V1` 演练已于 2026-09-16 在 8010 完成并通过。候选三题 Smoke 均为 `ANSWERED` 且有引用，V1 配置快照已恢复；8000 未启动、未写入。详见 `evaluation/knowledge_os_v2_6/v2_6_2_8010_rollback_drill.json`。

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
