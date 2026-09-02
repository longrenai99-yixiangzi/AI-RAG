# Business Gold V2 Report

> TASK-020A.1：只对齐最新已验收 Artifact 并生成 Candidate Gold Review Pack；不运行新的 Fresh Retrieval，不调用 LLM，不修改 Retriever、Router、Document Engine、Qdrant 或 8000。

## 1. Artifact Reconciliation

- `historical_fresh_run_available`：`true`（TASK-017D 已存在 Fresh Run）。
- `task020a_current_input_fresh_run`：`false`（当前 020A 输入包没有 fresh_run=true）。
- 当前输入无 Fresh Run 不等于项目历史没有 Fresh Run。
- 早期 `BUSINESS_QUERY_FAILURE_AUDIT` 仅保留为 historical baseline，不能覆盖后期验收结果。

## 2. Candidate Gold Card 汇总

| BA | Latest System Status | Truth Source | Runtime Answerability | Governance | Owner |
|---|---|---|---|---|---|
| BA-001 | `EVIDENCE_READY_PROVIDER_TEMPORARY_FAILURE` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `PENDING_APPROVAL` | `UNCONFIRMED` |
| BA-002 | `GENERATED_WITH_SEMANTIC_MAPPING_UNCONFIRMED` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `PENDING_APPROVAL` | `UNCONFIRMED` |
| BA-003 | `SOURCE_BODY_NOT_IN_APPROVED_SCOPE` | `KNOWN_OUT_OF_SCOPE` | `SOURCE_SCOPE_MISSING` | `OUT_OF_SCOPE` | `UNCONFIRMED` |
| BA-004 | `GENERATED_OPTION_QUERY` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `APPROVED` | `UNCONFIRMED` |
| BA-005 | `AUTHORITY_INSUFFICIENT` | `UNKNOWN` | `AUTHORITY_INSUFFICIENT` | `APPROVED` | `UNCONFIRMED` |
| BA-006 | `DIRECT_FACT_NO_SAME_SCOPE_EVIDENCE` | `KNOWN_OUT_OF_SCOPE` | `SOURCE_SCOPE_MISSING` | `OUT_OF_SCOPE` | `UNCONFIRMED` |
| BA-007 | `GENERATED_TWO_VALID_POLICY_FACETS` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `PENDING_APPROVAL` | `UNCONFIRMED` |
| BA-008 | `GENERATED_COMPANY_DIRECT_FACT` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `APPROVED` | `UNCONFIRMED` |
| BA-009 | `SOURCE_SCOPE_MISSING` | `KNOWN_OUT_OF_SCOPE` | `SOURCE_SCOPE_MISSING` | `OUT_OF_SCOPE` | `UNCONFIRMED` |
| BA-010 | `FACT_RESULT_VALIDATED` | `KNOWN_IN_SCOPE` | `ANSWERABLE` | `PENDING_APPROVAL` | `UNCONFIRMED` |

## 3. Candidate Failure Atlas

| BA | Candidate Failure | Final? |
|---|---|---|
| BA-001 | `GENERATION_FAILURE` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-002 | `SEMANTIC_MAPPING_UNCONFIRMED` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-003 | `SOURCE_MISSING` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-004 | `NONE_OR_PENDING_OWNER_REVIEW` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-005 | `AUTHORITY_FAILURE` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-006 | `SOURCE_MISSING` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-007 | `NONE_OR_PENDING_OWNER_REVIEW` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-008 | `NONE_OR_PENDING_OWNER_REVIEW` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-009 | `SOURCE_MISSING` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |
| BA-010 | `NONE_OR_PENDING_OWNER_REVIEW` | No — OWNER CONFIRMED Gold + Controlled Fresh Run required |

## 4. 关键对账结论

- BA-002：正式手册存在两个公式；“设计效益增量”与正式指标的映射仍未确认。
- BA-004：Sheet1 第89行的传统镀锌钢管与 PVC-C 两方案是候选事实来源。
- BA-005：当前不是普通 Evidence Miss，而是正式图审依据不足。
- BA-006、BA-009：目标正文处于当前批准范围外，运行时应安全拒答。
- BA-007：公司设计管理与局级深化设计是两个已验证 Facet，Root-002 仍为 PENDING_APPROVAL。
- BA-008：公司级年度金额为约4.45亿元；不得以项目金额替代。
- BA-010：统计依据是价值创造 Sheet 行4-87及业务确认的利润>0规则，不是检索上下文或 Root-001 登记页。

## 5. 输出

- `evaluation/business_gold_v2/latest_artifact_reconciliation.json`
- `evaluation/business_gold_v2/candidate_gold_manifest.json`
- `evaluation/business_gold_v2/candidate_failure_atlas.json`
- `evaluation/business_gold_v2/gold_review_queue.json`
- `docs/BUSINESS_GOLD_OWNER_REVIEW_SHEET.md`

## 6. 停止点

所有 Candidate Gold Card 均为 `owner_confirmation=UNCONFIRMED`。本任务未生成 final_failure_atlas，未进入 TASK-020B。

## TASK-020A.2.1 忠实性与范围修正

- Owner Source 记录：10/10；其中物理来源忠实性已确认 9/10。
- Gold Location：CONFIRMED 8、PARTIAL 2、UNRESOLVED 0；合计 10/10。
- BA-006 的工作计划仅作为 Supporting Source；责任状正文尚未定位。
- BA-007 Gold Claim 已收窄为“一、设计示范工程实施要求”四项，其他示范类型仅为 Related Context。
- BA-010 继续保持 PARTIAL，不继承旧 XLSX 的统计数字。
- `owner_confirmation` 仍全部为 `UNCONFIRMED`；Source Confirmation 不等于最终 Gold Confirmation。
- `Root-002` 文件治理状态继续保留 `PENDING_APPROVAL`。
- 不生成 final_failure_atlas，不进入 TASK-020B。

## TASK-020A.2.2 责任状与来源血缘闭环

- BA-006：责任状精确来源已确认，Table 1 Row 22 为不少于40个项目图形文件；工作计划500个保持 Supporting Source，并记录 EVIDENCE_CONFLICT。
- BA-010：DOCX 34条与 XLSX 80条判定为 `LINEAGE_PARTIAL`，不继承37条。
- Gold Location：CONFIRMED 9、PARTIAL 1、UNRESOLVED 0；合计 10/10。
- owner_confirmation 仍全部为 UNCONFIRMED；未生成 FINAL_GOLD、final_failure_atlas，不进入 TASK-020B。

## TASK-020A.3 受控 Fresh Run

- Owner Approved Gold 已冻结：BA-001～009 Full、BA-010 Partial。
- Fresh Run：10题；Provider HTTP Requests=0。
- Primary Failure：`{"NO_FAILURE": 1, "DOCUMENT_MISSED": 2, "SOURCE_SCOPE_MISSING": 5, "SECTION_MISSED": 1, "SOURCE_LINEAGE_FAILURE": 1}`。
- 已生成 Final Failure Atlas、Baseline Metrics 和 TASK-020B Input Requirements。
- TASK-020A 正式结束；不自动进入 TASK-020B。
