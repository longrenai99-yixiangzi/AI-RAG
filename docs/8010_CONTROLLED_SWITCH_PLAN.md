# 8010 Controlled Switch Plan（GATED）

状态：`V2.6.2` 已按授权切换为 8010 常驻主答；即时 Smoke 与 10 题 Canary 已通过。8000 仍关闭。

前置条件：

- Owner Source Version Gate：必须 5/5 `APPROVED`
- Live Shadow Gate：必须 PASS
- Rollback Drill：已 PASS（8010-only V1 → V2.6.2 → V1）
- Candidate Integrity：必须 PASS
- 用户明确授权“允许切换 8010”：已确认，仅限 8010，不包含 8000。

当前运行状态：8010 为 `V2.6.2` Primary，8000 保持 OFF；关键失败时按 Rollback Plan 恢复 V1。

获授权后的最小切换顺序：

1. 保存 V1 runtime snapshot。
2. 校验 V2.5 candidate/source/index/embedding/config hash 与已通过评测的一致性。
3. 以 versioned pointer 将 active runtime 指向 V2.5。
4. 立即执行固定 Smoke Query、health、search、QA、citation、diagnostics。
5. 任一关键项失败，立即按回滚计划恢复 V1。
6. Smoke 通过后进入 Canary，不在 Canary 阶段调整 Retrieval 参数。
