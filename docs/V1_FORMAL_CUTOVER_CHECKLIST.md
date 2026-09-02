# V1.0 Formal Cutover Checklist

> TASK-018 仅建立检查表，不执行 Cutover。

| 类别 | 检查项 | 当前状态 | 正式切换前要求 | 证据/负责人 |
|---|---|---|---|---|
| Root | Root-001 范围与只读权限 | READY_WITH_LIMITATION | 确认长期 owner、刷新和撤销机制 | `docs/KNOWLEDGE_SOURCE_ROOT_POLICY.md` |
| Root | Root-002 审批 | BLOCKED | 完成目录、保密边界和正式读取审批 | 二公司技术部/业务负责人 |
| Root | Root-003 审批 | BLOCKED | 完成独立审批，不自动加入 | 设计支持中心/业务负责人 |
| Retrieval | Shadow → Formal Retriever 配置迁移 | NOT_STARTED | 明确回退、灰度、版本和回滚 | Retrieval owner |
| Index | Shadow → Formal Qdrant 迁移 | NOT_STARTED | 独立备份、校验点数、回滚快照 | Index owner |
| Provider | Health、认证、限流和预算 | BLOCKED | 恢复服务后做小规模验证，保留 Budget/Circuit | Provider owner |
| Citation | Citation Audit View | NOT_STARTED | 分离 retrieval_evidence 与 fact_authority_source | Product/QA |
| OCR | OCR 策略 | READY_WITH_LIMITATION | 处理 2 个低文本 PDF，定义失败隔离和重试 | Document owner |
| Metadata | 质量与版本 | READY_WITH_LIMITATION | 修复 front matter、补齐分类、保留 review 状态 | Governance owner |
| Permissions | 多人权限和数据隔离 | NOT_STARTED | 角色、白名单、审计和撤销 | Security owner |
| Observability | 日志、指标、隐私 | READY_WITH_LIMITATION | 集中化 Trace/Audit、保留脱敏规则 | SRE/QA |
| Backup | 备份与恢复 | NOT_STARTED | SQLite/Qdrant/配置/Artifact 可恢复演练 | Operations |
| Rollback | 旧链路回退 | NOT_STARTED | 可一键回退旧 Retriever/Answer 链 | Release owner |
| UAT | 业务验收 | NOT_STARTED | BA-001～BA-010 和扩展问题通过业务评分 | Business owner |
| Cutover | 正式 8000 切换 | BLOCKED | 所有 P1 项关闭并获得发布批准 | Release approval |

## Cutover Gate

只有以下条件全部满足，才允许进入正式切换评审：

1. Provider 依赖型答案不再处于持续失败；
2. Root 审批、权限、备份和回滚完成；
3. Citation Audit View 能区分普通检索证据与事实权威来源；
4. OCR、Metadata、SQLite/Qdrant 一致性问题有闭环；
5. 业务 UAT 明确通过。

