# Knowledge OS V2.5 Final Report

## 结论

V2.5 已完成“Owner Gold 来源补齐 → Structured Knowledge V2 staging → 增量 Dense → Gold/Strict/Variant → Holdout/Shadow/Rollback”收口。

最终 Release Gate：**CONDITIONAL_APPROVE**。

所有客观门均通过；条件只有两项：Owner Gold 清单没有提供原始 `source_version`，以及 8010 仍保持 V1 Runtime，不能自动切换。8000 全程 OFF，未写正式 Qdrant、SQLite 或正式 Index。

## 1. 六条 NOT_EVALUABLE 的真实原因与处理结果

V2.4 的 6 条 NOT_EVALUABLE 不是答案错误，而是 Owner Gold 指向的原始来源不在 V2.4 Frozen Candidate Scope。五个唯一物理文件均真实存在，本轮全部进入独立 V2.5 staging。

| 回归题 | Owner Gold 来源与定位 | V2.4 | V2.5 | 证据/引用状态 |
|---|---|---:|---:|---|
| SRG-001 / BA-001 | `《项目设计管理手册》.pdf`，第 17 页，`9 设计任务书管理 / 9.1 设计任务书编制` | NOT_EVALUABLE | PASS | 项目概况、工作范围、工作要求、设计技术要点；并明确设计依据及管控要求 |
| SRG-002 / BA-002 | `《项目设计管理手册》.pdf`，第 30 页，`17.3 设计创效管理 / 17.3.2 设计创效计算` | NOT_EVALUABLE | PASS | 实施后实际经济效益额减实施前预期经济效益额（不含工期效益）；设计创效率公式；术语映射仍按未确认处理 |
| SRG-004 / BA-005 | `全专业施工图审核要点提示汇编（2026年）.xlsx`，正文 Sheet，1450–1455 行 | NOT_EVALUABLE | PASS | 17.1 重冰区、17.2 高海拔、17.3 沿海盐雾、17.4 林区、17.5 冻土、17.6 采空/地灾六行证据 |
| SRG-005 / BA-006 | `3.二公司：2026年设计与技术专项责任书 .docx`，表 1 第 22 行“考核内容” | NOT_EVALUABLE | PASS | 11 月份 DOP 平台电子图形文件数据中心上传不少于 40 个项目图形文件 |
| SRG-006 / BA-007 | `关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx`，`一、设计示范工程实施要求`，第 5–9 段 | NOT_EVALUABLE | PASS | 不超概/质量安全底线、7%/2.5%效益率增量、13 项/规定动作 100%执行及时、年度检查前 20% |
| SRG-008 / BA-009 | `EPC项目设计管理工作监督任务表（2026年4月第一周）.xlsx`，`Sheet1 (2)`，第 17–18 行 | NOT_EVALUABLE | PASS | 青山 52 街坊项目与武汉轻工大学金银湖校区 13 号学生公寓项目两条土木公司督办记录 |

六条均达到 `source coverage smoke = 6/6`，Strict Regression 中 `NOT_EVALUABLE = 0`，引用有效，未引入错误项目或错误来源版本。

## 2. 原始 Owner Gold 来源真实性

- 5 个唯一物理文件均存在、可访问、可解析。
- 解析结果：5/5 `parse_status=parsed`。
- 原始 Owner Gold 清单未提供可核实的语义版本号；V2.5 使用文件 SHA-256 作为不可变 `source_version`，并在 `admitted_sources.json` 与新 Document 记录中落盘。
- 该版本口径仍需内容负责人确认，不能被表述成“原始版本号已确认”。
- 五个来源与 BA 的追溯关系已补齐：BA-001/002、BA-005、BA-006、BA-007、BA-009。

## 3. Structured Knowledge V2 接入

接入严格沿用现有链路：Structured Parser V2 → Section Builder → Semantic Chunk V2 → Metadata → Knowledge Node Binding → Quality Gate。未为六道题编写特例 Parser/Chunk 规则。

| 指标 | 结果 |
|---|---:|
| 新来源文件 | 5 |
| 新 Sections | 77 |
| 新 Tables | 5 |
| 新 Table Rows | 1,616 |
| 新 Atomic Evidence | 7,159 |
| V2.5 Semantic Chunks 总数 | 10,711 |
| 新增 Semantic Chunks | 1,809 |
| 旧 Chunk 改写 | 0 |
| 新增 QUARANTINED | 9 |
| 新增重复标记 | 77 |
| Knowledge Node Binding | 1,891 |
| Quality Gate | PASS |

V2.5 数据与向量位于独立目录：`data/shadow/knowledge_v2_5_staging`；V2.4 Frozen Candidate 未被覆盖。

## 4. 增量 Dense Embedding

- 模型：`BAAI/bge-m3`。
- 输入：`retrieval_text`。
- 旧 8,902 个 Chunk 向量全部复用。
- 新 1,809 个 Chunk 向量全部生成，pending=0。
- `old_vectors_equal=true`，旧向量未发生变化。
- Reranker 仍为 OFF；未调整 BM25 权重、RRF k、Validator 或 Chunk 规则。

## 5. Retrieval Gold 50

冻结参数仍为：BM25 `section_path×5 / file_name×3 / knowledge_type×2 / raw_text×1`，RRF `k=60`，Reranker OFF。

V2.5 RRF-k60：

| 目标 | Recall@5 | Recall@10 | Recall@20 | MRR | nDCG@10 | Miss |
|---|---:|---:|---:|---:|---:|---:|
| File | 0.64 | 0.66 | 0.66 | 0.6040 | 0.6175 | 17 |
| Section | 0.54 | 0.58 | 0.58 | 0.5196 | 0.5335 | 21 |
| Row | 0.54 | 0.58 | 0.58 | 0.5196 | 0.5335 | 21 |

相对 V2.4：File MRR `+0.0967`、nDCG@10 `+0.1037`、Miss `-5`；Section/Row MRR `+0.0301`、nDCG@10 `+0.0337`、Miss `-1`。没有出现原有 Retrieval 的明显退化。

## 6. Answer Gold 与 Strict Regression

- Answer Gold：30/30 PASS。
- Strict Regression Core：30/30 PASS，`NOT_EVALUABLE=0`，`FAIL=0`。
- Core Pass Rate：100%。
- Critical Failure：0。
- Unsupported Claim：0。
- Wrong Scope：0。
- Variant：30/30 PASS，Variant Stability Rate 100%。

原 V2.4 的 24 PASS + 6 NOT_EVALUABLE 已变为 V2.5 的 30 PASS；六条来源的逐题差异已写入 `release_gate.json.not_evaluable_resolution`。

## 7. Observational Regression 48

- 运行 48/48。
- V2.4 与 V2.5 状态分布一致：`ANSWERED=37`、`INSUFFICIENT_EVIDENCE=11`。
- `UNCHANGED=48/48`。
- `accuracy_gate=NOT_APPLICABLE`，观察回归不替代 Strict Regression。

## 8. Holdout、Shadow、Rollback

### Holdout

- 封存 Holdout 30 题已运行，0 个运行错误。
- 本轮不评分、不用 Holdout 反调规则。
- 运行状态分布：`ANSWERED=23`、`INSUFFICIENT_EVIDENCE=6`、`PARTIAL_ANSWER=1`。

### Shadow

以封存 Holdout 30 题做只读对照：

- New Hit：0
- Lost Hit：0
- Agreement：30/30（100%）
- Citation Change：0
- Latency P50/P95：1,596.95 / 2,060.50 ms
- Error Rate：0

V2.5 仍是 isolated candidate-only Shadow；8010 没有切换。

### Rollback

- 状态：READY。
- V2.4 Frozen Candidate 未改变。
- V1 index intact=true。
- 未执行线上切换，因此没有制造需要恢复的正式状态。

## 9. Release Decision

| Gate | 状态 |
|---|---|
| CUDA | PASS |
| Dense | PASS |
| Retrieval Gold | PASS |
| Retrieval Regression | PASS |
| Answer Gold | PASS |
| Owner Gold Coverage | PASS |
| Strict Regression | PASS |
| Variant Stability | PASS |
| Observational Regression | OBSERVED（48 全部 UNCHANGED） |
| Holdout | PASS（执行通过，未评分） |
| Shadow | PASS |
| Rollback | PASS |

**最终建议：CONDITIONAL_APPROVE。**

条件：

1. 内容负责人确认五个物理来源的版本口径；当前可追溯版本是文件 SHA-256，不是原清单提供的语义版本号。
2. 如需让 8010 使用 V2.5，必须另行取得明确授权并执行受控切换；本任务不自动切换。
3. 8000 继续保持 OFF；不写正式 Qdrant、SQLite、Index。

## 10. 交付物

- [V2.5 Release Gate](../evaluation/knowledge_os_v2_5/release_gate.json)
- [V2.5 Candidate Manifest](../evaluation/knowledge_os_v2_5/candidate_v2_5_manifest.json)
- [Owner Gold Source Audit](../evaluation/knowledge_os_v2_5/owner_gold_source_audit.json)
- [Source Coverage Smoke Test](../evaluation/knowledge_os_v2_5/source_coverage_smoke_test.json)
- [Retrieval Gold Result](../evaluation/knowledge_os_v2_5/retrieval_gold_result.json)
- [Answer Gold Result](../evaluation/knowledge_os_v2_5/answer_gold_result.json)
- [Strict Regression Result](../evaluation/knowledge_os_v2_5/strict_regression_result.json)
- [Strict Variant Result](../evaluation/knowledge_os_v2_5/strict_variant_result.json)
- [Observational Regression Result](../evaluation/knowledge_os_v2_5/observational_regression_result.json)
- [Holdout Result](../evaluation/knowledge_os_v2_5/holdout_result.json)
- [Shadow Result](../evaluation/knowledge_os_v2_5/shadow_result.json)
- [Rollback Result](../evaluation/knowledge_os_v2_5/rollback_result.json)
