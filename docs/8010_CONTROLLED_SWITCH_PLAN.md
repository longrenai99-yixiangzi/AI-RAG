# 8010 Controlled Switch Plan（GATED）

状态：`BLOCKED`，尚未获得执行授权。

前置条件：

- Owner Source Version Gate：必须 5/5 `APPROVED`
- Live Shadow Gate：必须 PASS
- Rollback Drill：必须 PASS
- Candidate Integrity：必须 PASS
- 用户明确授权“允许切换 8010”

当前不执行任何切换。8010 保持 V1 Primary，8000 保持 OFF。

获授权后的最小切换顺序：

1. 保存 V1 runtime snapshot。
2. 校验 V2.5 candidate/source/index/embedding/config hash 与已通过评测的一致性。
3. 以 versioned pointer 将 active runtime 指向 V2.5。
4. 立即执行固定 Smoke Query、health、search、QA、citation、diagnostics。
5. 任一关键项失败，立即按回滚计划恢复 V1。
6. Smoke 通过后进入 Canary，不在 Canary 阶段调整 Retrieval 参数。
