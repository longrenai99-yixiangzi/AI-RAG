# Business Gold Owner Review Sheet

> 每题均为候选复核材料，不代表系统或业务负责人已经确认 Gold。

## BA-001

问题：设计任务书需要包含哪些内容？

最新验收 Artifact：`TASK-017E-1.2.1` / `evaluation/policy_facet_grounding/BA-001.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`《项目设计管理手册》.pdf`；root=`Root-002 frozen Shadow`；location=`{'page': 17}`
- `SUPPORTING_SOURCE`：`EPC设计管理复盘总结（光谷能源站).docx`；root=`Root-002 frozen Shadow`；location=`{'paragraph_start': 90, 'paragraph_end': 91}`
- `SOURCE_LINEAGE_ONLY`：`设计任务书.md`；root=`Root-001`；location=`{'line_start': 8, 'line_end': 10}`

最小引用位置：`[{'page': 17}, {'paragraph_start': 90, 'paragraph_end': 91}, {'line_start': 8, 'line_end': 10}]`

候选关键 Claims：包含项目概况、工作范围、工作要求、设计技术要点; 需明确设计依据及管控要求

适用 Scope：项目设计任务书管理；通用制度要求与项目复盘案例需分开表达。

Authority：PRIMARY=L2 管理手册；项目复盘与 Wiki 页仅作补充或来源链路。

当前运行是否应答：`ANSWERABLE`；预期行为：CLAIM_ANSWER_PATH；Provider 失败时保留 Evidence，不降级为知识不存在。

当前 Root 治理状态：`PENDING_APPROVAL`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得仅以 Wiki 概念页作为最终事实 Gold; 不得仅以单个项目复盘替代通用要求

系统置信度：`MEDIUM`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-002

问题：设计效益增量的计算方式？

最新验收 Artifact：`TASK-017C-2.1` / `evaluation/ba002_formula_semantic_alignment/BA-002.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`《项目设计管理手册》.pdf`；root=`Root-002 frozen Shadow`；location=`{'page': 30}`
- `SUPPORTING_SOURCE`：`设计创效价值创造问答.md`；root=`Root-001`；location=`{'line_start': 27, 'line_end': 35}`

最小引用位置：`[{'page': 30}, {'line_start': 27, 'line_end': 35}]`

候选关键 Claims：项目设计创效经济效益额=实施后实际经济效益额（不包括工期效益）-实施前预期经济效益额; 设计创效率=总创效金额/自施产值×100%; 设计效益增量与上述正式指标的术语映射尚未确认

适用 Scope：项目设计创效经济效益额与设计创效率的正式口径；不自动等同于“设计效益增量”。

Authority：PRIMARY=L2 管理手册；问答页只提供方法与量化维度。

当前运行是否应答：`ANSWERABLE`；预期行为：CLAIM_FORMULA_SEMANTIC_PATH；生成正式公式并保留 SEMANTIC_MAPPING_UNCONFIRMED 边界。

当前 Root 治理状态：`PENDING_APPROVAL`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得用项目案例替代正式公式; 不得把问答页作为公式主来源; 不得自行确认术语完全同义

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-003

问题：厂房产品线的方案比选案例包含哪些专业？

最新验收 Artifact：`TASK-017D` / `evaluation/p0_integrated_shadow_regression/BA-003.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`中建三局二公司产品线设计方案比选典型案例汇编（厂房）（正文）.docx`；root=`当前批准范围外`；location=`{'location': '厂房产品线专业目录/案例正文，待业务复核'}`
- `SOURCE_LINEAGE_ONLY`：`产品线设计方案比选典型案例汇编（厂房）.md`；root=`Root-001`；location=`{'line_start': 1, 'line_end': 1}`

最小引用位置：`[{'location': '厂房产品线专业目录/案例正文，待业务复核'}, {'line_start': 1, 'line_end': 1}]`

候选关键 Claims：仅以厂房案例正文实际列出的专业为准

适用 Scope：厂房产品线方案比选案例的专业目录。

Authority：正文案例库；Root-001 登记页只作来源链路。

当前运行是否应答：`SOURCE_SCOPE_MISSING`；预期行为：SAFE_REFUSAL / SOURCE_SCOPE_MISSING，不使用相近案例替代。

当前 Root 治理状态：`OUT_OF_SCOPE`；Truth Source：`KNOWN_OUT_OF_SCOPE`

绝不能使用：不得用医疗/学校产品线案例替代; 不得用登记页链接内容生成专业列表

系统置信度：`MEDIUM`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-004

问题：自动喷淋系统管材方案比选可采用哪几种方案进行比选？

最新验收 Artifact：`TASK-017C-3` / `evaluation/ba004_answer_structure_hardening/run_01.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`设计方案比选提示清单7.23.xlsx`；root=`Root-001`；location=`{'sheet_name': 'Sheet1', 'row_number': 89}`

最小引用位置：`[{'sheet_name': 'Sheet1', 'row_number': 89}]`

候选关键 Claims：传统镀锌钢管; 新型材料加强氯化聚氯乙烯(PVC-C)管材

适用 Scope：自动喷淋系统管材变更；DN80 以下支管适用条件需保留。

Authority：L3 标准模板/方案比选清单。

当前运行是否应答：`ANSWERABLE`；预期行为：OPTION_QUERY；后端确定性渲染两个方案及来源。

当前 Root 治理状态：`APPROVED`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得用其他消防系统或其他管材方案替代

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-005

问题：特殊环境条件下集电线路电气设计的图审要点有哪些？

最新验收 Artifact：`TASK-017E-1.1` / `evaluation/claim_preflight_positive_path/BA-005.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`未确认：特殊环境集电线路电气设计的正式图审依据`；root=`待补充`；location=`{'location': '待业务确认'}`
- `SUPPORTING_SOURCE`：`EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx`；root=`Root-001`；location=`{'role': '项目经验，仅作线索'}`

最小引用位置：`[{'location': '待业务确认'}, {'role': '项目经验，仅作线索'}]`

候选关键 Claims：待业务补充

适用 Scope：特殊环境条件下集电线路电气设计图审。

Authority：需 L2/L3 正式规范、图审要求或经批准技术标准。

当前运行是否应答：`AUTHORITY_INSUFFICIENT`；预期行为：AUTHORITY_INSUFFICIENT；返回缺少正式依据说明，不生成图审要点。

当前 Root 治理状态：`APPROVED`；Truth Source：`UNKNOWN`

绝不能使用：不得把项目经验、复盘或通用案例当作正式图审依据

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-006

问题：2026年局设计与技术系统的责任状要求DOP平台电子图形文件数据中心上传数量是多少？

最新验收 Artifact：`TASK-017E-1.1` / `evaluation/claim_preflight_positive_path/BA-006.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`局设计与技术系统责任状正文/目标数量资料（具体版本待业务确认）`；root=`当前正式批准范围外`；location=`{'field': 'DOP平台电子图形文件数据中心上传数量'}`

最小引用位置：`[{'field': 'DOP平台电子图形文件数据中心上传数量'}]`

候选关键 Claims：待业务补充

适用 Scope：2026年局级设计与技术系统责任状；组织范围必须为局级。

Authority：责任状正文或同范围正式目标文件。

当前运行是否应答：`SOURCE_SCOPE_MISSING`；预期行为：SOURCE_SCOPE_MISSING；安全拒答，不输出推测数量。

当前 Root 治理状态：`OUT_OF_SCOPE`；Truth Source：`KNOWN_OUT_OF_SCOPE`

绝不能使用：不得用项目级、二公司级或价值创造清单中的数量替代局级责任状目标

系统置信度：`MEDIUM`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-007

问题：2026年设计示范项目的打造要求是什么？

最新验收 Artifact：`TASK-017E-1.2.2` / `evaluation/policy_local_grounding_window/BA-007.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf`；root=`Root-002 frozen Shadow`；location=`{'page': 6, 'facet': 'COMPANY/DESIGN_MANAGEMENT'}`
- `PRIMARY_GOLD_CANDIDATE`：`关于印发中建三局2026年设计与技术工作计划的通知.pdf`；root=`Root-002 frozen Shadow`；location=`{'page': 4, 'facet': 'GROUP/DETAILED_DESIGN'}`

最小引用位置：`[{'page': 6, 'facet': 'COMPANY/DESIGN_MANAGEMENT'}, {'page': 4, 'facet': 'GROUP/DETAILED_DESIGN'}]`

候选关键 Claims：各主业公司打造不少于1个设计管理示范项目; 设计效益增量超*%或设计创效金额超**万; 聚焦深化设计计划管理等6大关键环节并制定标准化管控清单; 打造不少于1个深化设计示范项目

适用 Scope：2026年；必须区分二公司设计管理示范项目与局级深化设计示范项目，不可合并为单一要求。

Authority：两个来源均为 L2 管理指南；Root-002 governance=PENDING_APPROVAL。

当前运行是否应答：`ANSWERABLE`；预期行为：POLICY_QUERY；按两个已验证 Facet 分段回答并注明 Root-002 frozen Shadow governance。

当前 Root 治理状态：`PENDING_APPROVAL`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得把科技示范项目或 BIM 应用示范项目混入; 不得把公司与局级两个 Facet 合并成同一条要求

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-008

问题：2025年公司设计创效金额是多少元？

最新验收 Artifact：`TASK-017C-1.1` / `evaluation/direct_fact_scope_guard_hardening/BA-008.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`2025年饶淇述职.md`；root=`Root-001`；location=`{'line_start': 5, 'line_end': 7}`

最小引用位置：`[{'line_start': 5, 'line_end': 7}]`

候选关键 Claims：创效金额约4.45亿元; 确定性换算为约445,000,000元，并保留“约”

适用 Scope：二公司/公司级；2025年全年设计创效金额。

Authority：公司级年度述职/总结类来源；仅用于公司年度事实。

当前运行是否应答：`ANSWERABLE`；预期行为：DIRECT_FACT_CLAIM_PATH；后端确定性单位换算，Provider 不参与计算。

当前 Root 治理状态：`APPROVED`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得使用具体项目创效金额替代公司总额; 不得去掉“约”的限定

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-009

问题：2026年4月EPC项目双周推进会上，给土木公司的督办是什么？

最新验收 Artifact：`TASK-017E-1.1` / `evaluation/claim_preflight_positive_path/BA-009.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`2026年4月EPC项目双周推进会督办表/会议纪要正文（具体文件待业务确认）`；root=`当前批准范围外`；location=`{'target': '土木公司督办事项'}`

最小引用位置：`[{'target': '土木公司督办事项'}]`

候选关键 Claims：待业务补充

适用 Scope：2026年4月；EPC项目双周推进会；对象为土木公司。

Authority：会议纪要或督办表正文。

当前运行是否应答：`SOURCE_SCOPE_MISSING`；预期行为：SOURCE_SCOPE_MISSING；安全拒答并登记知识缺口。

当前 Root 治理状态：`OUT_OF_SCOPE`；Truth Source：`KNOWN_OUT_OF_SCOPE`

绝不能使用：不得用设计服务台账、通用工作计划或其他项目督办替代

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________

## BA-010

问题：星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？

最新验收 Artifact：`TASK-017D` / `evaluation/p0_integrated_shadow_regression/BA-010.json`

候选正确来源：
- `PRIMARY_GOLD_CANDIDATE`：`方案比选与价值创造清单方案比选及价值创造.xlsx`；root=`Root-002 frozen Shadow`；location=`{'sheet_name': '价值创造', 'row_start': 4, 'row_end': 87}`

最小引用位置：`[{'sheet_name': '价值创造', 'row_start': 4, 'row_end': 87}]`

候选关键 Claims：有效明细80条; 增加效益37条; 利润为空/未判定43条; 第88行公式汇总不计入明细

适用 Scope：星谷科创中心项目；价值创造 Sheet；不使用其他项目或方案比选 Sheet 的数字。

Authority：经业务负责人确认口径的原始 Workbook；Root-002 governance=PENDING_APPROVAL。

当前运行是否应答：`ANSWERABLE`；预期行为：FACT_ANSWER_PATH；后端确定性聚合和 Citation，不让 LLM 重算。

当前 Root 治理状态：`PENDING_APPROVAL`；Truth Source：`KNOWN_IN_SCOPE`

绝不能使用：不得使用 Root-001 登记页作为统计依据; 不得使用其他项目价值创造清单; 不得把第88行汇总公式视为一条明细

系统置信度：`HIGH`；Owner Confirmation：`UNCONFIRMED`

业务负责人选择：

[ ] 确认

[ ] 修改后确认

[ ] 不确认

业务负责人备注：

________________
