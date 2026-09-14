# V2.6.1 NOT_VERIFIED 修复队列

- 条数：`18`
- 分类：`{'SOURCE_BODY_MISSING_OR_STRUCTURED_GAP': 1, 'QUERY_INTENT_SCOPE_MISMATCH': 2, 'SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY': 2, 'SOURCE_BODY_OR_LOCATION_MISMATCH': 1, 'QUERY_SCOPE_AND_AGGREGATION_MISMATCH': 1, 'PROJECT_RETRIEVAL_MISMATCH': 1, 'SOURCE_ROLE_OR_RENDERING_GAP': 1, 'SOURCE_BODY_OR_ROLE_MISMATCH': 1, 'SOURCE_BODY_MISSING_OR_PROJECT_MISMATCH': 1, 'METRIC_PERIOD_OR_DEFINITION_CONFLICT': 1, 'SOURCE_AND_NARRATIVE_AGGREGATION_GAP': 1, 'TIME_SCOPE_SOURCE_MISMATCH': 2, 'METRIC_FACET_CONFLICT': 1, 'TABLE_ROW_SCOPE_MISMATCH': 1, 'MULTI_SOURCE_PERIOD_GAP': 1}`
- 状态：所有条目保持 `OPEN_REMEDIATION`，未自动改写答案或 Gate。

## V261-LSR-002

- 问题：《设计方案比选提示清单》覆盖多少项比选内容？每项包含哪些字段？
- 根因：`SOURCE_BODY_MISSING_OR_STRUCTURED_GAP`
- 证据判断：V2 returned a topic list instead of the requested count and fields.
- 下一步：Admit and parse the actual design-option checklist body; bind table headers and rows before answering.
- V1 来源：`['中建三局EPC项目设计管理指南2023.06.docx']`
- V2.6.1 来源：`['方案比选库.md']`

## V261-LSR-003

- 问题：设计策划评审由谁牵头？哪些单位参与？评审后形成几项督办？
- 根因：`QUERY_INTENT_SCOPE_MISMATCH`
- 证据判断：V2 confused design-planning review with generic design evaluation.
- 下一步：Add a design-planning-review intent facet and require participant and follow-up evidence from the same source.
- V1 来源：`['中建三局EPC项目设计管理指南2023.06.docx']`
- V2.6.1 来源：`['《项目设计管理手册》.pdf']`

## V261-LSR-004

- 问题：设计任务书汇编收录了多少个项目的任务书？覆盖哪些业态？
- 根因：`SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY`
- 证据判断：V2 returned a folder pointer, not the task-book body needed for project and typology counts.
- 下一步：Parse the task-book compilation source and derive counts and typologies from body evidence.
- V1 来源：`['全专业施工图审核要点提示汇编（2026年）.xlsx', '全专业施工图审核要点提示汇编（2026年）.xlsx', '全专业施工图审核要点提示汇编（2026年）.xlsx']`
- V2.6.1 来源：`['EPC项目设计管理流程.md']`

## V261-LSR-005

- 问题：孝感奥体项目 50 米游泳池铺砖完成后，两端池壁间距的精度要求是多少？
- 根因：`SOURCE_BODY_OR_LOCATION_MISMATCH`
- 证据判断：V2 cited an experience index and links but did not provide the requested pool-wall precision fact.
- 下一步：Parse the Xiaogan PDF and require a numeric page/line evidence window for the precision claim.
- V1 来源：`['公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx']`
- V2.6.1 来源：`['孝感奥体体育工艺经验交流.md']`

## V261-LSR-006

- 问题：沈阳中心大厦的设计创效成果中，各专业分别优化了多少金额？
- 根因：`QUERY_SCOPE_AND_AGGREGATION_MISMATCH`
- 证据判断：V2 returned company-wide totals instead of Shenyang Center Tower per-specialty amounts.
- 下一步：Bind the Shenyang source and use project-scoped table aggregation; reject company-wide fallback.
- V1 来源：`['中建三局EPC项目设计创效管理指南（试行版）0414.docx']`
- V2.6.1 来源：`['2025年设计管理总结.md']`

## V261-LSR-007

- 问题：海南中心塔冠施工设置多少个支撑胎架？针对主梁变形采取了什么措施？
- 根因：`PROJECT_RETRIEVAL_MISMATCH`
- 证据判断：V2 answered an unrelated anti-floating question instead of the Hainan Tower crown support-frame fact.
- 下一步：Add project identity rescue for Hainan Center and require the same-project structural evidence.
- V1 来源：`['医疗产品线项目设计建设标准参考手册（1.0版） （定稿）20240911.docx']`
- V2.6.1 来源：`['04天津华苑教育园项目（北京）.pptx']`

## V261-LSR-008

- 问题：设计管理策划书通常包含哪几个章节板块？
- 根因：`SOURCE_ROLE_OR_RENDERING_GAP`
- 证据判断：V2 had supporting chapter-row excerpts but did not promote the canonical eight-section list to a direct answer.
- 下一步：Mark the canonical design-planning source as direct for chapter-list queries and preserve section-row evidence.
- V1 来源：`['log.md']`
- V2.6.1 来源：`['设计管理策划章节问答.md', '设计管理策划章节问答.md', '设计管理策划章节问答.md']`

## V261-LSR-010

- 问题：设计与技术支持中心的组织架构和人员配置是怎样的？
- 根因：`SOURCE_BODY_OR_ROLE_MISMATCH`
- 证据判断：V2 returned a general center description and omitted organization and staffing details.
- 下一步：Use the approved organization-optimization source page and render organization, staffing, and optional-post boundaries separately.
- V1 来源：`['中建三局第二建设公司设计与技术支持中心组织优化及运行方案.pdf']`
- V2.6.1 来源：`['设计与技术支持中心.md', '设计与技术支持中心.md']`

## V261-LSR-011

- 问题：材料设备报审中，专项施工图出图后的时限要求是什么？海外项目有何不同？
- 根因：`QUERY_INTENT_SCOPE_MISMATCH`
- 证据判断：V2 returned curtain-wall review timing and unrelated schedule rows, not material-equipment approval timing and overseas variation.
- 下一步：Add a material-equipment-approval intent and require both domestic and overseas timing evidence.
- V1 来源：`['附件1：中建三局2025年设计管理工作计划 (1).pdf']`
- V2.6.1 来源：`['202407幕墙设计专业培训.pptx', '202407幕墙设计专业培训.pptx', '04天津华苑教育园项目（北京）.pptx']`

## V261-LSR-012

- 问题：海外全模块化数据中心的模块构成、数量与最大重量是多少？
- 根因：`SOURCE_BODY_MISSING_OR_PROJECT_MISMATCH`
- 证据判断：V2 returned hospital logistics and transport weights, not the overseas modular data-center module inventory.
- 下一步：Admit the overseas modular data-center source and bind module, quantity, and maximum-weight fields.
- V1 来源：`['潜江市中心医院工程总承包EPC项目设计计划.docx']`
- V2.6.1 来源：`['公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '医疗专项设计管理分享（丽水医院）.pptx']`

## V261-LSR-013

- 问题：2024 年二公司设计创效累计金额与创效率是多少？
- 根因：`METRIC_PERIOD_OR_DEFINITION_CONFLICT`
- 证据判断：V2 treated cumulative amount and efficiency as an unresolved conflict instead of two requested 2024 metrics.
- 下一步：Separate cumulative amount from efficiency and enforce 2024 scope before conflict detection.
- V1 来源：`['《项目设计管理手册》.pdf']`
- V2.6.1 来源：`['《项目设计管理手册》.pdf', '2024年度总结2.md']`

## V261-LSR-014

- 问题：2024 年二公司完成多少个项目标前概算分析与评审？中标情况如何？
- 根因：`SOURCE_AND_NARRATIVE_AGGREGATION_GAP`
- 证据判断：V2 returned an EPC table excerpt but missed the 100-project and 31-win narrative facts.
- 下一步：Bind the 2024 annual-summary evidence and keep the two requested facts as separate claims.
- V1 来源：`['2024年度总结2.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`

## V261-LSR-015

- 问题：2024 年上半年二公司完成多少次标前成本测算评审与图纸估概算评审？
- 根因：`TIME_SCOPE_SOURCE_MISMATCH`
- 证据判断：V2 returned a 2024 project-list row instead of the 2024 H1 review counts 37 and 13.
- 下一步：Prefer the 2024 H1 summary for this period-specific fact and reject project-list rows as substitutes.
- V1 来源：`['2024年半年总结.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`

## V261-LSR-016

- 问题：2025 年上半年二公司新开 EPC 项目设计策划完成情况如何？
- 根因：`TIME_SCOPE_SOURCE_MISMATCH`
- 证据判断：V2 returned a 2024 project-list table for a 2025 H1 EPC design-planning completion question.
- 下一步：Use the 2025 H1 summary and preserve the completion-status evidence window.
- V1 来源：`['2025年半年总结.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`

## V261-LSR-017

- 问题：2025 年二公司钢筋平均创效率是多少？多少个项目超 16%？
- 根因：`METRIC_FACET_CONFLICT`
- 证据判断：V2 mixed steel-average efficiency and overall efficiency facts from different metric facets.
- 下一步：Model steel-average efficiency and count-over-16% as separate claims under 2025 scope.
- V1 来源：`['2026年二季度半年运营会资料汇编（隐藏版）.pdf']`
- V2.6.1 来源：`['2025年饶淇述职.md', '2024年度总结2.md', '2025年设计管理总结.md']`

## V261-LSR-018

- 问题：铁投·书香林语项目屋面花架优化的做法与降低造价金额是多少？
- 根因：`TABLE_ROW_SCOPE_MISMATCH`
- 证据判断：V2 exposed multiple roof-decoration rows, including an unrelated 742.71万元 value, instead of one project-row answer.
- 下一步：Select the exact Iron-Investment project row and bind original method, optimized method, and 50万元 result together.
- V1 来源：`['01铁投·书香林语（华中）.pptx']`
- V2.6.1 来源：`['01铁投·书香林语（华中）.pptx', '01铁投·书香林语（华中）.pptx', '01铁投·书香林语（华中）.pptx']`

## V261-LSR-019

- 问题：EPC 项目设计管理流程包含哪 8 个环节？哪个环节资料量最大？
- 根因：`SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY`
- 证据判断：V2 returned process-folder pointers but not the eight stages and largest-material-volume fact.
- 下一步：Parse the canonical EPC design-management process body and add a stage-level evidence map.
- V1 来源：`['中船风电哈密市15万千瓦风储一体化项目设计任务书.docx']`
- V2.6.1 来源：`['EPC项目设计管理流程.md', 'EPC项目设计管理流程.md', 'EPC项目设计管理流程.md']`

## V261-LSR-020

- 问题：2026 年上半年中建三局打造了多少个 BIM 应用示范工程？同期改革管理论坛发布什么文件？
- 根因：`MULTI_SOURCE_PERIOD_GAP`
- 证据判断：V2 returned BIM requirements but not the H1 project count plus the same-period forum document.
- 下一步：Answer as two separately cited claims: 2026 H1 BIM count and forum publication, each with period-scoped evidence.
- V1 来源：`['局2026年第二次改革管理论坛会议资料（一）孙志凌.pdf']`
- V2.6.1 来源：`['3.二公司：2026年设计与技术专项责任书 .docx', '3.二公司：2026年设计与技术专项责任书 .docx', '关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx']`
