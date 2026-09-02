# Policy Facet Grounding Report

> TASK-017E-1.2.1：仅在 Shadow 环境执行 Candidate-Level Facet Grounding；未修改 Retriever、Router、Preflight Safety Gate、Scope Guard、Query Page Probe、OPTION_QUERY、BA-010 Fact Path、正式 Qdrant 或 8000 服务。
> Root-002 在本报告中统一称为 frozen Shadow scope，governance=PENDING_APPROVAL，不等同正式授权。

## 1. 原 1.2 误分类原因

原实现将文件名/全文信号投射到当前 Chunk，并在组织层级与示范项目类型之间进行组合，可能生成当前 Chunk 没有局部证据支持的 Facet。此次改为每个 Candidate 独立检测，Facet 集合只取真实 Candidate-Level Grounding 结果。

## 2. Cartesian Product 检查

- 不再先分别收集 organization_levels 与 demonstration_types 再补齐组合。
- 本次真实 valid_candidate_facets：`['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`
- 全局真实有效 Facet（含与本题无关的主题）：`['COMPANY/DEMONSTRATION_PROJECT/SMART_CONSTRUCTION/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`；只有与当前 Query 主题相关的 Facet 才进入 Coverage。
- Invalid Facet 不进入 Coverage denominator：`97` 条 Candidate-level invalid/weak 记录。

## 3. BA-007 Candidate-Level Facet Grounding

| Facet | Candidate Count | Top Rank | Top File | Top Location |
|---|---:|---:|---|---|
| `GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` | 1 | 34 | 关于印发中建三局2026年设计与技术工作计划的通知.pdf | `{'page': 4, 'text_length': 960}` |

### Grounding Validator 摘要

| Status | Count |
|---|---:|
| UNSUPPORTED_FACET | 84 |
| VALID_FACET | 3 |
| WEAK_FACET | 13 |

### Valid / Invalid Facets

- valid_candidate_facets：`['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`
- invalid_candidate_facets：`97` 条，详见 `BA-007.json` 的 `invalid_candidate_facets`。

## 4. BA-007 Before / After Coverage

| State | Selected Facets | Missing Valid Facets | Coverage Complete |
|---|---|---|---|
| Before | `[]` | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `False` |
| After | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `[]` | `True` |

## 5. BA-007 正确 Evidence 与最终答案

- query_scope_specificity：`UNSPECIFIED_SCOPE`
- organization_level：`['GROUP']`
- demonstration_type：`['DETAILED_DESIGN']`
- semantic_scope_status：`QUERY_SCOPE_UNSPECIFIED_PRESERVED`
- upstream_scope_diagnostic：`{'organization_level': ['局级', '二公司'], 'demonstration_type': ['设计管理示范项目', '深化设计示范项目'], 'semantic_scope_status': 'QUERY_SCOPE_UNSPECIFIED_PRESERVED'}`
- business_expected_facets：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`
- missing_business_facets：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']`
- business_answer_completeness：`PARTIAL_EVIDENCE`

最终答案：

当前问题未限定管理层级和示范项目类型；目前仅找到以下一类通过局部正文校验的 Policy Facet，其他范围暂未确认：

1. GROUP/DETAILED_DESIGN：力，动态配置人员到 项目开展设计与深化设计管理，年底对中心建设情况进行自查。 三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控 清单，打造不少于1 个深化设计示范项目，以点带面，全面提升 深化设计管理能力。四是要制定认质认样管理流程及配套工具， 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15: 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-0 [S1]

以上属于不同管理层级或示范项目类型，不能在未限定范围时合并成同一条要求。

### Atomic Claims

- `C1` / `POLICY_FACET` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / evidence=`S1` / support_span：力，动态配置人员到 项目开展设计与深化设计管理，年底对中心建设情况进行自查。 三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控 清单，打造不少于1 个深化设计示范项目，以点带面，全面提升 深化设计管理能力。四是要制定认质认样管理流程及配套工具， 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15: 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-09 15:59 刘畅 第二建设公司 2026-06-0
- `C2` / `SCOPE_BOUNDARY` / facet=`None` / evidence=`S1` / support_span：以上属于不同管理层级或示范项目类型，不能在未限定范围时合并成同一条要求。

### Citation

- `S1` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 4, 'text_length': 960}` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / candidate=`Root-002|44280ca2-3372-5a6b-bc48-4a2f3706a74a`

## 6. 15题负向 Facet 测试

| Test | Forbidden/Required Subtype | Detected Subtypes | Constraint | Result |
|---|---|---|---|---|
| NEG-A01 | DETAILED_DESIGN | `[]` | MUST_BE_ABSENT | PASS |
| NEG-A02 | DETAILED_DESIGN | `[]` | MUST_BE_ABSENT | PASS |
| NEG-A03 | DETAILED_DESIGN | `[]` | MUST_BE_ABSENT | PASS |
| NEG-B01 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-B02 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-B03 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-C01 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-C02 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-C03 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-D01 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-D02 | DESIGN_MANAGEMENT | `[]` | MUST_BE_ABSENT | PASS |
| NEG-E01 | DESIGN_MANAGEMENT | `['DESIGN_MANAGEMENT']` | MUST_PRESENT | PASS |
| NEG-E02 | DESIGN_MANAGEMENT | `['DESIGN_MANAGEMENT']` | MUST_PRESENT | PASS |
| NEG-F01 | DETAILED_DESIGN | `['DETAILED_DESIGN']` | MUST_PRESENT | PASS |
| NEG-F02 | DETAILED_DESIGN | `['DETAILED_DESIGN']` | MUST_PRESENT | PASS |

- False Facet：`0`
- 测试通过：`15/15`

## 7. 12题 Scope 回归

| Test | Specificity | Selected Valid Facets | Grounding/Coverage | Result |
|---|---|---|---|---|
| PSC-001 | EXPLICIT_SCOPE | `[]` | `True` | PASS |
| PSC-002 | EXPLICIT_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-003 | UNSPECIFIED_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-004 | EXPLICIT_SCOPE | `[]` | `True` | PASS |
| PSC-005 | EXPLICIT_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-006 | EXPLICIT_SCOPE | `[]` | `True` | PASS |
| PSC-007 | PARTIAL_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/SMART_CONSTRUCTION/2026']` | `True` | PASS |
| PSC-008 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-009 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-010 | UNSPECIFIED_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-011 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `True` | PASS |
| PSC-012 | PARTIAL_SCOPE | `[]` | `True` | PASS |

- Scope 回归通过：`12/12`

## 8. BA-001 / BA-003 / BA-005 回归

| BA | Status | Provider Calls | Note |
|---|---|---:|---|
| BA-001 | `PROVIDER_TEMPORARY_FAILURE` | `3` | Preflight 未被 Facet Coverage 改写 |
| BA-003 | `NO_EVIDENCE` | `0` | 保持 SOURCE_SCOPE_MISSING 安全路径 |
| BA-005 | `NO_EVIDENCE` | `0` | 保持 AUTHORITY_INSUFFICIENT 安全路径 |

BA-002/BA-004/BA-008/BA-010 仅做兼容性读取：
`{'BA-002': 'GENERATED', 'BA-004': 'GENERATED', 'BA-008': 'GENERATED', 'BA-010': 'FACT_RESULT'}`

## 9. 结论

BA-007：Grounding 后真实 valid Facet 的 coverage_complete=`True`；但业务期望 Facet 的完整性为 `PARTIAL_EVIDENCE`，缺失范围为 `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']`。最终答案只使用通过局部正文验证的 Facet Claim，没有输出整段 PDF，也没有补齐虚假的笛卡尔组合。
