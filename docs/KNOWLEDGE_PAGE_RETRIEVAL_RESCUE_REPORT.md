# Knowledge Page Retrieval Rescue Report

> TASK-017C-2：为已存在的 Query Page 增加 Shadow Rescue，并明确方法证据与正式公式证据边界。
> 未修改正式 Retriever、Router、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF 或 Reranker。

## 1. Target Knowledge Page

- 识别到的 Query Page：`设计创效价值创造问答.md`
- Source Path：`D:\设计管理\wiki\queries\设计创效价值创造问答.md`
- 识别方式：路径结构 `wiki/queries` + Query Page 内容形式；没有使用固定文件名作为检索规则。

| Retrieval | Rank | Score | Status |
|---|---:|---:|---|
| BM25 | 70 | 10.187929064123473 | RETRIEVED |
| Dense | 77 | 0.5960257770590488 | RETRIEVED |
| RRF | 25 | 0.014991577765300393 | RETRIEVED |

### Target Page 完整 Top100 命中记录

| Retrieval | Rank | Chunk ID | File | Heading | Location | Score | Excerpt |
|---|---:|---|---|---|---|---:|---|
| BM25 | 70 | `3b37042d-35b9-5735-9f73-48a393887c15` | 设计创效价值创造问答.md | 设计创效 / 价值创造（问答归档） > 二、价值从哪来（三大方式） | `{'line_start': 19, 'line_end': 25}` | 10.187929064123473 | ## 二、价值从哪来（三大方式）  - **设计方案优化**：调整平面、结构、工艺选型等，从源头降本提效 - **材料设备选型优化**：在满足功能前提下优选性价比更优的部品 - **施工工艺优化**：让设计更利于建造，降低施工难度与风险  配套管理工具：**价值创造清单**、**价值工程（VE）分析**、**成本效益分析**。 |
| Dense | 77 | `3b37042d-35b9-5735-9f73-48a393887c15` | 设计创效价值创造问答.md | 设计创效 / 价值创造（问答归档） > 二、价值从哪来（三大方式） | `{'line_start': 19, 'line_end': 25}` | 0.5960257770590488 | ## 二、价值从哪来（三大方式）  - **设计方案优化**：调整平面、结构、工艺选型等，从源头降本提效 - **材料设备选型优化**：在满足功能前提下优选性价比更优的部品 - **施工工艺优化**：让设计更利于建造，降低施工难度与风险  配套管理工具：**价值创造清单**、**价值工程（VE）分析**、**成本效益分析**。 |
| RRF | 25 | `3b37042d-35b9-5735-9f73-48a393887c15` | 设计创效价值创造问答.md | 设计创效 / 价值创造（问答归档） > 二、价值从哪来（三大方式） | `{'line_start': 19, 'line_end': 25}` | 0.014991577765300393 | ## 二、价值从哪来（三大方式）  - **设计方案优化**：调整平面、结构、工艺选型等，从源头降本提效 - **材料设备选型优化**：在满足功能前提下优选性价比更优的部品 - **施工工艺优化**：让设计更利于建造，降低施工难度与风险  配套管理工具：**价值创造清单**、**价值工程（VE）分析**、**成本效益分析**。 |

## 2. Target Page Chunk Structure

- Document：`设计创效价值创造问答.md`
- SourceBlock/Chunk 数量：11
- Heading 保留：`['设计创效 / 价值创造（问答归档）', '设计创效 / 价值创造（问答归档） > 一、是什么', '设计创效 / 价值创造（问答归档） > 三、怎么做（工作流程）', '设计创效 / 价值创造（问答归档） > 二、价值从哪来（三大方式）', '设计创效 / 价值创造（问答归档） > 五、协同关系（不是孤立动作）', '设计创效 / 价值创造（问答归档） > 六、落地清单（已有项目实例）', '设计创效 / 价值创造（问答归档） > 四、案例与沉淀结构', '设计创效 / 价值创造（问答归档） > 四、案例与沉淀结构 > 产品线价值创造（方法层）', '设计创效 / 价值创造（问答归档） > 四、案例与沉淀结构 > 设计创效案例库（实例层）', '设计创效 / 价值创造（问答归档） > 引用来源', '设计创效 / 价值创造（问答归档） > 相关页面']`
- Method Chunk：`['01b01b40-99e3-5931-a90b-0fbab093e986', '09eecab8-251a-5707-87db-c2600a784510', '13705ef4-faa5-5957-9c88-fe667ae374d9', 'd49e4e63-8010-5aa2-a40f-ee768cb0917e']`
- Metric Dimension Chunk：`['13705ef4-faa5-5957-9c88-fe667ae374d9']`
- Formula Chunk：`[]`

## 3. Query Page Classification

- `QUERY_PAGE`：路径位于 `wiki/queries`；
- `CONCEPT_PAGE`：路径位于 `wiki/concepts`；
- `SOURCE_DOCUMENT`：Office/PDF 或 raw/attachments 源文件；
- `OTHER`：不满足以上结构。

## 4. Query Page Probe 与 Candidate Fusion

- Query Page Probe 候选数：2
- Candidate Fusion 候选数：102
- Candidate Origin：BM25、DENSE、RRF、QUERY_PAGE_PROBE；同一 Chunk 合并来源，不重复计数。
- QUERY_PAGE_PROBE 只做 RESCUE，不直接生成答案。
- 正式制度/管理指南仍由现有 Evidence Selection 的角色与权威性规则优先。

| Rank | Root | File | knowledge_page_type | Candidate Origin | Fusion Score |
|---:|---|---|---|---|---:|
| 1 | Root-002 | EPC设计管理经验总结（光谷实验中学）.docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.03278689 |
| 2 | Root-002 | 河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02987737 |
| 3 | Root-002 | EPC设计管理经验总结(华师南湖训练馆).docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02889813 |
| 4 | Root-002 | EPC设计管理经验总结(华师南湖训练馆).docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02496124 |
| 5 | Root-002 | EPC设计管理经验总结（光谷实验中学）.docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02460361 |
| 6 | Root-002 | EPC设计管理复盘总结（光谷能源站).docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02419817 |
| 7 | Root-002 | EPC设计管理经验总结(常熟药机厂项目).docx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02418552 |
| 8 | Root-001 | 01仁和水厂桩基及支护部分（浙江）.pptx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02346003 |
| 9 | Root-001 | 仁和水厂桩基及支护部分（浙江）.md | CONCEPT_PAGE | RRF,BM25,DENSE | 0.02326468 |
| 10 | Root-002 | 《项目设计管理手册》.pdf | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02296402 |
| 11 | Root-002 | 2026年二季度半年运营会资料汇编（隐藏版）.pdf | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02291776 |
| 12 | Root-001 | 05数字经济产业园含超塔（华中）.pptx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.02089287 |
| 13 | Root-001 | 华师附中项目（直属）.md | CONCEPT_PAGE | RRF,BM25,DENSE | 0.02058516 |
| 14 | Root-001 | 仁和水厂桩基及支护部分（浙江）.md | CONCEPT_PAGE | RRF,BM25,DENSE | 0.01913919 |
| 15 | Root-001 | 淮安酒店项目（直属）.md | CONCEPT_PAGE | RRF,BM25,DENSE | 0.01731812 |
| 16 | Root-001 | 01铁投·书香林语（华中）.pptx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.01654701 |
| 17 | Root-001 | 02华师附中项目（直属）.pptx | SOURCE_DOCUMENT | RRF,BM25,DENSE | 0.01619511 |
| 18 | Root-001 | 05数字经济产业园含超塔（华中）.pptx | SOURCE_DOCUMENT | RRF,DENSE | 0.01612903 |
| 19 | Root-001 | 2025年设计管理总结.md | SOURCE_DOCUMENT | RRF,BM25 | 0.01587302 |
| 20 | Root-002 | 设计管理策划书-星谷科创中心项目.docx | SOURCE_DOCUMENT | RRF,DENSE | 0.01587302 |

## 5. Evidence Capability

- has_method_evidence：`True`
- has_formula_evidence：`True`
- `METHOD`：流程、步骤、开展方式和实施动作；
- `FORMULA`：证据中明确出现公式/计算式；
- `METRIC_DIMENSION`：造价节约、工期缩短、品质提升、运维成本降低等量化维度。

## 6. BA-002 最终实际答案

```text
现有知识库可以明确设计效益增量的评价思路和量化维度，但当前证据中没有发现唯一、正式的企业计算公式。

方法/流程证据：
- 第四章 实施总结
截至目前，完成方案比选52项，入图70%，设计效益策划19项，设计效益率增量6.27％，共1848.65万元。且设计进度符合施工进度要求。 [S2]
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
汪骞杰  二 [S3]

量化维度证据：
- ## 三、怎么做（工作流程）

1. **识别价值点** → 2. **分析可行性** → 3. **实施优化** → 4. **验证效果**

量化评估维度（成果怎么算账）：
- 造价节约
- 工期缩短
- 品质提升
- 运维成本降低 [S_RESCUE]

正式计算口径证据：
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

证据边界：以上公式仅作为来源原文引用，不对其适用范围外推。
```

Final Status：`GENERATED`

### Citation

- `S2`：EPC设计管理经验总结（光谷实验中学）.docx，Root=`Root-002`，location=`{'paragraph_start': 94, 'paragraph_end': 95}`；excerpt：第四章 实施总结 截至目前，完成方案比选52项，入图70%，设计效益策划19项，设计效益率增量6.27％，共1848.65万元。且设计进度符合施工进度要求。
- `S3`：《项目设计管理手册》.pdf，Root=`Root-002`，location=`{'page': 30, 'text_length': 1047}`；excerpt：- 24 - 17.3 设计创效管理 17.3.1 设计创效认定 设计创效包含设计管理效益及造价优化效益。其中设计管理创效包含 限额划分及指标拟定、设计成果与经济文件匹配性分析、交付界面策 划、勘察管理、进度管控等创造的隐性效益及风险化解；成本优化效 益包含通过设计优化创造的降本及增效效益。 17.3.2 设计创效计算 1）项目设计创效经济效益额=项目设计创效活动实施后实际取得的经 济效益额（不包括工期效益）—创效活动实施前（依据合同、方案、 报价等）预期取得的经济效益额。 2）设计创效率定义：设计创效率�= 总创效金额� 自施产值�×100% 总创效金额� 自施产值�×100%。 总创效金额X：设计创效实施后通过认定的经济效益总额； 自施产值Y：合同中明确的项目自行施工范围的累计产值。 18 附则 1）本手册由局设计与技术管理部负责解释和修订。 2）本手册自印发之日起执行，《中建三局EPC 项目设计管理指南》（中 建三设〔2023〕369 号）、《中建三局EPC 项目设计创效管理指南（试 行版）》（中建三设函〔2022〕3 号）同步废止。 3）本手册配合《中建三局流程手册》内容配套应用，流程及附件见流 程手册。 4）本手册附件目录见表17-1。 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 08:40 汪骞杰  二公司  2024-12-30 0 汪骞杰  二公司  2024-12-30 0 汪骞杰  二公司  2024-12-30 0 刘畅  二公司  2024-12-30 16:03 刘畅  二公司  20
- `S_RESCUE`：设计创效价值创造问答.md，Root=`Root-001`，location=`{'line_start': 27, 'line_end': 35}`；excerpt：## 三、怎么做（工作流程）  1. **识别价值点** → 2. **分析可行性** → 3. **实施优化** → 4. **验证效果**  量化评估维度（成果怎么算账）： - 造价节约 - 工期缩短 - 品质提升 - 运维成本降低

边界结论：当前 Evidence 已包含正式计算口径；最终答案只引用该正式来源，不对公式适用范围外推。本报告没有补充“优化后/优化前”类未被证据支持的公式。

## 7. 通用非 BA 测试

| ID | Query | Query Page Probe | Method | Formula | Final Status |
|---|---|---|---|---|---|
| Q-001 | 设计创效怎么做？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-002 | 如何开展设计价值创造？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-003 | 设计效益增量的计算方式？ | 2 | True | True | GENERATED |
| Q-004 | 设计创效的定义是什么？ | 2 | True | True | GENERATED |
| Q-005 | 设计创效有哪些评价维度？ | 2 | True | True | GENERATED |
| Q-006 | 设计价值创造流程是什么？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-007 | 设计任务书怎么做？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-008 | EPC项目设计管理的责任是什么？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-009 | 方案比选的方法是什么？ | 2 | True | False | PARTIAL_EVIDENCE |
| Q-010 | 设计风险如何开展识别和化解？ | 2 | True | False | PARTIAL_EVIDENCE |

## 8. BA-001～BA-010 回归

| BA | Baseline Status | Rescue Status | Route | Query Page Probe | Evidence Capability |
|---|---|---|---|---:|---|
| BA-001 | GENERATED | GENERATED | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-002 | NO_EVIDENCE | GENERATED | CLAIM_ANSWER_PATH | 2 | {"has_method_evidence": true, "has_formula_evidence": true, "items": [{"source_id": "S1", "knowledge_root_id": "Root-002", "approval_status": "ROOT002_SELECTIVELY_APPROVED_SHADOW", "document_id": "c9758b90-9300-5c37-aaba-eae72124a0b9", "chunk_id": "804cd46a-4478-55c8-b7bc-d23a73fa20a6", "file_name": "EPC设计管理经验总结（光谷实验中学）.docx", "source_path": "D:\\工作\\二公司技术部\\2026\\设计复盘\\EPC设计管理经验总结（光谷实验中学）.docx", "document_role": "项目案例", "authority_level": "L4", "knowledge_page_type": "SOURCE_DOCUMENT", "candidate_origin": ["RRF", "BM25", "DENSE"], "location": {"paragraph_start": 76, "paragraph_end": 77}, "excerpt": "3.5.5 设计效益策划\n对应指定设计效益策划，设计效益率增量6.27％，共1848.65万元（含降概金额），具体如下：", "evidence_capability": ["EXAMPLE"]}, {"source_id": "S2", "knowledge_root_id": "Root-002", "approval_status": "ROOT002_SELECTIVELY_APPROVED_SHADOW", "document_id": "c9758b90-9300-5c37-aaba-eae72124a0b9", "chunk_id": "7e440f36-2daa-514c-a2f4-0ab24b44ba50", "file_name": "EPC设计管理经验总结（光谷实验中学）.docx", "source_path": "D:\\工作\\二公司技术部\\2026\\设计复盘\\EPC设计管理经验总结（光谷实验中学）.docx", "document_role": "项目案例", "authority_level": "L4", "knowledge_page_type": "SOURCE_DOCUMENT", "candidate_origin": ["RRF", "BM25", "DENSE"], "location": {"paragraph_start": 94, "paragraph_end": 95}, "excerpt": "第四章 实施总结\n截至目前，完成方案比选52项，入图70%，设计效益策划19项，设计效益率增量6.27％，共1848.65万元。且设计进度符合施工进度要求。", "evidence_capability": ["METHOD", "EXAMPLE"]}, {"source_id": "S3", "knowledge_root_id": "Root-002", "approval_status": "ROOT002_SELECTIVELY_APPROVED_SHADOW", "document_id": "ece9a0e1-59df-5fd5-98b9-ea5533ccbd60", "chunk_id": "defd9780-451c-567d-8b80-607d3c03b56f", "file_name": "《项目设计管理手册》.pdf", "source_path": "D:\\工作\\二公司技术部\\2026\\各类文件\\设计管理\\《项目设计管理手册》.pdf", "document_role": "管理指南", "authority_level": "L2", "knowledge_page_type": "SOURCE_DOCUMENT", "candidate_origin": ["RRF", "BM25", "DENSE"], "location": {"page": 30, "text_length": 1047}, "excerpt": "- 24 -\n17.3\n设计创效管理\n17.3.1\n设计创效认定\n设计创效包含设计管理效益及造价优化效益。其中设计管理创效包含\n限额划分及指标拟定、设计成果与经济文件匹配性分析、交付界面策\n划、勘察管理、进度管控等创造的隐性效益及风险化解；成本优化效\n益包含通过设计优化创造的降本及增效效益。\n17.3.2\n设计创效计算\n1）项目设计创效经济效益额=项目设计创效活动实施后实际取得的经\n济效益额（不包括工期效益）—创效活动实施前（依据合同、方案、\n报价等）预期取得的经济效益额。\n2）设计创效率定义：设计创效率�= 总创效金额�\n自施产值�×100%\n总创效金额�\n自施产值�×100%。\n总创效金额X：设计创效实施后通过认定的经济效益总额；\n自施产值Y：合同中明确的项目自行施工范围的累计产值。\n18\n附则\n1）本手册由局设计与技术管理部负责解释和修订。\n2）本手册自印发之日起执行，《中建三局EPC 项目设计管理指南》（中\n建三设〔2023〕369 号）、《中建三局EPC 项目设计创效管理指南（试\n行版）》（中建三设函〔2022〕3 号）同步废止。\n3）本手册配合《中建三局流程手册》内容配套应用，流程及附件见流\n程手册。\n4）本手册附件目录见表17-1。\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 08:40\n汪骞杰  二公司  2024-12-30 0\n汪骞杰  二公司  2024-12-30 0\n汪骞杰  二公司  2024-12-30 0\n刘畅  二公司  2024-12-30 16:03\n刘畅  二公司  2024-12-30 16:03\n刘畅  二公司  2024-12-30 16:03\n刘畅  二公司  2024-12-3\n刘畅  二公司  2024-12-30 16:03\n刘畅  二公司  2024-", "evidence_capability": ["METHOD", "FORMULA", "DEFINITION", "EXAMPLE"]}, {"source_id": "S_RESCUE", "knowledge_root_id": "Root-001", "approval_status": "BASELINE_SHADOW_APPROVED", "document_id": "106362ed-a69d-5297-b052-56e2b15da3a1", "chunk_id": "13705ef4-faa5-5957-9c88-fe667ae374d9", "file_name": "设计创效价值创造问答.md", "source_path": "D:\\设计管理\\wiki\\queries\\设计创效价值创造问答.md", "document_role": "管理指南", "authority_level": "L2", "knowledge_page_type": "QUERY_PAGE", "candidate_origin": ["QUERY_PAGE_PROBE"], "location": {"line_start": 27, "line_end": 35}, "excerpt": "## 三、怎么做（工作流程）\n\n1. **识别价值点** → 2. **分析可行性** → 3. **实施优化** → 4. **验证效果**\n\n量化评估维度（成果怎么算账）：\n- 造价节约\n- 工期缩短\n- 品质提升\n- 运维成本降低", "evidence_capability": ["METHOD", "METRIC_DIMENSION"]}, {"source_id": "S5", "knowledge_root_id": "Root-002", "approval_status": "ROOT002_SELECTIVELY_APPROVED_SHADOW", "document_id": "a3c9cab5-43b6-5b40-91b1-058f1cb60090", "chunk_id": "a07bbb75-fff8-534b-94dd-1ea02bb9f3da", "file_name": "河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx", "source_path": "D:\\工作\\二公司技术部\\2026\\设计复盘\\河北科技师范学院滨海技术应用实训基地建设项目EPC设计总结.pptx", "document_role": "项目案例", "authority_level": "L4", "knowledge_page_type": "SOURCE_DOCUMENT", "candidate_origin": ["RRF", "DENSE"], "location": {"slide": 34, "title": "效益测算"}, "excerpt": "效益测算\n第六部分", "evidence_capability": ["EXAMPLE"]}]} |
| BA-003 | STRUCTURE_INVALID | STRUCTURE_INVALID | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-004 | STRUCTURE_INVALID | STRUCTURE_INVALID | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-005 | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-006 | PARTIAL_EVIDENCE | PARTIAL_EVIDENCE | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-007 | GENERATED | GENERATED | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-008 | GENERATED | GENERATED | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-009 | NO_EVIDENCE | NO_EVIDENCE | CLAIM_ANSWER_PATH | 2 | NOT_REPLAYED |
| BA-010 | FACT_RESULT | FACT_RESULT | FACT_ANSWER_PATH | 2 | NOT_REPLAYED |

## 9. 边界与未完成事项

- 未修改正式系统；
- 未重切全库 Chunk；
- 未重新生成全库 Embedding；
- BA-003、BA-004、BA-006、BA-009 未借本任务修复；
- 如果后续发现正式计算公式，应以正式制度/管理办法/批准口径替换当前方法性 Query Page 作为 DIRECT Evidence。
