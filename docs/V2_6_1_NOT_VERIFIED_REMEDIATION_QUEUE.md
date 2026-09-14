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
- Gold：`Q03`；目标来源：``wiki/concepts/设计支持/方案比选库.md` → 核心要点`
- Gold 标准答案：覆盖 18+ 项高频比选内容；每项字段为"专业类别 / 比选项目 / 方案一到三 / 比选分析（技术）/ 比选分析（商务）/ 比选结果 / 比选阶段"。

## V261-LSR-003

- 问题：设计策划评审由谁牵头？哪些单位参与？评审后形成几项督办？
- 根因：`QUERY_INTENT_SCOPE_MISMATCH`
- 证据判断：V2 confused design-planning review with generic design evaluation.
- 下一步：Add a design-planning-review intent facet and require participant and follow-up evidence from the same source.
- V1 来源：`['中建三局EPC项目设计管理指南2023.06.docx']`
- V2.6.1 来源：`['《项目设计管理手册》.pdf']`
- Gold：`Q06`；目标来源：``wiki/concepts/设计支持/设计策划评审.md` → 核心要点`
- Gold 标准答案：由设计与技术支持中心牵头，总承包支持中心、区域供应链管理中心、分公司商务中心等参与；评审后形成 7 项督办修改事宜（限 6.1–6.15 完成）：补充总图、明确设计现状与先导段、增加组团开发及标段划分、分阶段明确设计专业人员数量、明确与业主/设计沟通机制、完善策划点（增市政道路/景观绿化专业）、提前介入勘察。

## V261-LSR-004

- 问题：设计任务书汇编收录了多少个项目的任务书？覆盖哪些业态？
- 根因：`SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY`
- 证据判断：V2 returned a folder pointer, not the task-book body needed for project and typology counts.
- 下一步：Parse the task-book compilation source and derive counts and typologies from body evidence.
- V1 来源：`['全专业施工图审核要点提示汇编（2026年）.xlsx', '全专业施工图审核要点提示汇编（2026年）.xlsx', '全专业施工图审核要点提示汇编（2026年）.xlsx']`
- V2.6.1 来源：`['EPC项目设计管理流程.md']`
- Gold：`Q07`；目标来源：``wiki/sources/设计任务书汇编.md` → 关键内容 / 涉及项目业态`
- Gold 标准答案：26 个项目；覆盖新能源（风电、光伏、储能）、教育（高校、中小学）、医疗、产业园区、市政与城市更新（旧改、地下通道）、商业。

## V261-LSR-005

- 问题：孝感奥体项目 50 米游泳池铺砖完成后，两端池壁间距的精度要求是多少？
- 根因：`SOURCE_BODY_OR_LOCATION_MISMATCH`
- 证据判断：V2 cited an experience index and links but did not provide the requested pool-wall precision fact.
- 下一步：Parse the Xiaogan PDF and require a numeric page/line evidence window for the precision claim.
- V1 来源：`['公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司体育场馆产品线设计创效案例汇编模板（案例示例） - 成果.pptx']`
- V2.6.1 来源：`['孝感奥体体育工艺经验交流.md']`
- Gold：`Q51`；目标来源：``b6077e3f74f0a1b7ae9f.md` → 五、质量管理 / 3、质量管控重点——泳池`
- Gold 标准答案：自水面上 0.3m 至水面下 0.8m 范围内，两端池壁间距须控制在最小 50.02m～最大 50.03m；池体专用瓷砖主砖规格 244mm×119×9mm，厚度不小于 8.6mm，吸水率 E≤0.5%，需符合国家强制 3C 认证。

## V261-LSR-006

- 问题：沈阳中心大厦的设计创效成果中，各专业分别优化了多少金额？
- 根因：`QUERY_SCOPE_AND_AGGREGATION_MISMATCH`
- 证据判断：V2 returned company-wide totals instead of Shenyang Center Tower per-specialty amounts.
- 下一步：Bind the Shenyang source and use project-scoped table aggregation; reject company-wide fallback.
- V1 来源：`['中建三局EPC项目设计创效管理指南（试行版）0414.docx']`
- V2.6.1 来源：`['2025年设计管理总结.md']`
- Gold：`Q70`；目标来源：``cb93c382c9197043cab1.md` → 03 设计阶段成果 / 设计创效（Page 34）`
- Gold 标准答案：全专业联合成本相较方案估算阶段优化合计超 1 亿元。分项：主体结构（节点优化、含钢量优化）6000 万元；幕墙（主材、辅材、玻璃配置）3000 万元；机电（系统、设备配置）2000 万元；LEED 铂金优化为金级 1200 万元；电梯轿厢优化载重 800 万元；擦窗机优化数量 400 万元。

## V261-LSR-007

- 问题：海南中心塔冠施工设置多少个支撑胎架？针对主梁变形采取了什么措施？
- 根因：`PROJECT_RETRIEVAL_MISMATCH`
- 证据判断：V2 answered an unrelated anti-floating question instead of the Hainan Tower crown support-frame fact.
- 下一步：Add project identity rescue for Hainan Center and require the same-project structural evidence.
- V1 来源：`['医疗产品线项目设计建设标准参考手册（1.0版） （定稿）20240911.docx']`
- V2.6.1 来源：`['04天津华苑教育园项目（北京）.pptx']`
- Gold：`Q77`；目标来源：``f80e5def25e5a56bfc6f.md` → 4.前置风险识别、5.塔冠方案详解（Page 23、34）`
- Gold 标准答案：共设 22 个胎架，采用塔吊标准节与自制调节段相结合、销轴连接，分为胎座、标准节、胎帽、调整段。采用 midas Gen 开展全施工阶段工况模拟仿真，主梁 Z 向变形 max=22.5mm，解决方案为工厂预起拱 40mm，并在梁底部增设 D300*16mm 圆管斜撑回顶。

## V261-LSR-008

- 问题：设计管理策划书通常包含哪几个章节板块？
- 根因：`SOURCE_ROLE_OR_RENDERING_GAP`
- 证据判断：V2 had supporting chapter-row excerpts but did not promote the canonical eight-section list to a direct answer.
- 下一步：Mark the canonical design-planning source as direct for chapter-list queries and preserve section-row evidence.
- V1 来源：`['log.md']`
- V2.6.1 来源：`['设计管理策划章节问答.md', '设计管理策划章节问答.md', '设计管理策划章节问答.md']`
- Gold：`Q29`；目标来源：``wiki/queries/设计管理策划章节问答.md` → 一、标准策划书 8 章节`
- Gold 标准答案：8 个章节板块——项目概况、设计策划目标、设计组织策划、设计合约规划、设计风险识别、设计方案比选策划、设计创效点策划、报批报建管理。库内最完整实例为扬州十里外滩项目设计策划书（2024.6.16）。

## V261-LSR-010

- 问题：设计与技术支持中心的组织架构和人员配置是怎样的？
- 根因：`SOURCE_BODY_OR_ROLE_MISMATCH`
- 证据判断：V2 returned a general center description and omitted organization and staffing details.
- 下一步：Use the approved organization-optimization source page and render organization, staffing, and optional-post boundaries separately.
- V1 来源：`['中建三局第二建设公司设计与技术支持中心组织优化及运行方案.pdf']`
- V2.6.1 来源：`['设计与技术支持中心.md', '设计与技术支持中心.md']`
- Gold：`Q09`；目标来源：``wiki/organizations/设计与技术支持中心.md` → 组织定位与架构 / 人员配置（同见 `wiki/concepts/设计管理体系/法人管项目.md`）`
- Gold 标准答案：为公司设计与技术管理部二级部室；下设 4 个设计支持工作小组（房建 18 人、市政 6 人、专项 9 人、新兴业务小组）+ 1 个技术支持工作小组（8 人）；中心编制 56 人、现阶段配置 48 人（经理 1、副经理 1、助理 2、设计支持 36、技术支持 8）；总部设苏州（设计支持 24 + 技术支持 8），分中心设武汉（设计支持 12）。

## V261-LSR-011

- 问题：材料设备报审中，专项施工图出图后的时限要求是什么？海外项目有何不同？
- 根因：`QUERY_INTENT_SCOPE_MISMATCH`
- 证据判断：V2 returned curtain-wall review timing and unrelated schedule rows, not material-equipment approval timing and overseas variation.
- 下一步：Add a material-equipment-approval intent and require both domestic and overseas timing evidence.
- V1 来源：`['附件1：中建三局2025年设计管理工作计划 (1).pdf']`
- V2.6.1 来源：`['202407幕墙设计专业培训.pptx', '202407幕墙设计专业培训.pptx', '04天津华苑教育园项目（北京）.pptx']`
- Gold：`Q40`；目标来源：``0ee2959550610ce23750.md` → 二、9.1 材料设备报审的管理流程`
- Gold 标准答案：专项施工图出图后 30 天内完成首批视觉样板确认，2 个月内完成全部材料认样、封样；海外项目材料设备报审应在该项采购前 3～4 个月完成，定制加工的材料/设备要提前 6～12 个月以上。

## V261-LSR-012

- 问题：海外全模块化数据中心的模块构成、数量与最大重量是多少？
- 根因：`SOURCE_BODY_MISSING_OR_PROJECT_MISMATCH`
- 证据判断：V2 returned hospital logistics and transport weights, not the overseas modular data-center module inventory.
- 下一步：Admit the overseas modular data-center source and bind module, quantity, and maximum-weight fields.
- V1 来源：`['潜江市中心医院工程总承包EPC项目设计计划.docx']`
- V2.6.1 来源：`['公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx', '医疗专项设计管理分享（丽水医院）.pptx']`
- Gold：`Q58`；目标来源：``2c5dbe10c9b44d1d47d0.md` → 三（二）全模块化施工案例（Page 39）`
- Gold 标准答案：主楼由 3 个结构层、6 个模块层组成，结构层高 6.9m，每层 163 个标准模块，所有机电管线均预集成于模块内部。模块合计 1080 个：上模块 SC 489 个/最大 40.4 吨，下模块 MC 491 个/最大 51.3 吨，屋面撬块 SS 88 个/24.8 吨，蓄冷罐 CT 12 个/20 吨。

## V261-LSR-013

- 问题：2024 年二公司设计创效累计金额与创效率是多少？
- 根因：`METRIC_PERIOD_OR_DEFINITION_CONFLICT`
- 证据判断：V2 treated cumulative amount and efficiency as an unresolved conflict instead of two requested 2024 metrics.
- 下一步：Separate cumulative amount from efficiency and enforce 2024 scope before conflict detection.
- V1 来源：`['《项目设计管理手册》.pdf']`
- V2.6.1 来源：`['《项目设计管理手册》.pdf', '2024年度总结2.md']`
- Gold：`Q80`；目标来源：``raw/工作总结/2024年年度总结.md` → 一、（三）夯实总部支撑（另见 `37746aede39d6b33f745.md`）`
- Gold 标准答案：落实设计创效建议 2851 条，累计创效约 2.35 亿元，设计创效率 4.24%，同比提升 0.84 个百分点；指导扬州十里外滩、深圳宝安工业上楼等 31 个项目制定设计价值创造清单。

## V261-LSR-014

- 问题：2024 年二公司完成多少个项目标前概算分析与评审？中标情况如何？
- 根因：`SOURCE_AND_NARRATIVE_AGGREGATION_GAP`
- 证据判断：V2 returned an EPC table excerpt but missed the 100-project and 31-win narrative facts.
- 下一步：Bind the 2024 annual-summary evidence and keep the two requested facts as separate claims.
- V1 来源：`['2024年度总结2.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`
- Gold：`Q81`；目标来源：``raw/工作总结/2024年度总结2.md` → 标前概算精准管控（另见 `e0d9ad43a1f66a2d8531.md`）`
- Gold 标准答案：累计完成 100 个项目标前概算分析与评审，中标 31 项，总金额 219.2 亿元。

## V261-LSR-015

- 问题：2024 年上半年二公司完成多少次标前成本测算评审与图纸估概算评审？
- 根因：`TIME_SCOPE_SOURCE_MISMATCH`
- 证据判断：V2 returned a 2024 project-list row instead of the 2024 H1 review counts 37 and 13.
- 下一步：Prefer the 2024 H1 summary for this period-specific fact and reject project-list rows as substitutes.
- V1 来源：`['2024年半年总结.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`
- Gold：`Q86`；目标来源：``raw/工作总结/2024年半年总结.md` → （四）做实设计管理，提升后台赋能（另见 `e1f57b2f1862b9e921b2.md`）`
- Gold 标准答案：标前成本测算评审 37 次，设计阶段图纸及估概算评审 13 次；累计提出优化建议 1015 条，采纳 747 条，采纳率 73.6%；另发出概算预警单 4 项，召开 4 次 EPC 项目专题推进会。

## V261-LSR-016

- 问题：2025 年上半年二公司新开 EPC 项目设计策划完成情况如何？
- 根因：`TIME_SCOPE_SOURCE_MISMATCH`
- 证据判断：V2 returned a 2024 project-list table for a 2025 H1 EPC design-planning completion question.
- 下一步：Use the 2025 H1 summary and preserve the completion-status evidence window.
- V1 来源：`['2025年半年总结.md']`
- V2.6.1 来源：`['设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx', '设计阶段EPC项目清单-2024年7月.xlsx']`
- Gold：`Q89`；目标来源：``raw/工作总结/2025年半年总结.md` → 一、（二）项目管理不断夯实（另见 `55122ed33fea8877f535.md`）`
- Gold 标准答案：新开 EPC 项目 100% 开展设计策划，设计价值创造策划 850 条，预计创效 9409 万元。

## V261-LSR-017

- 问题：2025 年二公司钢筋平均创效率是多少？多少个项目超 16%？
- 根因：`METRIC_FACET_CONFLICT`
- 证据判断：V2 mixed steel-average efficiency and overall efficiency facts from different metric facets.
- 下一步：Model steel-average efficiency and count-over-16% as separate claims under 2025 scope.
- V1 来源：`['2026年二季度半年运营会资料汇编（隐藏版）.pdf']`
- V2.6.1 来源：`['2025年饶淇述职.md', '2024年度总结2.md', '2025年设计管理总结.md']`
- Gold：`Q95`；目标来源：``raw/工作总结/2025年年度总结.md` → "三优一创"稳步提升`
- Gold 标准答案：钢筋平均创效率 9.66%，11 个项目钢筋内外结算量效益超 16%，"三优一创"整体创效率 3.33%。

## V261-LSR-018

- 问题：铁投·书香林语项目屋面花架优化的做法与降低造价金额是多少？
- 根因：`TABLE_ROW_SCOPE_MISMATCH`
- 证据判断：V2 exposed multiple roof-decoration rows, including an unrelated 742.71万元 value, instead of one project-row answer.
- 下一步：Select the exact Iron-Investment project row and bind original method, optimized method, and 50万元 result together.
- V1 来源：`['01铁投·书香林语（华中）.pptx']`
- V2.6.1 来源：`['01铁投·书香林语（华中）.pptx', '01铁投·书香林语（华中）.pptx', '01铁投·书香林语（华中）.pptx']`
- Gold：`Q107`；目标来源：``wiki/.../铁投·书香林语（华中）.md` → 第 7 页 2.概算控制方法及实施结果`
- Gold 标准答案：原设计屋面花架外挑宽度 1.5m，优化后 1.2m；经与设计沟通不影响外观效果、业主同意修改，降低造价 50 万元，同时减少施工工期、降低机械费用、减少安全风险。

## V261-LSR-019

- 问题：EPC 项目设计管理流程包含哪 8 个环节？哪个环节资料量最大？
- 根因：`SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY`
- 证据判断：V2 returned process-folder pointers but not the eight stages and largest-material-volume fact.
- 下一步：Parse the canonical EPC design-management process body and add a stage-level evidence map.
- V1 来源：`['中船风电哈密市15万千瓦风储一体化项目设计任务书.docx']`
- V2.6.1 来源：`['EPC项目设计管理流程.md', 'EPC项目设计管理流程.md', 'EPC项目设计管理流程.md']`
- Gold：`Q129`；目标来源：``wiki/topics/EPC项目设计管理流程.md` → 全流程框架 1～8`
- Gold 标准答案：8 个环节——设计策划（10 个项目）、方案比选（20 个项目）、设计任务书（26 个项目）、设计计划、报批报建、相关方沟通、设计评估与质量管控、限额设计与价值创造。设计任务书环节资料量最大，为 26 个项目。

## V261-LSR-020

- 问题：2026 年上半年中建三局打造了多少个 BIM 应用示范工程？同期改革管理论坛发布什么文件？
- 根因：`MULTI_SOURCE_PERIOD_GAP`
- 证据判断：V2 returned BIM requirements but not the H1 project count plus the same-period forum document.
- 下一步：Answer as two separately cited claims: 2026 H1 BIM count and forum publication, each with period-scoped evidence.
- V1 来源：`['局2026年第二次改革管理论坛会议资料（一）孙志凌.pdf']`
- V2.6.1 来源：`['3.二公司：2026年设计与技术专项责任书 .docx', '3.二公司：2026年设计与技术专项责任书 .docx', '关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx']`
- Gold：`Q130`；目标来源：``.ai-growth/parsed/approved-sources/77d7e542b45a93853e16.md` → 一、（二）；`90b557ce19fb9d757b47.md` → 会议概况`
- Gold 标准答案：出台 BIM 提升方案，打造 21 个 BIM 应用示范工程；2026 年第二次改革管理论坛 3500 余人（现场+视频）参会，会上设计与技术部发布了《项目深化设计管理指南》。
