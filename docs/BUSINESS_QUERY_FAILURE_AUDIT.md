# Business Query Retrieval Failure Audit

> Scope: BA-001 to BA-010. Read-only diagnosis only. No LLM, Retrieval, code, formal Retriever, 8000 service, or formal Qdrant change.
> The 10-question output persisted only final Evidence Bundle data; separate BM25/Dense/Hybrid/Reranker Top-K traces were not persisted and were not re-run.

## 1. Ten-question audit table

| Question | Status | Primary root cause | Source file/body | Indexed | Final Evidence |
|---|---|---|---|---|---|
| BA-001 | PARTIAL_EVIDENCE | J ANSWER_ENGINE_FAILURE | YES | OK_INDEXED | YES |
| BA-002 | NO_EVIDENCE | F RETRIEVAL_FAILURE | YES | OK_INDEXED | NO / INCOMPLETE |
| BA-003 | NO_EVIDENCE | B SOURCE_REGISTERED_ONLY | YES | B SOURCE_REGISTERED_ONLY | NO / INCOMPLETE |
| BA-004 | STRUCTURE_INVALID | E INDEX_FAILURE | YES | E INDEX_FAILURE | NO / INCOMPLETE |
| BA-005 | NO_EVIDENCE | A SOURCE_MISSING | UNCONFIRMED | A SOURCE_MISSING | NO / INCOMPLETE |
| BA-006 | NO_EVIDENCE | B SOURCE_REGISTERED_ONLY | YES | B SOURCE_REGISTERED_ONLY | NO / INCOMPLETE |
| BA-007 | NO_EVIDENCE | B SOURCE_REGISTERED_ONLY | YES | B SOURCE_REGISTERED_ONLY | NO / INCOMPLETE |
| BA-008 | GENERATED | NONE (control) | YES | OK_INDEXED | YES |
| BA-009 | NO_EVIDENCE | B SOURCE_REGISTERED_ONLY | YES | B SOURCE_REGISTERED_ONLY | NO / INCOMPLETE |
| BA-010 | PARTIAL_EVIDENCE | H DOCUMENT_LINK_FAILURE (secondary B) | YES | B SOURCE_REGISTERED_ONLY + H LINK_FAILURE | NO / INCOMPLETE |

## 2. Root cause statistics

| Category | Count | IDs |
|---|---:|---|
| A | 1 | BA-005 |
| B | 4 | BA-003, BA-006, BA-007, BA-009 |
| C | 0 | - |
| D | 0 | - |
| E | 1 | BA-004 |
| F | 1 | BA-002 |
| G | 0 | - |
| H | 1 | BA-010 |
| I | 0 | - |
| J | 1 | BA-001 |

## 3. Detailed audit

## BA-001

### 1. User question

设计任务书需要包含哪些内容？

### 2. Current status

PARTIAL_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: Correct source is the wiki design-task-book concept page; it is in the final Evidence Bundle, but the response remained PARTIAL_EVIDENCE.

- Candidate path: D:\设计管理\wiki\concepts\设计支持\设计任务书.md
- Type/category: Markdown; wiki concept page; Shadow chunk count: 5
- Source excerpt: `﻿--- tags: [concept, design-support] created: 2026-06-25 updated: 2026-06-25 source_count: 26 --- # 设计任务书 设计任务书是设计管理中的核心文件，明确项目设计目标、范围、技术标准、进度要求等内容，是设计工作开展和设计合同管理的基础依据。 ## 核心要点 - **编制内容**：项目概况、设计范围、技术标准、进度计划、交付成果 - **分类方式**：方案设计任务书、施工图设计任务书、专项设计任务书 - **管理流程**：编制 → 审核 → 批准 → 交底 → 执行 → 变更管理 - **关键作用**：明确设计边界、控制设计质量、协调多方需求、作为合同附件 ## 相关来源 - [[raw/设计支持/设计任务书|设计任务书文件夹（26个文件）]] - [[raw/设计支持/设计任务书/施工图设计任务书 河北科技师范学院项目|河北科技师范学院施工图设计任务书]] - [[raw/设计支持/设计任务书/中船风电哈密市15万千瓦风储一体化项目设计任务书|中船风电哈密项目设计任务书]] ## 相关概念 `

### 4. Document Pipeline check

- SOURCE_STATUS: OK_INDEXED
- Scan/parse/chunk/index assessment: D/E: correct concept page is parsed, chunked and indexed; correct source is already in final Evidence
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence present

- [S1] 设计任务书.md | cited | role=标准模板 | authority=L3 | chunks_for_path=5
- [S2] 第三批北京旧改项目 设计任务书.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=2
- [S3] 设计任务书 三峡能源浙江杭州钱塘一期50MW分散式风电项目.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=2
- [S4] 施工图设计任务书 常熟厂房项目 2024.10.24.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=2
- [S5] 葛店完整社区施工图设计任务书.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=2

### 6. Document Link chain check

Assessment: Correct source is the wiki design-task-book concept page; it is in the final Evidence Bundle, but the response remained PARTIAL_EVIDENCE.

### 7. Evidence Bundle check

- Correct evidence is present in final bundle.

### 8. Answer Engine check

- J ANSWER_ENGINE_FAILURE: correct source evidence reached the bundle, but final status/answer remained incomplete.

## BA-002

### 1. User question

设计效益增量的计算方式？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: The Q&A page contains workflow and quantification dimensions, but it is absent from the final Evidence Bundle.

- Candidate path: D:\设计管理\wiki\queries\设计创效价值创造问答.md
- Type/category: Markdown; wiki query page; Shadow chunk count: 11
- Source excerpt: `--- tags: [query, design-support, value-creation] created: 2026-08-18 updated: 2026-08-18 question: 设计创效 / 价值创造 是什么、怎么做、有哪些案例？ sources: [wiki/concepts/设计支持/设计价值创造, wiki/concepts/设计支持/设计创效案例库, wiki/concepts/设计支持/设计价值创造/产品线价值创造, wiki/topics/设计支持] --- # 设计创效 / 价值创造（问答归档） > 本页由问答自动归档。原始知识来自 `wiki/concepts/设计支持/` 下相关概念页与 `raw/设计支持/设计价值创造` 原始清单。 ## 一、是什么 **设计价值创造**是通过设计管理活动为项目增值的工作体系，涵盖设计优化、价值工程、成本控制等方面的创新与优化。它是"设计支持"职能的四大目的之一——确保设计质量、控制项目成本、保障工程进度、**实现价值创造**（[[wiki/topics/设计支持]]）。 **设计创效**是价值创造在项目上的落`

### 4. Document Pipeline check

- SOURCE_STATUS: OK_INDEXED
- Scan/parse/chunk/index assessment: D/E: design-value Q&A page exists and has 11 Shadow chunks
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 01公安医院项目（华中）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=42
- [S2] 01公安医院项目（华中）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=42
- [S3] 关于印发中建三局第二建设公司2026年设计与技术工作计划的通知.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2
- [S4] 关于印发中建三局第二建设公司2026年设计与技术工作计划的通知.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2
- [S5] 关于印发中建三局第二建设公司2025年设计与技术工作计划的通知.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2

### 6. Document Link chain check

- The Q&A page contains workflow and quantification dimensions, but it is absent from the final Evidence Bundle.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-003

### 1. User question

厂房产品线的方案比选案例包含哪些专业？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: The local Markdown points to an external DOCX and contains no substantive factory-case body.

- Candidate path: D:\设计管理\raw\设计管理成果总结\管理工具书\设计方案比选案例汇编\产品线方案比选汇编\产品线设计方案比选典型案例汇编（厂房）.md
- Type/category: Markdown registration stub; body is an external DOCX link only.

### 4. Document Pipeline check

- SOURCE_STATUS: B SOURCE_REGISTERED_ONLY
- Scan/parse/chunk/index assessment: B: factory product-line Markdown is a link-only registration stub; external DOCX body is absent
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 方案比选案例分析.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=7
- [S2] 方案比选案例分析.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=7
- [S3] 电子厂房产品线建设标准.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2
- [S4] 产品线设计方案比选典型案例汇编（医疗）.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=2
- [S5] 产品线设计方案比选典型案例汇编（医疗）.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=2

### 6. Document Link chain check

- The local Markdown points to an external DOCX and contains no substantive factory-case body.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-004

### 1. User question

自动喷淋系统管材方案比选可采用哪几种方案进行比选？

### 2. Current status

STRUCTURE_INVALID

### 3. Correct answer existence

Conclusion: YES
Assessment: The indexed comparison XLSX has chunks but no matching automatic-sprinkler pipe-material row; exact approved parsed text is outside the indexed source set.

- Exact approved parsed source: hidden approved parsed artifact under the corpus .ai-growth directory (path recorded in the audit data, not in Shadow Qdrant).
- Indexed comparison file: the persisted 7.23 comparison XLSX; 75 chunks, but no matching automatic-sprinkler pipe-material row found.
- Approved parsed excerpt: water-fire/sprinkler system and DN450-to-DN400 optimization text; exact source is outside Shadow Qdrant.

### 4. Document Pipeline check

- SOURCE_STATUS: E INDEX_FAILURE
- Scan/parse/chunk/index assessment: E: exact sprinkler evidence appears in approved parsed artifacts but not in Shadow Qdrant
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 设计方案比选提示清单7.23.xlsx | candidate only | role=标准模板 | authority=L3 | chunks_for_path=75
- [S2] 设计方案比选提示清单7.23.xlsx | candidate only | role=标准模板 | authority=L3 | chunks_for_path=75
- [S3] 01公安医院项目（华中）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=42
- [S4] 01公安医院项目（华中）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=42
- [S5] AI_知识自生长接入映射_V0.1.md | candidate only | role=正式制度 | authority=L1 | chunks_for_path=9

### 6. Document Link chain check

- The indexed comparison XLSX has chunks but no matching automatic-sprinkler pipe-material row; exact approved parsed text is outside the indexed source set.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-005

### 1. User question

特殊环境条件下集电线路电气设计的图审要点有哪些？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: UNCONFIRMED
Assessment: Only generic project/standard evidence was selected; the exact answer-bearing source was not confirmed.

### 4. Document Pipeline check

- SOURCE_STATUS: A SOURCE_MISSING
- Scan/parse/chunk/index assessment: A: no dedicated source for special-environment collector-line electrical review points was confirmed
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 04天津华苑教育园项目（北京）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=189
- [S2] 04天津华苑教育园项目（北京）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=189
- [S3] 建设标准库.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=11
- [S4] 建设标准库.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=11
- [S5] 06广西体育专科学校（西部）.docx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=16

### 6. Document Link chain check

- Only generic project/standard evidence was selected; the exact answer-bearing source was not confirmed.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-006

### 1. User question

2026年局设计与技术系统的责任状要求DOP平台电子图形文件数据中心上传数量是多少？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: The PDF body containing the DOP upload quantity is not in the corpus root.

- Candidate path: D:\设计管理\raw\设计管理体系\制度性文件\工作计划\中建三局2026年设计与技术工作计划.md
- Type/category: Markdown registration stub; points to external PDF; Shadow chunk count: 2.

### 4. Document Pipeline check

- SOURCE_STATUS: B SOURCE_REGISTERED_ONLY
- Scan/parse/chunk/index assessment: B: 2026 plan Markdown is a link-only page pointing to an external PDF
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 复杂专项与地标.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=5
- [S2] 复杂专项与地标.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=5
- [S3] AI_知识自生长接入映射_V0.1.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=9
- [S4] EPC项目设计管理方法与实务.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=5
- [S5] EPC项目设计管理方法与实务.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=5

### 6. Document Link chain check

Assessment: The PDF body containing the DOP upload quantity is not in the corpus root.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-007

### 1. User question

2026年设计示范项目的打造要求是什么？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: Local Markdown pages contain source links, not the PDF requirements body.

- Candidate path: D:\设计管理\raw\设计管理评价\2025年度公司检查\附件：公司2025年拟打造EPC设计管理示范项目清单.md
- Type/category: Markdown registration stub; points to external PDF; Shadow chunk count: 2.

### 4. Document Pipeline check

- SOURCE_STATUS: B SOURCE_REGISTERED_ONLY
- Scan/parse/chunk/index assessment: B: 2026 work-plan/demonstration pages point to external PDFs
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] AI_存量知识库分类框架_系统生成.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=63
- [S2] AI_存量知识库分类框架_系统生成.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=63
- [S3] 关于印发中建三局2026年设计与技术工作计划的通知.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2
- [S4] 关于印发中建三局2026年设计与技术工作计划的通知.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=2
- [S5] 附件：公司2025年拟打造EPC设计管理示范项目清单.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=2

### 6. Document Link chain check

- Local Markdown pages contain source links, not the PDF requirements body.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-008

### 1. User question

2025年公司设计创效金额是多少元？

### 2. Current status

GENERATED

### 3. Correct answer existence

Conclusion: YES
Assessment: This is a positive control; numeric correctness still needs business confirmation.

- Candidate sources: final Evidence includes 2025 design-summary/related sources; exact numeric fact requires business verification.

### 4. Document Pipeline check

- SOURCE_STATUS: OK_INDEXED
- Scan/parse/chunk/index assessment: D/E: 2025 design-summary sources are indexed and final Evidence supports GENERATED
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence present

- [S1] 2025年饶淇述职.md | cited | role=汇报材料 | authority=L6 | chunks_for_path=8
- [S2] 2025年饶淇述职.md | candidate only | role=汇报材料 | authority=L6 | chunks_for_path=8
- [S3] 扬州十里外滩项目设计策划书2024.6.16(1).docx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=61
- [S4] 扬州十里外滩项目设计策划书2024.6.16(1).docx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=61
- [S5] 2025年设计管理总结.md | candidate only | role=汇报材料 | authority=L6 | chunks_for_path=9

### 6. Document Link chain check

- This is a positive control; numeric correctness still needs business confirmation.

### 7. Evidence Bundle check

- Correct evidence is present in final bundle.

### 8. Answer Engine check

- No failure observed; GENERATED output is a positive control. Human verification remains necessary.

## BA-009

### 1. User question

2026年4月EPC项目双周推进会上，给土木公司的督办是什么？

### 2. Current status

NO_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: The ledger body containing the civil-company supervision item is not in the corpus root.

- Candidate path: D:\设计管理\raw\设计管理服务台账\2026年4月.md
- Type/category: Markdown registration stub; points to external company service-ledger XLSX; Shadow chunk count: 2.

### 4. Document Pipeline check

- SOURCE_STATUS: B SOURCE_REGISTERED_ONLY
- Scan/parse/chunk/index assessment: B: April 2026 service-ledger Markdown points to an external XLSX
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 04天津华苑教育园项目（北京）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=189
- [S2] 04天津华苑教育园项目（北京）.pptx | candidate only | role=项目案例 | authority=L4 | chunks_for_path=189
- [S3] log.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=26
- [S4] log.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=26
- [S5] EPC项目设计管理方法与实务.md | candidate only | role=管理指南 | authority=L2 | chunks_for_path=5

### 6. Document Link chain check

Assessment: The ledger body containing the civil-company supervision item is not in the corpus root.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## BA-010

### 1. User question

星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？

### 2. Current status

PARTIAL_EVIDENCE

### 3. Correct answer existence

Conclusion: YES
Assessment: The entity page links to the raw value-list stub, which links to an external XLSX. Final Evidence stops at query/entity/concept pages.

- Entity page: D:\设计管理\wiki\entities\新洲星谷科创中心项目.md
- Raw stub: D:\设计管理\raw\设计支持\设计价值创造\新洲星谷科创中心价值创造清单.md
- Link chain: Wiki entity -> raw value-list stub -> external XLSX. Entity page has 5 chunks; raw stub has 2 chunks; actual XLSX body is not in Shadow.

### 4. Document Pipeline check

- SOURCE_STATUS: B SOURCE_REGISTERED_ONLY + H LINK_FAILURE
- Scan/parse/chunk/index assessment: B/E: entity/query/raw stub pages are indexed; actual external value-list XLSX body is absent
- For current final Evidence items, source paths exist and have Shadow chunks; this does not prove the missing answer-bearing source body was indexed.

### 5. Retrieval chain check

- BM25 Top: NOT_RECORDED (not re-run)
- Dense Top: NOT_RECORDED (not re-run)
- Hybrid Top: NOT_RECORDED (not re-run)
- Reranker Top: NOT_RECORDED (not re-run)
- Correct chunk rank: BM25/Dense/Hybrid/Reranker = NOT_RECORDED
- Final Evidence Bundle assessment: correct-source evidence absent or incomplete

- [S1] 设计创效价值创造问答.md | cited | role=标准模板 | authority=L3 | chunks_for_path=11
- [S2] 设计创效价值创造问答.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=11
- [S3] 新洲星谷科创中心项目.md | candidate only | role=项目案例 | authority=L4 | chunks_for_path=5
- [S4] 新洲星谷科创中心项目.md | cited | role=项目案例 | authority=L4 | chunks_for_path=5
- [S5] 设计价值创造.md | candidate only | role=标准模板 | authority=L3 | chunks_for_path=5

### 6. Document Link chain check

- The entity page links to the raw value-list stub, which links to an external XLSX. Final Evidence stops at query/entity/concept pages.

### 7. Evidence Bundle check

- Correct answer-bearing evidence is not present in final bundle.

### 8. Answer Engine check

- No primary Answer Engine failure established; upstream source/retrieval/link issue dominates.

## 4. Priority recommendations

### P0 - Business-blocking

1. Import external PDF/DOCX/XLSX bodies referenced by link-only registration pages, then verify parse, SourceBlock, Chunk and Shadow indexing.
2. Add controlled Wiki/entity/query -> raw source expansion and retain an explicit failure state when the target is external or missing.
3. Distinguish source registration from source body availability in ingestion audits.

### P1 - Quality-impacting

1. Persist per-question BM25/Dense/Hybrid/Reranker Top-K traces; current artifacts cannot prove rank-level root causes without re-running.
2. Prefer direct source bodies over generic PPTs, logs, entity pages and link-only registration notes in Evidence selection.
3. Treat valid Evidence plus incomplete answer sections as a separate Answer Engine diagnostic, as seen in BA-001.

### P2 - Experience improvements

1. Display source status, body availability, chunk count and Evidence status to business users.
2. Explain NO_EVIDENCE, PARTIAL_EVIDENCE and STRUCTURE_INVALID with actionable next steps.

## 5. Next-stage advice (diagnosis only)

- Fix source-body ingestion and external-link handling before tuning Retrieval metrics.
- Add Retrieval trace persistence before claiming BM25/Dense/Reranker root causes.
- Use BA-001 and BA-008 as positive controls; use BA-002/003/006/007/009/010 as source/link-chain tests.
- Do not implement changes until this audit is reviewed by the business owner.

