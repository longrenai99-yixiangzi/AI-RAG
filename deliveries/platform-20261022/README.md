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

真实模式还需要私有固定候选索引、同型号模型权重、来源版本映射、分类契约、工作台状态及本机环境。`live_app` / `unified_preview` 中的固定目录来自受控本机装配，不是公共克隆一键运行承诺。不要直接运行附带的既有资料启动脚本，直到这些依赖和端口归属逐一核对。真实数据接回前核对路径、哈希、向量维度及引用版本，不重建或切换现有索引。本轮交付没有启动、重启或切换任何在线服务。
