# V1.0 Business Failure Triage

> TASK-017B：基于 TASK-017A 的统一 Shadow 结果，对 BA-001～BA-010 进行业务层失败分诊。
>
> 本任务只诊断和设计修复方案，未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF、Reranker、Answer Engine、Router 或知识源文件。

## 1. 审计边界与证据

本次使用：

- `evaluation/v1_business_acceptance/BA-001.json` ～ `BA-010.json`
- `evaluation/traces_optimized/BA-001.json` ～ `BA-010.json`
- Root-001：`data/shadow/full_corpus_qdrant`
- Root-002：`data/shadow/root002_import/qdrant`
- Root-002 Pipeline 记录：`data/shadow/root002_import/pipeline_staging.jsonl`
- 原始 Gold：`tests/gold_questions/business_acceptance_10.yaml`
- Excel 只读检查：`设计方案比选提示清单7.23.xlsx`、`公司设计服务管理台帐2026.xlsx`及已确认的 2026 年 4 月 EPC 监督任务表

### 1.1 当前技术状态分布

| 状态 | 数量 |
|---|---:|
| GENERATED | 3 |
| PARTIAL_EVIDENCE | 0 |
| NO_EVIDENCE | 4 |
| STRUCTURE_INVALID | 2 |
| FACT_RESULT | 1 |
| PROVIDER_TEMPORARY_FAILURE | 0 |

`GENERATED` 不等于业务正确。本报告只给出业务初判，最终仍需业务负责人确认。

### 1.2 分类定义

- `PASS_CANDIDATE`：证据、范围和回答方向基本一致，可进入业务复核。
- `CORRECT_REFUSAL`：证据不足或权威源缺失时未强行编造，拒答方向正确。
- `SOURCE_SCOPE_MISSING`：源文件存在或有明确登记，但不在当前批准 Root 范围内。
- `GOLD_SOURCE_NOT_RETRIEVED`：正确源文件已在允许范围内，但未进入有效检索候选。
- `TARGET_FILE_NOT_RETRIEVED`：目标文件没有进入 RRF Top20 或其后选择输入。
- `ANSWER_STRUCTURE_FAILURE`：正确事实已进入 Evidence，但 Answer Schema、Section Map 或引用渲染失败。
- `ANSWER_SEMANTIC_FAILURE`：回答混合了不同业务层级、实体或语义范围。
- `FACT_SCOPE_MISMATCH`：问题要求公司级/年度级事实，回答却使用项目级事实。
- `NEEDS_OWNER_CONFIRMATION`：问题本身缺少业务层级、口径或范围限定，系统无法安全替业务负责人决定。

## 2. 十题业务失败分诊表

| BA ID | Current Technical Status | Provisional Business Verdict | Primary Root Cause | Secondary Cause | Correct Source | Correct Source In Approved Root? | Correct Chunk Retrieved? | Correct Evidence Selected? | Answer Correct? | Recommended Fix | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BA-001 | GENERATED | PASS_CANDIDATE | PASS_CANDIDATE | — | Root-001 `wiki/concepts/设计支持/设计任务书.md`；Root-002 `《项目设计管理手册》.pdf` | 是 | 是 | 是 | 候选正确，待业务复核 | 保持现状；业务确认内容完整性 | — |
| BA-002 | NO_EVIDENCE | FAIL candidate | GOLD_SOURCE_NOT_RETRIEVED | KNOWLEDGE_GAP | Root-001 `wiki/queries/设计创效价值创造问答.md` | 是 | 否 | 否 | 否 | 先保证目标问答页进入 RRF/Evidence；再补充明确计算公式或业务口径 | P0 |
| BA-003 | STRUCTURE_INVALID | FAIL / SOURCE BODY MISSING candidate | SOURCE_SCOPE_MISSING | TARGET_FILE_NOT_RETRIEVED | 外部 DOCX：`D:\工作\二公司技术部\2026\知识库\《产品线（医疗、学校、厂房）方案比选案例库》\厂房\中建三局二公司产品线设计方案比选典型案例汇编（厂房）（正文）.docx` | 否 | 否；仅登记页 | 否；选入的是登记页/通用手册 | 否 | 先审批并闭环厂房正文；禁止用通用项目管理手册代替厂房案例 | P1 |
| BA-004 | STRUCTURE_INVALID | PARTIAL candidate | ANSWER_STRUCTURE_FAILURE | — | `D:\设计管理\raw\设计支持\方案比选\方案比选库\设计方案比选提示清单7.23.xlsx`，`Sheet1` 第89行，序号86，`管材变更` | 是 | 是 | 是 | 事实正确，最终回答结构失败 | 修复 Section Map/Schema 校验：`evidence_boundary` 不得写自然语言，必须引用 Claim ID | P0 |
| BA-005 | NO_EVIDENCE | CORRECT_REFUSAL candidate | CORRECT_REFUSAL | KNOWLEDGE_GAP | 当前没有确认的“特殊环境条件下集电线路电气图审要点”专门权威资料；平鲁风电文件只是项目复盘 | 否 | 否；只召回相关案例 | 否 | 是，拒绝强行推导是正确方向 | 由业务补充或批准专门标准/图审资料；不从风电案例生成完整标准 | P2 |
| BA-006 | NO_EVIDENCE | CORRECT_REFUSAL / SOURCE GAP candidate | SOURCE_SCOPE_MISSING | KNOWLEDGE_GAP | 候选责任状资料位于当前批准范围外，例如 `D:\工作\二公司技术部\2026\责任状\局\3.二公司：2026年设计与技术专项责任书 .docx`；当前工作计划只说明 DOP 数据入库方向，没有上传数量 | 否 | 否 | 否 | 是，未从工作计划猜数字 | 先确认并审批真正责任状正文；确认原文后再索引，禁止使用工作计划推算数量 | P1 |
| BA-007 | GENERATED | PARTIAL candidate | NEEDS_OWNER_CONFIRMATION | ANSWER_SEMANTIC_FAILURE | Root-002 `关于印发中建三局二公司2026年设计与技术（科技）工作计划的通知.pdf` | 是 | 是 | 是 | 部分正确；混合了层级和类型 | 明确局级/二公司、设计管理/深化设计/科技智能建造的回答范围，或分层输出 | P1 |
| BA-008 | GENERATED | FAIL candidate | FACT_SCOPE_MISMATCH | TARGET_FILE_NOT_RETRIEVED | Root-001 `D:\设计管理\raw\工作总结\2025年饶淇述职.md`；原文包含“全年服务项目78个……创效金额约4.45亿元” | 是 | 否 | 否 | 否；回答成华师南湖训练馆2594.70万元 | 为“公司+年度+创效金额”建立目标文件/范围优先；公司级问题不得被项目案例覆盖 | P0 |
| BA-009 | NO_EVIDENCE | FAIL / SOURCE GAP candidate | SOURCE_SCOPE_MISSING | ENTITY_SCOPE_MISMATCH | 真实候选源在批准范围外：`D:\工作\二公司技术部\2026\EPC项目双周推进会\4月\EPC项目设计管理工作监督任务表（2026年4月第一周）.xlsx`，`Sheet1 (2)` 第17行有“土木公司—完成设计策划评审，并通知公司参与”；当前批准台账不是该会议资料 | 否 | 否 | 否 | 否 | 先解决 Gold 问题与目标资料冲突，审批 2026 年4月 EPC 会议资料或重定义验收源 | P1 |
| BA-010 | FACT_RESULT | PASS_CANDIDATE | PASS_CANDIDATE | — | Root-002 `方案比选与价值创造清单方案比选及价值创造.xlsx`，`价值创造` Sheet | 是 | 是 | 是 | 候选正确，80/37/43 事实链通过 | 保持确定性 Fact Path；业务复核后再考虑路由集成 | — |

## 3. 逐题根因审计

### BA-001：设计任务书需要包含哪些内容？

Root-001 的 `设计任务书.md` 与 Root-002 的《项目设计管理手册》都进入了 Evidence。回答覆盖项目概况、范围、工作要求、技术要点和专业范围，当前没有发现源范围或证据链断裂。

结论：`PASS_CANDIDATE`。仍需业务负责人确认“包含哪些内容”的颗粒度是否满足实际任务书编制要求。

### BA-002：设计效益增量的计算方式？

`D:\设计管理\wiki\queries\设计创效价值创造问答.md` 确实存在于 Root-001 Shadow。其正文包含：

- `怎么做`：识别价值点 → 分析可行性 → 实施优化 → 验证效果；
- 量化维度：造价节约、工期缩短、品质提升、运维成本降低；
- 设计创效与价值创造的定义和关系。

但现有 `evaluation/traces_optimized/BA-002.json` 明确记录：目标文件未进入 RRF Top20、selection input 或最终 Evidence。现有 trace 没有保存目标文件在 Top20 之外的完整 BM25/Dense 原始排名，因此不能伪造精确的 BM25/Dense 名次；可以确认的是：目标文件没有进入有效 RRF 候选。

此外，该问答页提供的是方法和量化维度，不等于已经存在唯一的企业计算公式。因此：

- 第一根因是 `GOLD_SOURCE_NOT_RETRIEVED`；
- 第二根因是可能存在 `KNOWLEDGE_GAP`，需要业务确认设计效益增量的正式计算口径。

### BA-003：厂房产品线的方案比选案例包含哪些专业？

Root-001 中的登记页 `产品线设计方案比选典型案例汇编（厂房）.md` 只有外部 DOCX 链接，正文 DOCX 实际存在，但位于 `D:\工作\二公司技术部\2026\知识库\...`，不在当前 Root-002 P0/P1 批准目录。

当前 Evidence 选入了登记页和《项目设计管理手册》通用内容，不能证明厂房案例正文的专业清单。因而不能把通用“建筑、结构、给排水、暖通、电气、园林、幕墙”等列表当成该厂房案例的正式答案。

主因是 `SOURCE_SCOPE_MISSING`，不是单纯 Answer Engine 失败。

### BA-004：自动喷淋系统管材方案比选可采用哪几种方案？

Excel 只读检查确认：`设计方案比选提示清单7.23.xlsx` 的 `Sheet1` 第89行、序号86：

- C列：管材变更；
- D列：自动喷淋系统采用传统镀锌钢管；
- E列：自动喷淋系统采用新型材料加强氯化聚氯乙烯（PVC-C）管材；
- H列：包含人工成本降低4.71元/m、材料效益增加2.79元/m等说明；
- I列：根据实际情况选用，建议选用方案二。

该 Sheet1 Chunk 已进入最终 Evidence，当前回答中的两种材料事实与目标行一致。失败发生在 Answer Schema/Section Map：模型把自然语言说明写入 `section_map.evidence_boundary`，而该字段只允许 Claim ID；Citation Renderer 随后报告 unknown claim。它不是知识缺失，也不是 Retrieval 失败。

### BA-005：特殊环境条件下集电线路电气设计的图审要点有哪些？

Evidence 中有平鲁风电项目复盘，包含集电线路路径、手续、接口和设计管理经验，但没有确认的“特殊环境条件下集电线路电气图审要点”专门权威资料。系统拒绝生成完整标准，避免把项目经验升级为企业规范。

结论：当前 `NO_EVIDENCE` 属于合理安全边界，主因是 `CORRECT_REFUSAL`，并伴随 `KNOWLEDGE_GAP`。

### BA-006：2026 年责任状 DOP 电子图形文件数据中心上传数量是多少？

Root-002 的 2026 工作计划确实说明了 DOP 设计管理模块、电子图形文件数据入库和数据资产集成，但当前 Evidence 没有责任状中的具体上传数量。已批准 Root-002 目录中没有发现责任状正文；责任书候选文件位于 `2026\责任状\局`，不属于当前批准目录。

因此不能从“DOP 数据入库”推导数量。当前拒答是正确的，真正需要解决的是责任状正文的 Root 审批与闭环。

### BA-007：2026 年设计示范项目的打造要求是什么？

目标 2026 工作计划已进入 Root-002 Evidence，且直接证据包含：

- 各专业公司打造不少于1个设计管理示范项目；
- 设计管理示范项目的设计效益增量/创效金额要求；
- 深化设计示范项目相关要求。

问题在于用户没有明确要求“设计管理示范”“深化设计示范”“科技/智能建造示范”中的哪一层。当前回答把设计管理示范和深化设计示范并列输出，技术上有来源，但业务语义边界未确认。

主因是 `NEEDS_OWNER_CONFIRMATION`，同时存在 `ANSWER_SEMANTIC_FAILURE` 风险。不能简单把所有“示范项目”内容合并为一个无层级答案。

### BA-008：2025 年公司设计创效金额是多少元？

Root-001 的 `2025年饶淇述职.md` 正文明确写有：全年服务项目78个、提出创效项1340条、入图1151条、创效金额约4.45亿元；该文件和 Chunk 都存在于 Root-001 Shadow。

但 Unified Evidence 中出现的是华师南湖训练馆等项目案例，最终回答为“2594.70万元”。这是项目级金额，不是公司年度金额。

因此主因是 `FACT_SCOPE_MISMATCH`，并伴随目标公司年度文件没有进入 RRF/Evidence 的 `TARGET_FILE_NOT_RETRIEVED`。这是本批最高优先级的已知知识误答。

### BA-009：2026 年4月 EPC 项目双周推进会给土木公司的督办是什么？

当前批准的 `公司设计服务管理台帐2026.xlsx` 只有：

- `技术服务2025年`：5行；
- `技术服务2024年`：148行；
- `次数统计`：17行。

它不是 2026 年4月 EPC 双周推进会督办资料。已确认的 2026 年4月监督任务表位于批准范围外，其 `Sheet1 (2)` 第17行记录：单位“土木公司”，任务为“完成设计策划评审，并通知公司参与”。

所以不是当前台账解析失败，而是 Gold 问题与批准资料范围不一致：`SOURCE_SCOPE_MISSING + ENTITY_SCOPE_MISMATCH`。

### BA-010：星谷科创中心设计价值创造清单

目标 Workbook 和 `价值创造` Sheet 已进入 Root-002 Shadow，确定性 Fact Path 复用已验证结果：

- 有效明细：80条；
- 增加效益：37条；
- 利润为空/未判定：43条；
- 业务口径：增加效益 = 利润 > 0；
- 第88行公式汇总行不计入明细。

该题当前属于 `PASS_CANDIDATE`，但仍不是自动业务验收通过。

## 4. 修复优先级

### P0：知识已存在，但系统答错或没有正确回答

1. **BA-008**：公司年度创效金额被项目金额替代，属于公司级/项目级范围错配；同时目标述职文件没有进入有效证据。
2. **BA-002**：正确问答页已在 Root-001，却未进入 RRF/Evidence；同时需要确认是否有正式计算公式。
3. **BA-004**：正确 Excel 行已进入 Evidence，事实已找到，但结构化回答协议失败。

### P1：源文件存在，但未批准、未闭环或问题层级未确认

1. **BA-003**：厂房案例正文在 Root-002 批准范围外，登记页不能代替正文。
2. **BA-006**：责任状正文和 DOP 数量口径未进入批准 Root；工作计划不能替代责任状。
3. **BA-009**：4月 EPC 督办资料在批准范围外，Gold 问题与“设计服务台账”存在目标冲突。
4. **BA-007**：2026 工作计划已存在，但示范项目层级需要业务确认，回答不能无层级混合。

### P2：真实知识缺口或应保持安全拒答

1. **BA-005**：暂无专门权威的特殊环境集电线路电气图审资料；保持拒答，不把项目复盘升格为标准。

## 5. 只设计、不实施的定向修复方案

| 优先级 | 题目 | 设计性修复方案 | 验收重点 |
|---|---|---|---|
| P0 | BA-008 | 增加公司/年度/总额范围识别；对公司级年度汇总文件建立目标文件保护；项目案例只能作为补充证据 | 不再出现单项目金额；目标述职文件进入 Evidence |
| P0 | BA-002 | 使 query 问答页和正文方法章节进入检索候选；在业务口径确认前，将“流程说明”和“正式计算公式”分开回答 | 召回目标问答页；没有公式时明确证据不足 |
| P0 | BA-004 | Section Map 只允许 Claim ID；自然语言边界说明放入 `evidence_insufficient` 或 Claim，不得写入 ID 数组 | 事实保持第89行两种管材；Final Status 不再因结构错误降级 |
| P1 | BA-003 | 对登记页执行 Root 审批后的外部正文展开；未审批前显式标记 SOURCE_SCOPE_MISSING | 不使用通用手册冒充厂房案例 |
| P1 | BA-006 | 审批并闭环责任状正文；建立“责任状数字”与“工作计划方向性要求”的来源优先级 | 没有责任状数字时继续拒答 |
| P1 | BA-009 | 解决 Gold 目标冲突：批准4月 EPC 资料，或将问题改为设计服务台账查询 | 目标 Sheet/行明确，不能用不相关台账替代 |
| P1 | BA-007 | 先确认示范项目层级；回答按局级、二公司、设计管理、深化设计、科技/智能建造分层 | 不把不同层级混成一条结论 |
| P2 | BA-005 | 由业务补充专门标准或图审清单；在此之前保留 CORRECT_REFUSAL | 不生成未经授权的完整图审标准 |
| — | BA-001、BA-010 | 暂不改动，进入业务复核 | 保持现有证据和 Fact 结果 |

## 6. 关键结论

1. 当前最需要修复的不是继续增加资料，而是 **BA-008 的公司级/项目级范围错配**。
2. BA-002 证明“源文件存在”并不等于“答案已具备”：目标页未召回，且现有内容可能没有唯一计算公式。
3. BA-004 证明 Retrieval 已经找到正确事实，但 Answer Schema 仍能让正确事实以 `STRUCTURE_INVALID` 失败。
4. BA-003、BA-006、BA-009 的主要问题是批准 Root 和 Gold 目标不闭环，不能靠调 Retriever 解决。
5. BA-005 的安全拒答应保留，不应为了提高 GENERATED 数量而把案例经验包装成企业标准。
6. BA-010 的确定性 Fact Path 已具备继续 Shadow 集成的条件，但业务负责人仍需完成最终验收。

## 7. 任务边界确认

- 未实施任何修复；
- 未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF、Reranker、Answer Engine 或 Router；
- 未新增 Root；
- 未修改 `D:\设计管理`、Root-002 源文件或任何 Excel 文件。

