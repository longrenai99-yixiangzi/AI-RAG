# P0 Integrated Shadow Regression Report

> TASK-017D：仅在 Root-001 + Root-002 Shadow 环境执行统一端到端回归；未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding 全库索引、RRF、Reranker、业务口径或新增知识源。

## 1. Unified Pipeline Architecture

Question → Router V1.1 → Root-001 + Root-002 BM25/Dense/RRF → conditional Scope/Query Page Probe → Candidate Fusion/Dedup → Scope/Authority/Role validation → Optimized Evidence Selection → Claim/Option/Direct Fact/Deterministic Fact Answer → Schema/Claim/Section/Citation/Semantic validators → Final Renderer

- Root-001 chunks：`4747`
- Root-002 chunks：`1847`
- Qdrant collections：`[('Root-001', 'full_corpus_shadow_bge_m3'), ('Root-002', 'root002_shadow_bge_m3')]`
- fresh_run：所有 BA-001～BA-010 记录均为 `true`；旧 JSON 仅用于 baseline comparison。

## 2. BA-001～BA-010 Fresh Run

| BA | Route | Answer Path | Final Status | Business Quality | Scope Probe | Query Page Probe | Evidence IDs |
|---|---|---|---|---|---|---|---|
| BA-001 | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | PROVIDER_TEMPORARY_FAILURE | PENDING_OWNER_REVIEW | False | False | S1,S2,S3,S4,S5 |
| BA-002 | CLAIM_ANSWER_PATH | CLAIM_FORMULA_SEMANTIC_PATH | GENERATED | CORRECT_CANDIDATE | False | True | S1,S2,S3,S_RESCUE,S5 |
| BA-003 | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | PROVIDER_TEMPORARY_FAILURE | PENDING_OWNER_REVIEW | False | False | S1,S2,S3,S4,S5 |
| BA-004 | CLAIM_ANSWER_PATH | OPTION_QUERY | GENERATED | CORRECT_CANDIDATE | False | False | S1,S2,S3,S4,S5 |
| BA-005 | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | PROVIDER_TEMPORARY_FAILURE | PENDING_OWNER_REVIEW | False | False | S1,S2,S3,S4,S5 |
| BA-006 | CLAIM_ANSWER_PATH | DIRECT_FACT_CLAIM_PATH | NO_EVIDENCE | CORRECT_REFUSAL_CANDIDATE | True | False | S1,S2,S3,S4,S5 |
| BA-007 | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | PROVIDER_TEMPORARY_FAILURE | PENDING_OWNER_REVIEW | False | False | S1,S2,S3,S4,S5 |
| BA-008 | CLAIM_ANSWER_PATH | DIRECT_FACT_CLAIM_PATH | GENERATED | CORRECT_CANDIDATE | True | False | S1,S2,S3,S4,S_DIRECT |
| BA-009 | CLAIM_ANSWER_PATH | CLAIM_SCOPE_GAP_REFUSAL | NO_EVIDENCE | KNOWN_SOURCE_SCOPE_GAP | False | False | S1,S2,S3,S4,S5 |
| BA-010 | FACT_ANSWER_PATH | FACT_ANSWER_PATH | FACT_RESULT | CORRECT_CANDIDATE | False | False | S1,S2,S3,S4,S5 |

### 每题最终实际答案与 Citation

#### BA-001

问题：设计任务书需要包含哪些内容？

最终答案：

生成服务暂时不可用，保留可核查 Evidence。

Evidence：
- `S1` EPC设计管理复盘总结（光谷能源站).docx / `{'paragraph_start': 90, 'paragraph_end': 91}` / origin=RRF,BM25,DENSE
- `S2` EPC设计管理复盘总结（光谷能源站).docx / `{'table': 15, 'rows': 4, 'columns': 4}` / origin=RRF,BM25,DENSE
- `S3` 《项目设计管理手册》.pdf / `{'page': 17, 'text_length': 1358}` / origin=RRF,BM25,DENSE
- `S4` 《项目设计管理手册》.pdf / `{'page': 37, 'text_length': 1213}` / origin=RRF,BM25,DENSE
- `S5` 设计任务书.md / `{'line_start': 8, 'line_end': 10}` / origin=RRF,BM25,DENSE

business_quality_flag：`PENDING_OWNER_REVIEW`

#### BA-002

问题：设计效益增量的计算方式？

最终答案：

现有正式资料已经给出了设计创效的计算口径：

- - 24 -
17.3
设计创效管理
17.3.1
设计创效认定
设计创效包含设计管理效益及造价优化效益。其中设计管理创效包含
限额划分及指标拟定、设计成果与经济文件匹配性分析、交付界面策
划、勘察管理、进度管控等创造的隐性效益及风险化解；成本优化效
益包含通过设计优化创造的降本及增效效益。
17.3.2
设计创效计算
1）项目设计创效经济效益额=项目设计创效活动实施后实际取得的经
济效益额（不包括工期效益）—创效活动实施前（依据合同、方案、
报价等）预期取得的经济效益额。
2）设计创效率定义：设计创效率�= 总创效金额�
自施产值�×100%
总创效金额�
自施产值�×100%。
总创效金额X：设计创效实施后通过认定的经济效益总额；
自施产值Y：合同中明确的项目自行施工范围的累计产值。
18
附则
1）本手册由局设计与技术管理部负责解释和修订。
2）本手册自印发之日起执行，《中建三局EPC 项目设计管理指南》（中
建三设〔2023〕369 号）、《中建三局EPC 项目设计创效管理指南（试
行版）》（中建三设函〔2022〕3 号）同步废止。
3）本手册配合《中建三局流程手册》内容配套应用，流程及附件见流
程手册。
4）本手册附件目录见表17-1。
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 08:40
汪骞杰  二公司  2024-12-30 0
汪骞杰  二公司  2024-12-30 0
汪骞杰  二公司  2024-12-30 0
刘畅  二公司  2024-12-30 16:03
刘畅  二公司  2024-12-30 16:03
刘畅  二公司  2024-12-30 16:03
刘畅  二公司  2024-12-3
刘畅  二公司  2024-12-30 16:03
刘畅  二公司  2024- [S3]

- 方法补充：第四章 实施总结
截至目前，完成方案比选52项，入图70%，设计效益策划19项，设计效益率增量6.27％，共1848.65万元。且设计进度符合施工进度要求。 [S2]

- 量化维度补充：## 三、怎么做（工作流程）

1. **识别价值点** → 2. **分析可行性** → 3. **实施优化** → 4. **验证效果**

量化评估维度（成果怎么算账）：
- 造价节约
- 工期缩短
- 品质提升
- 运维成本降低 [S_RESCUE]

语义边界：当前证据尚未明确证明“设计效益增量”与“项目设计创效经济效益额”完全等同，因此不进一步替业务负责人定义术语。

Evidence：
- `S1` EPC设计管理经验总结（光谷实验中学）.docx / `{'paragraph_start': 76, 'paragraph_end': 77}` / origin=RRF,BM25,DENSE
- `S2` EPC设计管理经验总结（光谷实验中学）.docx / `{'paragraph_start': 94, 'paragraph_end': 95}` / origin=RRF,BM25,DENSE
- `S3` 《项目设计管理手册》.pdf / `{'page': 30, 'text_length': 1047}` / origin=RRF,BM25,DENSE
- `S_RESCUE` 设计创效价值创造问答.md / `{'line_start': 27, 'line_end': 35}` / origin=QUERY_PAGE_PROBE
- `S5` 河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx / `{'slide': 34, 'title': '效益测算'}` / origin=RRF,DENSE

business_quality_flag：`CORRECT_CANDIDATE`

#### BA-003

问题：厂房产品线的方案比选案例包含哪些专业？

最终答案：

生成服务暂时不可用，保留可核查 Evidence。

Evidence：
- `S1` AI_存量知识库分类框架_系统生成.md / `{'line_start': 275, 'line_end': 318}` / origin=RRF,BM25,DENSE
- `S2` AI_存量知识库分类框架_系统生成.md / `{'line_start': 275, 'line_end': 318}` / origin=RRF,BM25,DENSE
- `S3` 方案比选典型案例.md / `{'line_start': 12, 'line_end': 16}` / origin=RRF,BM25,DENSE
- `S4` 方案比选典型案例.md / `{'line_start': 8, 'line_end': 10}` / origin=RRF,BM25,DENSE
- `S5` 产品线设计方案比选典型案例汇编（厂房）.md / `{'line_start': 1, 'line_end': 1}` / origin=RRF,BM25,DENSE

business_quality_flag：`PENDING_OWNER_REVIEW`

#### BA-004

问题：自动喷淋系统管材方案比选可采用哪几种方案进行比选？

最终答案：

## 结论
- 可以采用以下 2 种方案进行比选：[S2]
## 可比选方案
- 传统镀锌钢管 [S2]
- 新型材料加强氯化聚氯乙烯(PVC-C)管材 [S2]
## 补充说明
- 根据实际情况选用，建议选用方案二 [S2]
## 证据边界
- evidence_insufficient

Evidence：
- `S1` 设计方案比选提示清单7.23.xlsx / `{'sheet_name': 'Sheet1', 'row_start': 1, 'row_end': 362, 'column_count': 10, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S2` 设计方案比选提示清单7.23.xlsx / `{'sheet_name': 'Sheet1', 'row_start': 1, 'row_end': 362, 'column_count': 10, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S3` 《项目设计管理手册》.pdf / `{'page': 64, 'text_length': 869}` / origin=RRF,BM25,DENSE
- `S4` 《项目设计管理手册》.pdf / `{'page': 18, 'text_length': 1306}` / origin=RRF,BM25
- `S5` 方案比选.md / `{'line_start': 12, 'line_end': 17}` / origin=RRF,BM25,DENSE

business_quality_flag：`CORRECT_CANDIDATE`

#### BA-005

问题：特殊环境条件下集电线路电气设计的图审要点有哪些？

最终答案：

生成服务暂时不可用，保留可核查 Evidence。

Evidence：
- `S1` EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx / `{'paragraph_start': 210, 'paragraph_end': 256}` / origin=RRF,BM25,DENSE
- `S2` EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx / `{'paragraph_start': 167, 'paragraph_end': 169}` / origin=RRF,BM25,DENSE
- `S3` EPC设计管理经验总结(涟水第三水厂建设项目3.17).docx / `{'paragraph_start': 155, 'paragraph_end': 474}` / origin=RRF,BM25,DENSE
- `S4` EPC设计管理经验总结(涟水第三水厂建设项目3.17).docx / `{'paragraph_start': 155, 'paragraph_end': 474}` / origin=RRF,DENSE
- `S5` EPC设计管理经验总结(泸州垃圾焚烧发电厂项目)20260309.docx / `{'table': 7, 'rows': 53, 'columns': 8}` / origin=RRF,BM25,DENSE

business_quality_flag：`PENDING_OWNER_REVIEW`

#### BA-006

问题：2026年局设计与技术系统的责任状要求DOP平台电子图形文件数据中心上传数量是多少？

最终答案：

未找到可直接核查的同范围数值事实。

Evidence：
- `S1` EPC项目设计管理方法与实务.md / `{'line_start': 1, 'line_end': 3}` / origin=SCOPE_PROBE
- `S2` 设计风险清单.md / `{'line_start': 2, 'line_end': 7}` / origin=SCOPE_PROBE
- `S3` 新洲星谷科创中心价值创造清单.md / `{'line_start': 1, 'line_end': 1}` / origin=SCOPE_PROBE
- `S4` 示范文本.md / `{'line_start': 2, 'line_end': 7}` / origin=SCOPE_PROBE
- `S5` 应城智汇港价值创造清单.md / `{'line_start': 1, 'line_end': 1}` / origin=SCOPE_PROBE

business_quality_flag：`CORRECT_REFUSAL_CANDIDATE`

#### BA-007

问题：2026年设计示范项目的打造要求是什么？

最终答案：

生成服务暂时不可用，保留可核查 Evidence。

Evidence：
- `S1` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 2, 'text_length': 888}` / origin=RRF,BM25,DENSE
- `S2` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 1, 'text_length': 524}` / origin=RRF,BM25,DENSE
- `S3` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S4` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S5` AI_存量知识库分类框架_系统生成.md / `{'line_start': 220, 'line_end': 269}` / origin=RRF,BM25,DENSE

business_quality_flag：`PENDING_OWNER_REVIEW`

#### BA-008

问题：2025年公司设计创效金额是多少元？

最终答案：

结论：根据同范围正式资料，创效金额约4.45亿，折合约 445,000,000 元。 [S_DIRECT]

口径边界：该证据为公司年度事实，未使用项目级金额替代。

Evidence：
- `S1` 2025年年度总结.md / `{'line_start': 5, 'line_end': 7}` / origin=SCOPE_PROBE
- `S2` 关于优化公司总部部门及设置“四大中心”的通知.pdf / `{'page': 9, 'text_length': 770}` / origin=SCOPE_PROBE
- `S3` 设计策划评审意见表(1).xlsx / `{'sheet_name': 'Sheet1', 'row_start': 1, 'row_end': 37, 'column_count': 8, 'header_row': 1}` / origin=SCOPE_PROBE
- `S4` 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf / `{'page': 9, 'text_length': 828}` / origin=SCOPE_PROBE
- `S_DIRECT` 2025年饶淇述职.md / `{'line_start': 5, 'line_end': 7}` / origin=RRF,BM25,DENSE,SCOPE_PROBE

business_quality_flag：`CORRECT_CANDIDATE`

#### BA-009

问题：2026年4月EPC项目双周推进会上，给土木公司的督办是什么？

最终答案：

目标资料不在当前批准 Shadow 知识源范围内，暂不使用不相关资料替代。

Evidence：
- `S1` 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf / `{'page': 1, 'text_length': 548}` / origin=RRF,BM25,DENSE
- `S2` 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf / `{'page': 12, 'text_length': 464}` / origin=RRF,BM25,DENSE
- `S3` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S4` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / origin=RRF,BM25,DENSE
- `S5` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 1, 'text_length': 524}` / origin=RRF,BM25,DENSE

business_quality_flag：`KNOWN_SOURCE_SCOPE_GAP`

#### BA-010

问题：星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？

最终答案：

### 结论

星谷科创中心设计价值创造清单共有 **80 条有效明细**。按业务负责人确认口径“增加效益 = 利润 > 0”，其中有 **37 条增加效益记录**。

### 专业/原始分组统计

| 专业/原始分组 | 总条数 | 其中增加效益条数（利润 > 0） |
|---|---:|---:|
| 整体方案 | 4 | 0 |
| 桩基及支护 | 23 | 12 |
| 建筑 | 25 | 12 |
| 结构 | 14 | 3 |
| 给排水 | 4 | 4 |
| 暖通 | 3 | 3 |
| 电气 | 3 | 1 |
| 消防 | 4 | 2 |

### 口径说明

- 增加效益字段：`利润`；判断规则：`利润 > 0`。
- 有效明细中利润为空或未判定的记录：**43 条**。这些记录不能直接解释为没有效益。
- 第 88 行是公式汇总行，不属于有效明细，未计入上述统计。

Evidence：
- `S1` EPC设计管理经验总结(华师南湖训练馆).docx / `{'paragraph_start': 81, 'paragraph_end': 85}` / origin=RRF,BM25,DENSE
- `S2` EPC设计管理经验总结(华师南湖训练馆).docx / `{'table': 11, 'rows': 10, 'columns': 6}` / origin=RRF,BM25,DENSE
- `S3` 河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx / `{'slide': 35, 'title': '6.效益测算'}` / origin=RRF,BM25,DENSE
- `S4` 河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx / `{'slide': 16, 'title': '3.5借助资源，集中策划'}` / origin=RRF,BM25,DENSE
- `S5` 方案比选与价值创造清单方案比选及价值创造.xlsx / `{'sheet_name': '方案比选', 'row_start': 1, 'row_end': 103, 'column_count': 16, 'header_row': 1}` / origin=RRF,DENSE

business_quality_flag：`CORRECT_CANDIDATE`

## 3. P0 Stability Runs

| BA | Runs | Status Distribution | Provider Failure | Key Check |
|---|---:|---|---:|---|
| BA-002 | 10 | `{'GENERATED': 10}` | 0 | formula=10/10; boundary=10/10 |
| BA-004 | 10 | `{'GENERATED': 10}` | 0 | generated=10/10; unsupported_options=0 |
| BA-008 | 10 | `{'GENERATED': 10}` | 0 | company_scope=10/10 |

## 4. Real Cross-Evidence OPTION_QUERY

| Case | Actual Status | Evidence Count | Selected Files | Unsupported Option |
|---|---|---:|---|---|
| OPTION-E2E-01 | PROVIDER_TEMPORARY_FAILURE | 5 | EPC设计管理经验总结(泸州垃圾焚烧发电厂项目)20260309.docx; EPC设计管理经验总结（光谷实验中学）.docx; 《项目设计管理手册》.pdf | [] |
| OPTION-E2E-02 | GENERATED | 5 | EPC设计管理经验总结(河北科技师范学院项目) .docx; EPC设计管理经验总结(泸州垃圾焚烧发电厂项目)20260309.docx; 设计方案比选提示清单7.23.xlsx | [] |
| OPTION-E2E-03 | GENERATED | 5 | EPC设计管理经验总结（光谷实验中学）.docx; 公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx; 设计方案比选提示清单7.23.xlsx | [] |
| OPTION-E2E-04 | PROVIDER_TEMPORARY_FAILURE | 5 | EPC设计管理经验总结(河北科技师范学院项目) .docx; 河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx; 设计方案比选提示清单7.23.xlsx | [] |
| OPTION-E2E-05 | GENERATED | 5 | AI_知识自生长接入映射_V0.1.md; EPC设计管理经验总结（光谷实验中学）.docx; 设计方案比选提示清单7.23.xlsx | [] |

## 5. P0 Acceptance Checks

- BA-002：status=`GENERATED`，formula=`True`，semantic_alignment=`SEMANTIC_MAPPING_UNCONFIRMED`。
- BA-004：status=`GENERATED`，selected target file=`True`。
- BA-008：status=`GENERATED`，scope=`COMPANY`。
- BA-010：status=`FACT_RESULT`，frozen facts=`{'total_rows': 80, 'increase_effect_count': 37, 'undetermined_profit_count': 43, 'business_rule': '利润 > 0'}`。
- BA-003/005/006/009：未因新路由或 OPTION_QUERY 自动生成无依据答案；业务标记保留为候选或范围缺口，需人工验收。

## 6. Before / After TASK-017A

| Aspect | TASK-017A / historical baseline | TASK-017D fresh integrated shadow |
|---|---|---|
| Execution | 既有分阶段/局部产物 | `fresh_run=true`，统一 pipeline_run_id |
| BA-002 | 可能出现公式语义矛盾 | 正式公式与 semantic boundary 分离 |
| BA-004 | Evidence 已有但结构可能失败 | OPTION_QUERY 原子 Claim + Section Map + Citation |
| BA-008 | 项目/公司范围需单独 Scope Guard | Unified Retrieval + Scope Probe + deterministic direct fact |
| BA-010 | 冻结 FACT_RESULT | 仍使用 80/37/43，未让 LLM 重算 |

## 7. Remaining P1/P2

- P1：普通 Claim Path 仍依赖 Provider 可用性；需继续保留 Provider Failure 与业务失败的区分。
- P1：部分业务资料仍在批准 Root 范围外，安全拒答不等于知识已完整。
- P1：业务负责人仍需逐题确认 `business_quality_flag`，程序不自动判定最终 PASS。
- P2：统一 pipeline 的检索轨迹可继续细化为可视化审计视图；本任务不进入正式 8000 服务。
