# 已完成内容及限制

## 数据与分类

保留原件路径，以共享分类契约承载产品线、管理域、设计管理动作和浏览层级。导航与待审核内容不因出现在目录中就成为正式问答依据。区分原件、转换稿、经审核知识及引用线索，按来源和版本绑定，避免把登记页当正文回答。

## 检索与引用

复用既有 BM25、BGE-M3、RRF 和重排链，增加指定文件、章节、项目、人员、表格范围等约束。对原始 Word 表格补行列上下文，对需要核实的少量转换结果补解析，不因回答不好就重解析整库。引用保留真实显示名称、位置、来源版本及正文关联；摘要展示与完整证据分开保存。原文变化后旧的知识和引用不得继续冒充当前依据。

## 当前答复方式

日常问答当前主要是检索后本地摘录与规则整理。人员表格按完整、匹配阶段和岗位的原生行取值；金额和面积按主体、字段、条件、单位绑定，不跨项目借值，不把估算价当合同价，不把项目总人数当设计岗位合计。面积问题的修复还区分“证据不存在”和“相关原文已找到但字段尚未提取”。尚未提取的字段不计作已回答。随后补齐通用章节中的项目人民币金额提取及路径式引用标识适配，见[修复记录](PROJECT_MONEY_PRECISION.md)；不依赖固定项目或答案常量。

已实现对部分并列条目和岗位职责的简洁展示；完整引用仍保留。它不是通用语义摘要模型，不能外推为所有问题都能简洁、完整且正确回答。

## 平台闭环

- 来源登记、版本、项目及分类关联；资料浏览、问答、引用核对、历史记录、反馈。
- 草稿、提交审核、退回、批准、明确发布、撤回和历史版本；来源变更后的失效检查。
- 增量文件任务、解析、同模型编码、待激活、明确启用、重试、取消与撤回；不自动把候选变成正式业务知识。
- 状态和所属运行文件的备份、校验及恢复；恢复前安全副本与缺失文件处理。
- 本地启动、停止和检查入口；停止前检查正在执行的任务，核对进程归属，不按端口盲目结束进程。
- 模型调用预览、冻结请求、来源版本复核、预算与请求次数约束、审计及失败计次。

## 不能称为已完成的部分

本轮新增了简短答复、逐项引文核对和失败回退代码。随后经批准执行两次真实调用，原始在线校验均失败；修复后台误拒后，同一批原始响应离线回放通过，该原始批次的在线失败记录保持；后续在限额日常流程另完成1次新主题真实通路验证并启用日常策略，但尚未做系统性的独立新题业务验收。对任意自然语言改写的通用语义支持关系无法靠字面校验保证；不可靠的改写回退为原文短引文。工作台与原企业知识库 OS 的页面布局尚未统一。单机 JSON 状态不是多人权限系统，未完成企业级并发、账号权限、高可用与长期运行验收。

通过的合成测试、既有题复测、用户确认过的业务题和独立新题是不同证据，不能相加为问答正确率。原问题修改或同主题重复提问也不算独立新题。受控本机的业务复核明细继续保留本地，公开交付不重新发布其内容或裁定。

后续12项试用覆盖检查发现并修复面积子范围与整项目总量混用，完成9项主证据答复及3项范围保护的技术复查。结果与剩余限制见[覆盖检查](TRIAL_COVERAGE_REVIEW.md)；未扩大模型调用或业务验收范围。

已补齐日常模型的限额策略、白名单版本检查、原子预占、暂停恢复及备份不退额度，实现阶段保持待批准；后续已获明确批准并启用，系统性的真实新题业务验收仍未完成，见[实现记录](DAILY_MODEL_POLICY.md)。

用户后续明确批准后，限额日常模型已在独立试用启用；首条真实生成的短引文与当前主证据匹配，明确数值和证据不足继续本地处理。业务验收与浏览器交互验收仍分开，见[启用记录](DAILY_MODEL_ACTIVATION.md)。

后续六项扩展检查并未全部通过：2项有答复、2项保护性受限、2项意图或章节覆盖待修；只新增1次模型请求。已登记检索反馈，原文对照保留本机，具体缺口见[覆盖记录](DAILY_TOPIC_COVERAGE.md)。

已修复一般比较方法被误拦及父章节概览只取单节的问题。5项仅检索回归和1次真实模型路径检查完成，不计作独立新题或全库验收；当前白名单及附表覆盖限制见[修复记录](SECTION_INTENT_REPAIR.md)。

已实现批准范围先筛选再召回、标题及同章补证范围一致、缓存范围隔离。真实调用暴露子问漏答，原响应离线核对后标记部分答复；不计完整业务通过，详见[处理记录](APPROVED_SCOPE_RETRIEVAL.md)。

新增显式主题必要检查及标点边界保护，避免相似片段自动成为主证据。5题检查中1题形成可核对的场景内答复，4题保持缺口或范围限制，不合并为全部答对，见[检查记录](NEW_QUESTION_TOPIC_CHECKS.md)。

已完成固定版本4项新问句技术复核，并定位导语、同节表格和复合问题覆盖缺口。1题有据答复不等于全库验收；2项人工预检截停不等于自动拒答，见[复核记录](FROZEN_VERSION_REVIEW.md)。

已补齐同节相关业务行关联、完整表头/行引用、案例范围和缺失子问显示；真实回归结果为部分答复，不算整题或业务验收通过，见[修复记录](SECTION_TABLE_FACETS.md)。

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
