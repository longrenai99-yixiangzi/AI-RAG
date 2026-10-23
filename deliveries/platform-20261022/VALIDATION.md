# 交付副本验证记录 · 2026-10-22

检查对象为本目录的公开源码副本，不是只沿用原工作区历史结果。

| 检查 | 结果 |
| --- | --- |
| `runtime` 下 `python -m pytest tests -q` | 最新493项通过，3条依赖弃用提示。仅覆盖本交付附带的测试，不是根目录另一版本的全部测试。 |
| `knowledge-ui` 下 `node --test tests/assistedChat.test.mjs` | 3 项通过；测试中断、拆分帧和无效完成状态。 |
| `knowledge-ui` 下 `tsc -b` | 通过；使用合成分类快照，不读取业务资料库。 |
| `vite build --config vite.platform.config.ts` | 工作台构建通过；构建产物留本地，不上传生成包。 |
| 密钥形状、个人目录、内部 HTTP 地址和已知业务标识扫描 | 本轮公开源码清单扫描未命中；这是有边界的检查，不宣称能发现一切敏感文本。 |
| Git 白名单 | 只增加本交付与入口文档；不合并旧历史，不上传数据目录和运行产物。 |

首次导出遗漏分类规则 YAML，造成相关检查失败；补齐规则后继续验证。后续发现两份试验源码未导出、一个旧测试依赖私有真实请求包，分别补齐通用实现并将该测试改为自行生成合成请求，保留了价格哈希不匹配的拒绝检查。合成分类快照最初为空导致 TypeScript 推断失败，补为明确的合成样例后通过。前端依赖本机离线缓存不完整，按锁文件安装依赖后完成验证。

没有跳过失败测试、降低业务范围保护或发送额外模型请求来取得通过。失败轮次原始 XML、最终 XML 与构建产物保留在本地交付目录，因为包含本机路径，不进入公开仓库。

公开副本清除了私有来源映射、业务示例和本机目录，关闭历史试用配置里的公网生成及已批准来源列表。它与在线工作区有明确差异，差异通过 `source-manifest.json` 的两组哈希记录。没有对当前在线源码做这些导出转换。

后续经用户另行批准执行了2次真实公网生成，原始在线校验均失败，离线修复后以同一批原始响应回放通过。详见[真实结果记录](REAL_VALIDATION_RESULT.md)；没有追加调用，没有完整私有包冷启动、真实库重新入库或正式服务切换。未重新进行全部真实业务题验收，也未将技术检查结果转成全库正确率。

金额修复阶段重新运行公开副本全部后端测试：450项通过、3条依赖提示。另在本机完成原问题浏览器提交、原文接口版本核对及5项接口技术回归。前端未修改，表内前端检查沿用此前同一源码的结果，本阶段未重复执行。旧失败、备份与验证明细保留本机；详见[金额修复](PROJECT_MONEY_PRECISION.md)。

本轮试用覆盖修复后，正确复制最新源码到公开副本并重跑全部后端：459项通过，3条依赖提示。此前一次复制路径出错后的450项属于旧副本检查，未当作最终结果。12项本机复查及浏览器范围验证详见[覆盖记录](TRIAL_COVERAGE_REVIEW.md)。前端未改，未重复构建；未完成并发验收或真实模型新题验证。

2026-10-23限额日常模型阶段：公开副本最终493项通过，3条依赖提示，包含34项新增合成检查；TypeScript与工作台构建重新通过。实际HTTP验证未授权拦截和待批路由；浏览器检查被工具停止，不算界面验收。模型新请求0次，真实新题未验收。详见[日常策略记录](DAILY_MODEL_POLICY.md)。

获得明确批准后的启用阶段：首条实际模型HTTP1次，短引文与同版主证据匹配；另2条本地路由检查没有模型调用。前端隐藏日常启用状态下的旧逐题按钮，TypeScript及构建通过；后台逻辑未变，沿用493项结果。该次真实试用不自动计为Owner验收，见[启用记录](DAILY_MODEL_ACTIVATION.md)。

六项扩展检查阶段没有代码变更，因此未重复运行或增加后端/前端测试计数。只新增1次真实模型HTTP且引文匹配；其余结果含未答和未通过，不能计为六题模型验收通过，见[覆盖记录](DAILY_TOPIC_COVERAGE.md)。

2026-10-23同章汇聚与意图识别修复：公开副本全部后端506项通过，3条既有依赖提示；5项真实仅检索回归，1次授权模型调用覆盖3个子节且引文匹配。未进行独立新题Owner验收或浏览器交互验收，前端未改。方法题首选来源仍受白名单限制，详见[修复记录](SECTION_INTENT_REPAIR.md)。

批准范围检索阶段最终525项后端检查通过、3条既有依赖提示，新增19项。7项在线仅检索回归完成；真实模型1次的整题覆盖未通过，新增谓词保护后离线回放为PARTIAL，未再次调用模型。浏览器交互和Owner新题验收仍未完成，见[范围与缺口修复](APPROVED_SCOPE_RETRIEVAL.md)。

新问题主题检查阶段：公开副本最终533项通过、3条既有依赖提示，新增8项。5题预检后转为修复回归；实际HTTP1次取得4项匹配引文的场景内答复，另4题未答或受限且没有模型调用。未将5题合并计为正确率，见[检查记录](NEW_QUESTION_TOPIC_CHECKS.md)。

冻结版本复核阶段无代码变更，未重跑或增加此前533项后端计数。1项流程题实际模型HTTP1次，6项引文与关键限制核对；1项时间保护为0次模型；2项人工预检失败未提交模型，不算自动保护通过。70个核心文件哈希及进程保持，Owner验收仍未完成，见[冻结版本复核](FROZEN_VERSION_REVIEW.md)。

表格关联与子问覆盖修复阶段：公开副本最终550项通过、3条既有依赖提示，新增17项；7项仅检索回归，1次真实模型以完整表头/行引用形成PARTIAL并保留缺口。未记为独立新题Owner验收，前端未改，见[修复记录](SECTION_TABLE_FACETS.md)。

现有资料限用版收尾：统一8897日常入口、显式续批与历史账本保护，修复内容清单旁及主题和谓语省略拆问。最终566项后端检查通过；一次模型技术对照及三项无模型边界检查完成，业务和界面交互确认仍待收口，见[限用版收尾](LIMITED_RELEASE_CLOSEOUT.md)。

业务负责人后续否定上轮两题的依据/适用范围：旧题不计业务通过，已限定项目并改按手册模板出题，证据不足项获确认；本轮无新增模型调用，见[业务范围修订](OWNER_SCOPE_REVIEW.md)。

后续已将必要的资料用途/项目范围约束接入8897及共用检索：本地、审核复用、日常生成及旧预览均检查。最终593项后端通过，本轮真实模型调用0次；效力、章节完整性和业务验收仍不自动成立，见[运行时适用约束](EVIDENCE_APPLICABILITY.md)。

后续已分开默认本地检索和模型外发白名单，并在生成前核对完整清单；原问题本地直接答复，原文版本校验保留。最终615项后端通过，本轮模型请求0次，见[本地范围与清单修复](LOCAL_RETRIEVAL_COMPLETE_LIST.md)。

Current limited-trial UI, backup/restore and runtime readiness checks: [verification and limits](LIMITED_READINESS_VERIFICATION.md). Backend baseline unchanged; no new model HTTP calls.

Owner follow-up: both reviewed historical answers and their sources are accepted, within their stated lecture context. See [two-answer acceptance scope](OWNER_ANSWER_ACCEPTANCE.md); three content limitations remain.

Explicit appendix outline retrieval is live, with detailed-content gaps kept partial and local: [behavior and validation](APPENDIX_OUTLINE.md). Final backend: 627 checks; this phase added no real model calls.

Titled numbered PDF explanations are now selectable as bounded primary evidence, preserving the existing topic and source guards: [implementation and validation](PDF_NUMBERED_NOTES.md). Final backend: 639 checks; no new real model HTTP calls.
