# Answer Engine Failure Diagnosis

> TASK-016E-1：只使用 TASK-016D-2B Optimized Evidence Bundle 诊断 BA-007、BA-010。
> 未使用 Baseline Evidence；未修改 Retriever、Shadow Selector、RRF、Embedding、正式 Qdrant、8000 服务或 Answer Engine 代码。
> 本次未关闭 Claim Validator / Citation Validator，也未以 LLM 结果质量作为 Selector 成败判断。

## 1. 诊断范围

- Provider：现有 OpenAI-compatible Shadow Provider；使用当前已配置 Key。
- Provider 配置可用：`True`；错误：`无`
- Evidence 来源：`evaluation/traces_optimized/BA-007.json`、`BA-010.json` 的 `final_evidence`。
- Answer Policy：沿用当前 `policy_for_intent`，未增加 FACT_QUERY / AGGREGATION_QUERY 分支。

完整逐题回放记录：

- [BA-007.json](D:/AI智能体/AI设计管理RAG-V1/evaluation/answer_engine_failure/BA-007.json)
- [BA-010.json](D:/AI智能体/AI设计管理RAG-V1/evaluation/answer_engine_failure/BA-010.json)

每份记录均保存 question、intent、fact_types、Optimized Evidence、Prompt、raw_llm_response、parsed_response、repair_response、claims、section_map、Schema、Claim Validation、Citation Render、final_status、failure_stage 和 Provider diagnostics。

## 2. 逐题总览

| 问题 | Intent | Fact Type | Optimized Evidence | Fact Type进入Prompt | Claims | Schema | Citation | Claim Validator | Final Status | Primary Root Cause | Secondary Cause |
|---|---|---|---:|---|---:|---|---|---|---|---|---|
| BA-007 | POLICY_QUERY | DATE_FACT | 5 | False | 4 | True | True | True | GENERATED | J OTHER | - |
| BA-010 | TEMPLATE_QUERY | AMOUNT_FACT, COUNT_FACT, SCOPE_FACT | 6 | False | 0 | True | True | True | NO_EVIDENCE | H FACT_QUERY_CAPABILITY_MISSING | G MULTI_CHUNK_AGGREGATION_FAILURE, A PROMPT_FAILURE |

## 3. BA-007 诊断

- Final Status：`GENERATED`
- Failure Stage：`{'primary': 'J OTHER', 'secondary': [], 'evidence': 'No failure observed in this run; retain trace for replay'}`
- Optimized Evidence IDs：`['S1', 'S2', 'S3', 'S4', 'S5']`
- Raw JSON 可解析：`True`
- Claims 数量：`4`
- section_map：`{"conclusion": ["C3"], "management_requirements": ["C1", "C2", "C3"], "evidence": ["C1", "C2", "C3", "C4"], "scope_or_exceptions": []}`
- Schema：`{"valid": true, "category": "A", "errors": []}`
- Repair：triggered=`False`，success=`False`
- Claim Validation：`{"valid": true, "unsupported_claims": 0, "invalid_source_ids": [], "missing_evidence_claims": 0, "errors": []}`
- Citation Render：`{"answer_text": "## conclusion\n- 局属各单位需打造不少于1个深化设计示范项目 [S1]\n## management_requirements\n- 局属各单位需聚焦深化设计计划管理等6大关键环节 [S1]\n- 局属各单位需制定标准化管控清单 [S1]\n- 局属各单位需打造不少于1个深化设计示范项目 [S1]\n## evidence\n- 局属各单位需聚焦深化设计计划管理等6大关键环节 [S1]\n- 局属各单位需制定标准化管控清单 [S1]\n- 局属各单位需打造不少于1个深化设计示范项目 [S1]\n- 打造深化设计示范项目旨在以点带面，全面提升深化设计管理能力 [S1]\n## scope_or_exceptions\n- evidence_insufficient", "valid": true, "errors": [], "rendered_claim_ids": ["C3", "C1", "C2", "C3", "C1", "C2", "C3", "C4"], "visible_section_ids": ["conclusion", "management_requirements", "evidence"]}`

判断：

- BA-007 的证据已包含目标 PDF，若本次出现 STRUCTURE_INVALID，根因应定位在 LLM JSON/Schema/Section Mapping，而不是 Retriever 或 Selector。
- 如果 Schema 与 Citation 均通过但没有 Claim，则是回答策略/Prompt 未把“设计示范项目要求”组织成可输出 Claim 的问题。

## 4. BA-010 诊断

- Final Status：`NO_EVIDENCE`
- Failure Stage：`{'primary': 'H FACT_QUERY_CAPABILITY_MISSING', 'secondary': ['G MULTI_CHUNK_AGGREGATION_FAILURE', 'A PROMPT_FAILURE'], 'evidence': 'No Claim was produced for a fact/aggregation query despite a non-empty optimized Evidence Bundle'}`
- Optimized Evidence IDs：`['S1', 'S2', 'S3', 'S4', 'S5', 'S6']`
- 目标 Workbook Evidence 数量：`6`
- Fact Types：`['AMOUNT_FACT', 'COUNT_FACT', 'SCOPE_FACT']`
- Fact Types 是否进入 Prompt：`False`
- Claims 数量：`0`
- section_map：`{"purpose": [], "fields": [], "usage": [], "precautions": [], "version_or_basis": []}`
- Schema：`{"valid": true, "category": "A", "errors": []}`
- Claim Validation：`{"valid": true, "unsupported_claims": 0, "invalid_source_ids": [], "missing_evidence_claims": 0, "errors": []}`
- Citation Render：`{"answer_text": "## purpose\n- evidence_insufficient\n## fields\n- evidence_insufficient\n## usage\n- evidence_insufficient\n## precautions\n- evidence_insufficient\n## version_or_basis\n- evidence_insufficient", "valid": true, "errors": [], "rendered_claim_ids": [], "visible_section_ids": []}`

判断：

- 当前 Answer Schema 只有 TEMPLATE_QUERY 的 purpose / fields / usage / precautions / version_or_basis，没有 group_by、count、sum、list、scope 等聚合字段。
- 当前 Prompt Builder 没有把 COUNT_FACT、AMOUNT_FACT、SCOPE_FACT 作为结构化事实类型传给模型。
- 六个 Workbook Chunk 虽然进入 Evidence，但多个 Sheet 的表格事实需要跨 Chunk 聚合；当前 Claim Schema 只表达自然语言 Claim + evidence_ids，不能稳定表达按专业分组、计数和金额合计。
- 如果本题返回 NO_EVIDENCE / NO_CLAIM 且 Schema、Citation、Claim Validator 均正常，主要根因是 FACT_QUERY_CAPABILITY_MISSING，次要根因是 MULTI_CHUNK_AGGREGATION_FAILURE 和 PROMPT_FAILURE。

## 5. Answer Pipeline 检查结论

| 阶段 | 检查内容 | 本任务结论 |
|---|---|---|
| Optimized Evidence | 是否只使用 D-2B Evidence | 是 |
| Prompt Builder | 是否包含 Fact Type 字段 | 按当前实现不包含 |
| LLM JSON | 是否可解析 | 以逐题 JSON 记录为准 |
| Schema | claims / section_map / evidence_insufficient | 以逐题 Schema 记录为准 |
| Claim Validator | 是否放宽或绕过 | 否 |
| Citation Renderer | 是否自动引用 Evidence IDs | 沿用现有确定性渲染 |
| Fact Aggregation | 是否有 group_by / count / sum / scope | 当前没有 |

## 6. PRIMARY ROOT CAUSE 分类

允许分类：A PROMPT_FAILURE、B LLM_SCHEMA_FAILURE、C PARSER_FAILURE、D SECTION_MAPPING_FAILURE、E CLAIM_VALIDATION_FAILURE、F CITATION_FAILURE、G MULTI_CHUNK_AGGREGATION_FAILURE、H FACT_QUERY_CAPABILITY_MISSING、I PROVIDER_FAILURE、J OTHER。

- BA-007 PRIMARY：**J OTHER**；Secondary：无；证据：No failure observed in this run; retain trace for replay
- BA-010 PRIMARY：**H FACT_QUERY_CAPABILITY_MISSING**；Secondary：G MULTI_CHUNK_AGGREGATION_FAILURE, A PROMPT_FAILURE；证据：No Claim was produced for a fact/aggregation query despite a non-empty optimized Evidence Bundle

## 7. 最小修复方案（只设计，不实施）

### BA-007

1. 保持现有 Claim Validator 与 Citation Renderer；
2. 在 POLICY_QUERY 的 Prompt/Schema 中明确 conclusion、requirements、basis、scope_or_exceptions；
3. 要求模型将“示范项目”相关 Claim 绑定到目标 PDF 的具体 Evidence ID；
4. 若 JSON/Schema 失败，只允许一次受限 Repair，不增加新事实；
5. 继续保留 STRUCTURE_INVALID，不把结构失败伪装成 GENERATED。

### BA-010

1. 新增只用于 Shadow 的 `FACT_QUERY` / `AGGREGATION_QUERY` Answer Policy；
2. 结构至少支持：`group_by`、`count`、`sum`、`list`、`scope`、`unit`；
3. Claim 增加聚合表达，例如每个专业一个 Claim，并允许一个 Claim 绑定多个 Evidence ID；
4. 明确区分 COUNT_FACT、AMOUNT_FACT、RATE_FACT、DATE_FACT、SCOPE_FACT；
5. 对多个 Sheet 先做确定性表格聚合，再让 LLM 组织语言；LLM 不得自行计算或猜测；
6. 聚合结果必须保留原始 Sheet、行范围和 Evidence ID，继续经过 Claim Validator 与 Citation Validator；
7. 聚合失败时返回 `AGGREGATION_INSUFFICIENT` 或 `PARTIAL_EVIDENCE`，不返回无依据的确定性结论。

## 8. 结论

本任务只诊断 Answer Engine。D-2B 已解决目标证据进入 Evidence Bundle 的问题；BA-010 即使拥有目标 Workbook 的多 Sheet Evidence，当前 Answer Engine 仍缺少事实查询和跨 Chunk 表格聚合表达能力。该问题不应通过关闭 Validator、扩大 Chunk 或让 LLM 猜测数字解决。
