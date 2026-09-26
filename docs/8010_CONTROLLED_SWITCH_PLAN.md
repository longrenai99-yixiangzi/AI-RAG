# 8010 Controlled Switch Plan（GATED）

> 历史快照，非当前运行状态。该文档中的“V2.6.2 已切为 8010 主答”已被后续回滚覆盖。当前配置为 `V1_PRIMARY`；截至 2026-09-26 19:48 +08，8010 与 8000 均无监听进程。当前门禁请以 `final_release_gate.json` 和最新交接记录为准。

历史状态：`V2.6.2` 曾按当时授权切换为 8010 常驻主答；即时 Smoke 与 10 题 Canary 曾通过；8000 保持关闭。

前置条件：

- Owner Source Version Gate：必须 5/5 `APPROVED`
- Live Shadow Gate：必须 PASS
- Rollback Drill：已 PASS（8010-only V1 → V2.6.2 → V1）
- Candidate Integrity：必须 PASS
- 用户明确授权“允许切换 8010”：已确认，仅限 8010，不包含 8000。

历史切换方案：8010 候选主答仅在满足前置条件并得到授权后使用；关键失败时按 Rollback Plan 恢复 V1。不得据本历史快照判断当前服务正在运行。

获授权后的最小切换顺序：

1. 保存 V1 runtime snapshot。
2. 校验 V2.5 candidate/source/index/embedding/config hash 与已通过评测的一致性。
3. 以 versioned pointer 将 active runtime 指向 V2.5。
4. 立即执行固定 Smoke Query、health、search、QA、citation、diagnostics。
5. 任一关键项失败，立即按回滚计划恢复 V1。
6. Smoke 通过后进入 Canary，不在 Canary 阶段调整 Retrieval 参数。
