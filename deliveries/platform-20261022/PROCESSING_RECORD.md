# 分阶段处理台账

原始记录保留本机；本文件记录处理目的、实现与边界。`processing-ledger.json` 覆盖各阶段留存产物的文件标识、校验值及历史测试计数，不含逐题原文。计数可能重复、包含失败轮次，不相加、不替代业务验收。本轮发布另行验证公开副本。

| 阶段目录 | 工作及处理决定 |
| --- | --- |
| platform_compat_20261018 | 先建立分类契约、入库范围与平台兼容规则；原件路径稳定，分类浏览不等于正式知识。 |
| source_completion_20261018 | 核对已有正文与索引是否被使用，仅补真正缺失的来源链。 |
| markdown_chain_20261019 | 追查 Markdown、转换稿、原件与实际引用间的关联。 |
| markdown_holdout_20261019 / markdown_holdout_round2_20261019 | 用不同问题检查转换和引用链，区分已有内容未被使用与真正解析缺陷。 |
| section_retrieval_20261019 | 章节范围、标题层级、父子证据及同源展开。 |
| scalar_completion_20261019 | 数值字段与主体、单位、阶段绑定，保护不完整统计。 |
| browser_trial_20261019 / cross_source_browser_20261019 | 实际浏览器检验原文引用、跨来源召回及不完整答复展示。 |
| unified_colleague_flow_20261019 | 将同事方案中的问答交互、模型入口和检索处理映射到现有接口，保留原检索资产。 |
| focused_holdout_20261019 | 新主题回归；模型调用采用逐批、冻结内容、限次数及预算的审核。 |
| unified_entry_20261020 | 资料浏览和问答共用同一版本候选；本地检索与公网生成状态分开。 |
| docx_hybrid_20261020 | Word 正文、原生表格、表头与行上下文并用；不只信转换后的段落。 |
| personnel_scope_20261020 | 岗位人数与阶段、专兼职绑定；不足以计算总人数时停止推算。 |
| scope_grounding_fix_20261020 | 避免相关背景混入答案及跨范围借值。 |
| answer_contract_20261020 / v2_answer_boundary_20261020 | 区分可答、部分可答、证据缺口；检查模型格式、证据标识及条件，不靠放宽验证制造成功。 |
| business_scope_20261021 | 界定本轮可用资料及业务范围，避免宣称整库已准备完成。 |
| parse_cache_audit_20261021 | 核对转换缓存、原文变化与索引版本，防止修改旧文件后继续使用旧结果。 |
| reference_binding_20261021 | 登记页仅作导航线索，答案追溯到同版本正文；原文与转换稿分别显示。 |
| personnel_answer_20261021 / personnel_scope_holdout_20261021 | 人员配置答复与范围负例；复用已验证的原生字段。 |
| platform_workbench_20261021 | 先用合成数据建立登记、审核、发布、反馈、任务、备份恢复闭环。 |
| platform_existing_content_20261021 | 在不重建整库的条件下接入已有资料检索；题目先留存，再执行并保存失败状态。 |
| platform_completion_20261021 | 增量入库、版本失效、生命周期、恢复和模型原文单元协议；格式失败保留记录，离线修复不冒充新真实调用。 |
| platform_closeout_20261022 | 启停与恢复收尾、数值桥接、引用可读名称及本机业务复核处理。 |
| platform_concise_20261022 | 本地简洁摘录、岗位与并列结构保护；旧记录保留，新查询使用修复逻辑。 |
| usable_scope_20261022 | 提出适用资料范围；范围清单不等于已经对运行库施加强制过滤。 |
| project_area_precision_20261022 | 面积单字段提取、项目案例隔离、条件与单位保护；未实现字段明确列为尚未提取。 |
| grounded_concise_20261022 | 用户确认后增加简短答复、逐项短引文核对、改写回退及生成失败回退；仅合成与离线验证，不调用公网或切换服务。 |
| concise_real_validation_20261022 | 冻结两题真实请求和总额度；预检实际证据、原件关联与核价；修复多行证据误判路径。准备与预检不代表授权调用或业务验收。 |
| concise_trial_20261022 | 两条离线回放经Owner核对后，按校验值导入独立试用历史；浏览引用与外发预览可用，后台模型执行关闭，原工作台保持。 |
| project_money_precision_20261022 | 已找到证据而金额未提取的修复；复用项目范围及金额标签，核对单位、指标、地块与版本，修正原文链接，保留旧失败，仅重启独立试用入口。 |
| trial_coverage_20261022 | 冻结12项既有/邻行/范围技术检查；区分数量格式误报与面积范围实错，补齐共用面积保护，核对引用版本；不当作独立新题或模型验收。 |
| daily_answer_policy_20261022（续至20261023） | 日常模型有限资料、期限与预算策略；复用逐项证据协议及调用计次，增加原子预占、来源停用/变更和备份恢复保护。构建与接口验证通过，待批准，真实调用0，界面自动检查受阻。 |
| daily_answer_activation_20261023 | 依据新的明确限期授权启用日常模型；真实生成1次，短引文和原文版本核对通过；金额直答与证据缺口保护不新增模型调用；无重试或付费修复。 |
| daily_answer_topics_20261023 | 冻结6项扩展检查，仅1次新增真实生成；区分可答、保护性受限与未通过，定位一般方法意图和父子章覆盖问题；登记检索反馈，无代码变更或付费修复。 |
| knowledge_os_system_audit / knowledge_os_v2_6 / verified_answer_engine_v2 | 留存此前版本与治理诊断；不将历史候选或旧验收结论套用为当前平台状态。 |

后续优先补齐通用的证据约束答复流程，再用未参与开发的新业务问题检验。当前没有因发布 GitHub 而自动扩大数据外发、调用预算、业务知识发布或正式部署范围。

新增处理阶段 `section_intent_fix_20261023`：区分方法问法与具体对象比较；同源同版父章说明汇聚、缺项和附表提示；保留独立引用，新增13项检查，全部506项通过，1次授权真实生成核对；原记录与额度保留。

新增处理阶段 `approved_scope_retrieval_20261023`：批准版本候选池过滤、标题与同章范围一致、评价维度聚焦、请求范围隔离；保留1次真实响应及漏答事实，离线回放改为部分答复，无追加模型调用。

新增处理阶段 `new_business_probes_20261023`：检索前冻结5项问题，发现2项主题错配及规范化拼词边界，补共用检查；533项后端检查通过，实际模型1次，原始失败与受限结果保留，不作为独立新题验收。

新增处理阶段 `frozen_version_review_20261023`：检索前冻结4条新问句及70个核心文件哈希，整轮不改代码、问题或进程；1次真实生成核对6项引文和关键限制，另1项时间保护、2项人工预检失败；未以原题修复重测冒充独立通过。

新增处理阶段 `section_table_facets_20261023`：复用已有表格行与拆问，关联同源同版同节证据，排除表头、保留整行条件，自动记录并列缺口及失败回退字段；550项检查通过，真实模型1次，待补反馈仅记录未发布知识。

现有资料限用版收尾：统一8897日常入口、显式续批与历史账本保护，修复内容清单旁及主题和谓语省略拆问。最终566项后端检查通过；一次模型技术对照及三项无模型边界检查完成，业务和界面交互确认仍待收口，见[限用版收尾](LIMITED_RELEASE_CLOSEOUT.md)。

业务负责人后续否定上轮两题的依据/适用范围：旧题不计业务通过，已限定项目并改按手册模板出题，证据不足项获确认；本轮无新增模型调用，见[业务范围修订](OWNER_SCOPE_REVIEW.md)。

后续已将必要的资料用途/项目范围约束接入8897及共用检索：本地、审核复用、日常生成及旧预览均检查。最终593项后端通过，本轮真实模型调用0次；效力、章节完整性和业务验收仍不自动成立，见[运行时适用约束](EVIDENCE_APPLICABILITY.md)。

后续已分开默认本地检索和模型外发白名单，并在生成前核对完整清单；原问题本地直接答复，原文版本校验保留。最终615项后端通过，本轮模型请求0次，见[本地范围与清单修复](LOCAL_RETRIEVAL_COMPLETE_LIST.md)。

Current limited-trial UI, backup/restore and runtime readiness checks: [verification and limits](LIMITED_READINESS_VERIFICATION.md). Backend baseline unchanged; no new model HTTP calls.

Owner follow-up: both reviewed historical answers and their sources are accepted, within their stated lecture context. See [two-answer acceptance scope](OWNER_ANSWER_ACCEPTANCE.md); three content limitations remain.

Explicit appendix outline retrieval is live, with detailed-content gaps kept partial and local: [behavior and validation](APPENDIX_OUTLINE.md). Final backend: 627 checks; this phase added no real model calls.

Titled numbered PDF explanations are now selectable as bounded primary evidence, preserving the existing topic and source guards: [implementation and validation](PDF_NUMBERED_NOTES.md). Final backend: 639 checks; no new real model HTTP calls.

Direct requirements/practices/content lookups now retain a full-topic necessity check; the audited unsupported project question refuses unrelated submission evidence: [audit and validation](DIRECT_TOPIC_GUARD.md). Backend: 646 checks; no new real model HTTP calls.

Native column-label lookup and a visible, version-checked source-page image preview are live: [scope and final validation](NATIVE_TABLE_SCHEMA.md). Final backend: 671 checks. Current approval and expiry are preserved; no new real model calls.

Existing accepted-answer lifecycle: [isolated real-content drill and boundaries](REVIEWED_KNOWLEDGE_LIFECYCLE.md). Eleven assertion groups passed; no runtime change, new model call or live publication. Prior backend result retained separately.

Browser lifecycle and readable source-name propagation: [interaction evidence and scope](BROWSER_REVIEW_LIFECYCLE.md). Eight browser check groups and final exported backend 673 checks passed. Only the daily workbench restarted; no live business publication or new model call.
