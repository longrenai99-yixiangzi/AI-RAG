# Policy Local Grounding Window Report

> TASK-017E-1.2.2 仅在 Shadow 环境执行。未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF、Reranker、Router、Preflight 或 BA-010 Fact Path。
> Root-002 是 frozen Shadow scope，governance=PENDING_APPROVAL，不等同于正式授权。

## 1. 1.2.1 问题与本次修复

- 1.2.1 基线缺失业务 Facet：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']`。
- 1.2.1 基线 selected evidence：`['关于印发中建三局2026年设计与技术工作计划的通知.pdf']`。
- 根因：PDF 文本中存在中文字符间换行，例如“设计管\n理示范项目”；普通空白压缩后仍保留中间空格，导致局部模式未命中。
- 本次方案：全文候选 → 中文字符间空白归一化 → 多锚点 finditer → 锚点居中窗口 → 当前窗口内 Facet Grounding。
- 组织层级来自文件名/标题/路径元数据，主题与子类型只来自当前局部窗口。

## 2. BA-007 Candidate-Level 结果

- 状态：`GENERATED`。
- 业务期望 Facet：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`。
- 有效 Candidate Facet：`[{'facet': 'COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'candidate_count': 1, 'top_rank': 21, 'top_file': '关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf', 'top_location': {'page': 6, 'text_length': 851}, 'top_support_span': '五是打造设计管理示范项目，各主业公司打造不少于1 个设计效益增量超*%或设计创效金额超**万的示范项目，为各单位树立榜样。'}, {'facet': 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'candidate_count': 1, 'top_rank': 34, 'top_file': '关于印发中建三局2026年设计与技术工作计划的通知.pdf', 'top_location': {'page': 4, 'text_length': 960}, 'top_support_span': '三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单，打造不少于1 个深化设计示范项目，以点带面，全面提升深化设计管理能力。'}]`。
- selected_valid_facets：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`。
- missing_valid_facets：`[]`。
- missing_business_facets：`[]`。
- business_answer_completeness：`COMPLETE`。
- invalid_candidate_facets：`96` 个候选保留为诊断信息，未计入 Coverage denominator。

### BA-007 局部有效证据

| Facet | Top rank | 文件 | 位置 | 局部锚点/窗口 |
|---|---:|---|---|---|
| `COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` | 21 | 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf | `{'page': 6, 'text_length': 851}` | 五是打造设计管理示范项目，各主业公司打造不少于1 个设计效益增量超*%或设计创效金额超**万的示范项目，为各单位树立榜样。 |
| `GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` | 34 | 关于印发中建三局2026年设计与技术工作计划的通知.pdf | `{'page': 4, 'text_length': 960}` | 三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单，打造不少于1 个深化设计示范项目，以点带面，全面提升深化设计管理能力。 |

### BA-007 压缩后的原子 Claim

- `C1` / `POLICY_ATOMIC` / facet=`COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / evidence=`S1` / 各主业公司打造不少于1个设计管理示范项目。
  - support_span：五是打造设计管理示范项目，各主业公司打造不少于1 个设计效益增量超*%或设计创效金额超**万的示范项目，为各单位树立榜样。
- `C2` / `POLICY_ATOMIC` / facet=`COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / evidence=`S1` / 设计效益增量超*%或设计创效金额超**万
  - support_span：五是打造设计管理示范项目，各主业公司打造不少于1 个设计效益增量超*%或设计创效金额超**万的示范项目，为各单位树立榜样。
- `C3` / `POLICY_ATOMIC` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / evidence=`S2` / 聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单
  - support_span：三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单，打造不少于1 个深化设计示范项目，以点带面，全面提升深化设计管理能力。
- `C4` / `POLICY_ATOMIC` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / evidence=`S2` / 打造不少于1 个深化设计示范项目
  - support_span：三是要聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单，打造不少于1 个深化设计示范项目，以点带面，全面提升深化设计管理能力。
- `C5` / `SCOPE_BOUNDARY` / facet=`MULTI_SCOPE_BOUNDARY` / evidence=`S1` / 公司层面的设计管理示范项目要求，与局级的深化设计示范项目要求属于不同管理层级和专业类型。
  - support_span：selected_valid_facets>=2; boundary is derived from the two validated facet identities

### BA-007 最终回答（Shadow）

结论：根据当前选中的局部政策证据，示范项目要求按已验证的管理层级和专业类型分别列示。

1. 各主业公司打造不少于1个设计管理示范项目。 [S1]
2. 设计效益增量超*%或设计创效金额超**万 [S1]
3. 聚焦深化设计计划管理等6 大关键环节，制定标准化管控清单 [S2]
4. 打造不少于1 个深化设计示范项目 [S2]

## 3. 多锚点与局部窗口测试

| Test | Expected | Detected | False Facet | Missed Valid | Result |
|---|---|---|---|---|---|
| W-A01 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT']` | False | False | PASS |
| W-A02 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT']` | False | False | PASS |
| W-A03 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT']` | False | False | PASS |
| W-B01 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT', 'TECHNOLOGY']` | False | False | PASS |
| W-B02 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT', 'SMART_CONSTRUCTION']` | False | False | PASS |
| W-B03 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT', 'GREEN_CONSTRUCTION']` | False | False | PASS |
| W-C01 | DETAILED_DESIGN=True | `['DETAILED_DESIGN']` | False | False | PASS |
| W-C02 | DETAILED_DESIGN=True | `['DETAILED_DESIGN']` | False | False | PASS |
| W-D01 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT', 'TECHNOLOGY']` | False | False | PASS |
| W-E01 | DETAILED_DESIGN=True | `['DETAILED_DESIGN']` | False | False | PASS |
| W-F01 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT']` | False | False | PASS |
| W-G01 | DESIGN_MANAGEMENT=True | `['DESIGN_MANAGEMENT']` | False | False | PASS |
| W-N01 | DETAILED_DESIGN=False | `[]` | False | False | PASS |
| W-N02 | DESIGN_MANAGEMENT=False | `['TECHNOLOGY']` | False | False | PASS |
| W-N03 | DESIGN_MANAGEMENT=False | `['SMART_CONSTRUCTION']` | False | False | PASS |

- Window tests：`15/15`。
- False Facet：`0`。
- Missed Valid Facet：`0`。

## 4. Claim Compression 测试

| Test | 文件 | 局部支持 | Claim短于窗口 | 水印/签名/时间戳 | Unsupported Claim | Result |
|---|---|---|---|---|---|---|
| C-01 | 关于印发中建三局2026年设计与技术工作计划的通知.pdf | True | True | False | False | PASS |
| C-02 | 公司复盘EPC项目管理台账.xlsx | True | True | False | False | PASS |
| C-03 | 公司复盘EPC项目管理台账.xlsx | True | True | False | False | PASS |
| C-04 | 公司复盘EPC项目管理台账.xlsx | True | True | False | False | PASS |
| C-05 | AI_存量知识库分类框架_系统生成.md | True | True | False | False | PASS |
| C-06 | 公司复盘EPC项目管理台账.xlsx | True | True | False | False | PASS |
| C-07 | 公司复盘EPC项目管理台账.xlsx | True | True | False | False | PASS |
| C-08 | 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf | True | True | False | False | PASS |
| C-09 | 关于印发中建三局2026年设计与技术工作计划的通知.pdf | True | True | False | False | PASS |
| C-10 | 附件：公司2025年拟打造EPC设计管理示范项目清单.md | True | True | False | False | PASS |

- Compression evidence count：`10`（目标至少10条；不足时不补造证据）。
- Compression pass：`10/10`。

## 5. 12项 Scope 回归

| Test | Specificity | Selected Facets | Coverage Complete | Result |
|---|---|---|---|---|
| LGS-001 | EXPLICIT_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | True | PASS |
| LGS-002 | EXPLICIT_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-003 | UNSPECIFIED_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-004 | EXPLICIT_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | True | PASS |
| LGS-005 | EXPLICIT_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-006 | EXPLICIT_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/TECHNOLOGY/2026']` | True | PASS |
| LGS-007 | PARTIAL_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/SMART_CONSTRUCTION/2024', 'COMPANY/DEMONSTRATION_PROJECT/SMART_CONSTRUCTION/2025', 'COMPANY/DEMONSTRATION_PROJECT/SMART_CONSTRUCTION/2026']` | True | PASS |
| LGS-008 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-009 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | False | PASS |
| LGS-010 | UNSPECIFIED_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-011 | PARTIAL_SCOPE | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | True | PASS |
| LGS-012 | PARTIAL_SCOPE | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | False | PASS |

- Scope pass：`12/12`。

## 6. BA-001/003/005 与兼容性回归

本次只读取既有 Shadow/Preflight 持久化结果，不重新调用 LLM；未修改这些问题的正式或 Shadow 结果。

| 问题 | 持久化状态 | 结果文件 |
|---|---|---|
| BA-001 | `GENERATED` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-001.json` |
| BA-003 | `NO_EVIDENCE` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-003.json` |
| BA-005 | `NO_EVIDENCE` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-005.json` |
| BA-002 | `GENERATED` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-002.json` |
| BA-004 | `GENERATED` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-004.json` |
| BA-008 | `GENERATED` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-008.json` |
| BA-010 | `FACT_RESULT` | `D:\AI智能体\AI设计管理RAG-V1\evaluation\claim_preflight_positive_path\BA-010.json` |

## 7. 结论与边界

- BA-007 已从 1.2.1 的缺失公司 Facet 状态复核为：`COMPLETE`；当前状态为 `GENERATED`。
- 只有局部窗口内同时满足组织层级、示范项目主题、子类型、年度和制度/指南权威条件的 Candidate 才计为 VALID_FACET。
- 无法通过局部证据支持的候选仍保留为 WEAK/UNSUPPORTED 诊断，不进入 Coverage denominator。
- Claim 只引用压缩后的局部支持片段；未把整段 PDF Chunk 直接作为回答，也未恢复被掩码的数字。
- 本报告不代表正式链路已接入；下一步如进入集成，需先审查 BA-007 两个 Facet 的业务口径与 PDF 定位稳定性。
