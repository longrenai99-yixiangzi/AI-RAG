# AI设计管理知识库 V1.0 Internal Trial Readiness Review

> TASK-018：统一审查当前 Ingestion、Retrieval、Router、Answer Engine、Fact Path、Scope Guard、Query Page Rescue、Policy Scope、Preflight、Citation、Provider Reliability、Runtime Guard 和 Knowledge Governance。
>
> 本任务只读取既有代码和 Shadow Artifact；未重新索引、重新 Embedding、重新调用 Provider、创建新预算、扫描新的 Root-002 目录或执行正式 Cutover。

## 1. 冻结基线

- Root-001：`D:\设计管理`，当前正式知识基线，保持只读。
- Root-002：`D:\工作\二公司技术部`，只能称为 frozen Shadow scope，`governance=PENDING_APPROVAL`。
- Root-003：`D:\工作\设计支持中心`，`PENDING_APPROVAL`，未自动加入。
- 正式 8000 服务尚未切换到新 Shadow Pipeline；新 RAG/Answer 能力仍属于 Shadow。

## 2. Corpus 与处理基线

| 指标 | 已有结果 | 评审含义 |
|---|---:|---|
| Root-001 资产文件 | 710 | 资产总量，不等于已进入 Shadow 的可处理文档 |
| Shadow Document | 498 | 当前支持格式的处理范围 |
| Shadow Chunk | 4747 | BGE-M3 Shadow 索引输入 |
| Metadata 完整 Chunk | 4747/4747 | 当前 Shadow 覆盖 |
| location 有效 Chunk | 4747/4747 | 当前 Shadow 覆盖 |
| needs_ocr | 2 | 低文本图像型 PDF，仍需人工/OCR策略处理 |
| front_matter_error | 1 | 模板文件解析异常 |
| SQLite documents/chunks | 不可确认 | V1 data 缺少 `index.sqlite3`，不能解释为 0 |
| Qdrant collection | 1 | `design_management_chunks` 正式目录存在，但不代表状态一致 |

Markdown 是数量第一优先级；PPT/PPTX 数量较少但约占 1.14 GiB，并存在超大文件，内部试用应保留大文件风险提示。

## 3. V1_READINESS_SCORECARD

完整字段和证据见 `evaluation/v1_internal_trial_readiness/readiness_scorecard.json`。

| 评审项 | 状态 | 关键证据 | 内部试用影响 |
|---|---|---|---|
| Corpus Readiness | READY_WITH_LIMITATION | 710 资产；498 Document/4747 Chunk | 可控只读试用，显示 OCR/源覆盖边界 |
| Parsing / Chunking Readiness | READY_WITH_LIMITATION | 五类样本 78 SourceBlock/164 Chunk；定位 164/164 | 支持格式可审查，异常文件不隐藏 |
| Retrieval Readiness | READY_WITH_LIMITATION | Hybrid+Reranker Recall@5=69% | 可做证据检索，不等于答案正确 |
| Query Routing Readiness | READY_WITH_LIMITATION | Router 40/40；False Fact/Claim=0 | 可控试用，歧义问题保留不可用状态 |
| Evidence Selection Readiness | READY_WITH_LIMITATION | GOLD_IN_ROOT 目标文件命中 2/2；位置完整率100% | 可预览证据，Root-002仍不得正式发布 |
| Answer Generation Readiness | BLOCKED | 100题仅32 GENERATED；当前 Provider 成功率0% | 禁用 Provider-dependent 普通答案 |
| Deterministic Fact Readiness | READY | BA-010 10/10；80/37/43；BA-004 20/20 | 可开放确定性路径 |
| Citation / Traceability Readiness | READY_WITH_LIMITATION | Citation检索完整率100%；BA-010 10/10 | 需人工审查，正式 Audit View 未完成 |
| Safety / Refusal Readiness | READY_WITH_LIMITATION | Preflight 7 Ready/2 Source Gap/1 Authority Gap；Unsafe=0 | 可开放安全拒答和状态诊断 |
| Provider Runtime Readiness | BLOCKED | Fault 11/11、Guard通过；真实成功率0%；预算 EXHAUSTED | 只能 Degraded Trial |
| Knowledge Governance Readiness | READY_WITH_LIMITATION | Root-001 active；Root-002/003 pending | Root-002只能作为标注过的 Shadow 证据 |
| Observability / Audit Readiness | READY_WITH_LIMITATION | Trace/Telemetry Artifact齐备 | 工程可审计，产品化 Audit View不足 |

## 4. Business Acceptance Matrix

完整字段见 `evaluation/v1_internal_trial_readiness/business_acceptance_matrix.json`。

| 问题 | Route | Evidence State | Final Status | Provider依赖 | 内部试用建议 |
|---|---|---|---|---|---|
| BA-001 设计任务书内容 | CLAIM | 已选证据，案例/模板混合风险 | GENERATED | 是 | Provider不可用时仅证据预览 |
| BA-002 设计效益增量计算 | CLAIM/公式 | 正式公式存在，术语边界未确认 | GENERATED | 否 | 开放确定性公式 |
| BA-003 厂房方案比选专业 | CLAIM | SOURCE_SCOPE_MISSING | NO_EVIDENCE | 否 | 仅安全拒答 |
| BA-004 喷淋管材方案 | OPTION | 两种方案证据正确 | GENERATED | 否 | 开放确定性 OPTION |
| BA-005 集电线路图审要点 | CLAIM | AUTHORITY_INSUFFICIENT | NO_EVIDENCE | 否 | 仅安全拒答 |
| BA-006 DOP上传数量 | DIRECT_FACT/CLAIM | 责任状正文/数量缺口 | NO_EVIDENCE | 否 | 仅安全拒答 |
| BA-007 示范项目打造要求 | CLAIM | 两个真实局部 Policy Facet 已 Ground | GENERATED | 是 | Provider不可用时局部证据预览 |
| BA-008 公司设计创效金额 | DIRECT_FACT | 公司 Scope Guard 有效 | GENERATED | 否 | 开放确定性 Direct Fact |
| BA-009 4月EPC督办 | CLAIM | SOURCE_SCOPE_MISSING | NO_EVIDENCE | 否 | 仅安全拒答 |
| BA-010 星谷价值创造清单 | FACT | 确认结构化事实链 | FACT_RESULT | 否 | 开放确定性 Fact Path |

关键口径：BA-002 正式公式存在，但 `设计效益增量` 与正式指标的语义映射仍有边界；BA-010 的 43 条利润为空/未判定，不等于无效益。

## 5. Provider 与降级模式

Provider 架构层面具备：

- Retry Policy：Fault Injection 11/11；
- Failure Isolation：临时/永久错误分离；
- Circuit Breaker：9/9；
- Budget Guard：跨重启和耗尽保护通过。

但当前真实 Provider 最近成功率为 0%，返回持续 502；主预算为 `max=40, used=60, remaining=0, EXHAUSTED`。因此 Provider 不能评为 READY。

内部试用采用三种状态：

1. `NORMAL ANSWER`：仅在 Provider、Schema、Claim、Citation 均通过时显示；
2. `SAFE REFUSAL`：来源/权威/证据不足时显示；
3. `GENERATION SERVICE UNAVAILABLE`：Provider、Circuit 或预算保护触发时显示，并保留 Evidence Preview。

## 6. Knowledge Source Governance Matrix

| Root | Path | Owner | Governance | Allowed in Trial | Allowed in Formal | Refresh/Write |
|---|---|---|---|---|---|---|
| Root-001 | `D:\设计管理` | 设计管理知识库维护方 | APPROVED_ACTIVE | 是，只读 | 待正式发布审批 | 只读/禁止写回 |
| Root-002 | `D:\工作\二公司技术部` | 二公司技术部/设计与技术管理责任部门 | PENDING_APPROVAL | 仅冻结 Shadow 证据 | 否 | 待审批/禁止写回 |
| Root-003 | `D:\工作\设计支持中心` | 设计支持中心 | PENDING_APPROVAL | 否，除非后续单独批准 | 否 | 待审批/禁止写回 |

## 7. Trial Blockers

### P0 Trial Blocker

- Provider-dependent Claim Answer 当前不可用。解决方式是关闭普通生成答案，开放证据预览、确定性路径和安全拒答。

### P1 Formal Cutover Blockers

- 正式 8000 尚未切换；
- Root-002/Root-003 未完成正式审批；
- Provider 健康、预算和熔断保护尚未恢复上线状态；
- 缺少区分 retrieval_evidence 与 fact_authority_source 的 Citation Audit View；
- OCR、front matter、legacy format、SQLite/Qdrant 一致性未闭环；
- 权限、备份、回滚和 UAT 未完成。

### P2 Improvement

- 提升长尾 Retrieval Recall 和 Metadata 质量；
- 补齐 BA-003/006/009 业务源闭环；
- 将文件型 Shadow Trace 产品化为 Audit View。

## 8. Q1–Q5 最终判断

- Q1：具备小范围内部试用技术基础，但仅限受控只读/Shadow 模式。
- Q2：可以采用 Degraded Trial Mode，Provider-dependent Claim Answer 必须关闭。
- Q3：可试用 Root-001 证据检索、Citation、确定性 Formula/OPTION/Direct Fact/Fact Path 和 Safe Refusal。
- Q4：必须关闭正式 Root-002 使用、新 Root 自动导入、自动 OCR 生产化、正式 8000 切换及 Provider 依赖普通生成。
- Q5：正式切换前还缺 Provider 健康、Root 审批、正式链路迁移、Audit View、OCR/一致性、权限、备份、回滚和 UAT。

## 9. Overall Readiness

**CONDITIONAL_GO**

### Trial Ready Capabilities

- Root-001 只读 Evidence Retrieval；
- Evidence/Citation Preview；
- BA-002 确定性公式；
- BA-004 OPTION；
- BA-008 Direct Fact；
- BA-010 Fact Result；
- Safe Refusal 和状态诊断。

### Trial Disabled Capabilities

- Provider-dependent 普通 Claim Answer；
- Root-002 正式使用；
- Root-003 和新 Root 自动导入；
- 自动 OCR 生产化；
- 正式 8000 切换；
- 自动写回和正式多人权限。

### Recommended Next Step

按 [V1_INTERNAL_TRIAL_CONDITIONS.md](D:\AI智能体\AI设计管理RAG-V1\docs\V1_INTERNAL_TRIAL_CONDITIONS.md) 启动小范围 Degraded Trial；不要继续单点算法优化，也不要执行正式 Cutover。

