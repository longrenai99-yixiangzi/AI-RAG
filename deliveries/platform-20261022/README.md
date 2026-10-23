# 本机知识库平台交付快照 · 2026-10-22

本交付保存本轮平台、检索与答复治理的通用实现及处理记录索引。仅面向设计管理、已有资料、本地单用户；技术管理和科技管理暂不建设。上传源码不等于切换正式服务、发布业务知识或完成全库业务验收。

## 为什么独立存放

本机开发基线与公开分支已分别演进，公开分支还清理过私有资料历史。本次从公开分支 `10e74c7` 创建交付，不合并旧克隆历史，不覆盖仓库根目录的另一套成果。`runtime/` 是本机工作版的公开源码副本；根目录原系统继续保留。它们不是已经合并、可互换的同一运行版本。

## 成果与记录

- [完成内容与使用边界](COMPLETED_WORK.md)
- [分阶段处理台账](PROCESSING_RECORD.md)
- [受证据约束的大模型答复方案](EVIDENCE_CONSTRAINED_ANSWER_PLAN.md)
- [简短答复协议实现与验证](CONCISE_IMPLEMENTATION.md)
- [真实验证请求准备与执行边界](REAL_VALIDATION_PREPARATION.md)
- [两题真实结果与离线修复](REAL_VALIDATION_RESULT.md)
- [两题业务确认与独立试用](OWNER_CONFIRMED_TRIAL.md)
- [项目金额字段与引用修复](PROJECT_MONEY_PRECISION.md)
- [试用覆盖检查与面积范围保护](TRIAL_COVERAGE_REVIEW.md)
- [限额日常模型答复与授权边界](DAILY_MODEL_POLICY.md)
- [日常模型已启用及首条真实验证](DAILY_MODEL_ACTIVATION.md)
- [六项扩展检查与未解决缺口](DAILY_TOPIC_COVERAGE.md)
- [公开源码清单及校验值](source-manifest.json)
- [本机处理产物的脱敏索引](processing-ledger.json)
- [本次交付验证](VALIDATION.md)

公开副本移除了真实目录、来源映射和业务样本内容，替换为示例。`source-manifest.json` 同时记录本机文件与公开文件校验值，明确标记转换。模型权重、索引、向量、原件、业务分类清单、问题和答复明细、逐题人工复核、运行日志、备份和付费调用包均不公开。处理索引用不可读的文件标识和内容哈希关联本机留存文件；它不是原始证据备份，也不能据此还原业务内容。

## 验证与运行

从 `runtime/` 运行，Python 环境按 `requirements.txt` 安装。源码保留了本地模型推理接口，但纯合成测试无需加载权重或调用公网模型。

```powershell
python -m pytest tests/test_platform_workbench.py tests/test_platform_completion.py tests/test_platform_existing_content.py tests/test_concise_extract.py tests/test_source_field_answer.py tests/test_personnel_scope.py tests/test_scalar_bridge.py tests/test_existing_text_answers.py tests/test_unified_candidate.py tests/test_assisted_chat.py tests/test_trial_knowledge_store.py -q
```

工作台前端单独构建，不运行读取私有分类数据的通用 `prebuild`：

```powershell
cd knowledge-ui
npm ci
npx tsc -b
npx vite build --config vite.platform.config.ts --outDir ../evaluation/platform_workbench_20261021/platform-dist
```

公开副本包含仅有合成示例的分类快照，只供编译与演示；它不表示已经装配真实知识库。演示入口 `python -m uvicorn app.trial.platform_app:demo_app --factory --host 127.0.0.1 --port 8896 --workers 1` 仅在该端口空闲时手动使用，生成独立演示数据。合成演示不能证明真实来源的问答效果。

真实模式还需要私有固定候选索引、同型号模型权重、来源版本映射、分类契约、工作台状态及本机环境。`live_app` / `unified_preview` 中的固定目录来自受控本机装配，不是公共克隆一键运行承诺。不要直接运行附带的既有资料启动脚本，直到这些依赖和端口归属逐一核对。真实数据接回前核对路径、哈希、向量维度及引用版本，不重建或切换现有索引。首次源码导出没有切换在线服务；随后建立独立试用入口，并在金额修复时仅重启8897，既有检索、工作台与正式服务边界保持。

2026-10-23追加：日常模型策略已接入独立试用，保持待批准；需要本机私有资料版本清单及明确费用授权。通用实现与未完成验证见[限额日常模型](DAILY_MODEL_POLICY.md)。

后续用户已明确批准，独立试用的日常模型已启用，并完成1次真实生成及2条本地保护检查；详见[启用记录](DAILY_MODEL_ACTIVATION.md)。不覆盖此前待批阶段的原始记录或历史失败。

2026-10-23同章汇聚与意图识别修复已在本机试用加载，实际限制及验证见[修复记录](SECTION_INTENT_REPAIR.md)。

已补齐日常策略有效时按批准版本优先检索，并对实际模型漏答子问做离线保护；实际结果为部分答复，见[范围与缺口修复](APPROVED_SCOPE_RETRIEVAL.md)。

后续5题技术检查发现并修复主题错配，只对1题执行模型，4题仍未答或受限；结果不计作独立业务验收，见[新问题检查](NEW_QUESTION_TOPIC_CHECKS.md)。

新增固定版本的新问句复核：1项流程答复核对通过、1项时间保护、2项人工预检失败，代码与进程保持不变。计数及剩余缺口见[冻结版本复核](FROZEN_VERSION_REVIEW.md)。

同节表格关联和明确并列子问覆盖已修复；原题自动形成有据部分答复及缺口，实际1次模型请求通过，见[表格与子问修复](SECTION_TABLE_FACETS.md)。

现有资料限用版收尾：统一8897日常入口、显式续批与历史账本保护，修复内容清单旁及主题和谓语省略拆问。最终566项后端检查通过；一次模型技术对照及三项无模型边界检查完成，业务和界面交互确认仍待收口，见[限用版收尾](LIMITED_RELEASE_CLOSEOUT.md)。

业务负责人后续否定上轮两题的依据/适用范围：旧题不计业务通过，已限定项目并改按手册模板出题，证据不足项获确认；本轮无新增模型调用，见[业务范围修订](OWNER_SCOPE_REVIEW.md)。

后续已将必要的资料用途/项目范围约束接入8897及共用检索：本地、审核复用、日常生成及旧预览均检查。最终593项后端通过，本轮真实模型调用0次；效力、章节完整性和业务验收仍不自动成立，见[运行时适用约束](EVIDENCE_APPLICABILITY.md)。

后续已分开默认本地检索和模型外发白名单，并在生成前核对完整清单；原问题本地直接答复，原文版本校验保留。最终615项后端通过，本轮模型请求0次，见[本地范围与清单修复](LOCAL_RETRIEVAL_COMPLETE_LIST.md)。
