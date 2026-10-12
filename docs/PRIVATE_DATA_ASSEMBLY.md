# 公开代码与私有资料怎样装配

供维护人员使用。公开代码包含通用功能，原始资料、摘录、索引、模型、来源映射和运行记录留在受控本机。本次没有上传可直接复刻业务知识库的私有固定包。

## 公开开发检查

使用项目Python环境安装 `requirements.txt` 和 `requirements-dev.txt`（若存在），运行合成测试与前端构建：

```powershell
python -m pytest tests/public_release tests/test_docx_loader.py tests/test_markdown_loader.py tests/test_wps_loader.py tests/test_atomic_evidence.py tests/test_candidate_fusion_v2.py tests/test_hierarchical_retrieval_v1.py tests/test_structured_v2.py tests/test_new05_runtime_scope.py -q
Set-Location knowledge-ui
npm ci
npm run build
```

上面为最初专项检查命令。W批已处理原18项未通过检查；当前213项公开回归的完整命令见[W版修复说明](SHARED_JUDGMENT_REPAIR_20261012.md)，第一次发布结果保留在[原发布记录](PUBLISH_20261012.md)。公开测试只用合成资料、临时目录与替身检索引擎，不调用付费问答接口。

## 固定包准备

1. 从公开分支取得程序、脚本和网页源码，按本机实际Python、模型、配置与运行数据路径装配私有运行目录。
2. 将 `deployment/private_package/start_release.py`、`state_recovery.py` 放在包根目录，将 `release_adapter.py` 放入 `runtime`。网页构建结果放入该运行目录的 `knowledge-ui/dist`。
3. 在受控环境生成来源目录、候选、原文证据、表格行与向量，绑定来源版本；保留现有正式数据，不能拿空的公开目录覆盖它。
4. 私有 `project_navigation.json` 绑定候选及项目来源版本；`assessment_handoff.json` 保存已核对报告、位置与来源指纹。读取器会检查身份和版本，不接受仅改文件名替换原件。
5. 评估读取器当前适配特定报告表格结构，不承诺任意报告自动识别。新模板需先校验章节、表格与行位置，不能只把新文件塞进旧映射。
6. 方案比选使用已核对的主题映射。公开实现不内置真实项目及原文中的方案标识；在私有案例对象增加下面的 `comparison_topic_specs`，其引用文字必须确实出现在对应来源项中。

以下全为合成示例，不能直接当业务数据：

```json
{
  "comparison_topic_specs": [
    {
      "source_item_id": "ITEM-ALPHA",
      "subject": "演示对象",
      "baseline_reference": "方案甲",
      "candidate_reference": "方案乙"
    }
  ]
}
```

7. 按装配后的实际文件重新生成私有清单及SHA-256，不能借用原V包指纹为修改后的公开副本背书。私有包清单、案例JSON及导航JSON不得提交GitHub。
8. 明确设置 `RAG_EXPECTED_CANDIDATE_HASH`、`RAG_RELEASE_TARGET`、`RAG_EMBEDDING_MODEL_PATH`。候选指纹必须和私有清单一致；缺少或不一致应阻止启动。
9. 默认运行 `python start_release.py` 只读预检，保存结果。正式8000的 `--serve` 还要核对独立授权文件中的具体包清单指纹、端口、目标目录、状态和恢复范围；不能用公开模板中的示例替代批准材料。
10. 新副本先在隔离环境测试，核查原件下载、拒绝越界、同版引用、导出、状态保留与回退。浏览器实际操作和用户业务确认单独做完，再决定是否采用。

本次公开版对私有映射作了外置处理，并保留远端可编辑试用的反馈审核功能；因此它与本机冻结V包不是同一批字节，必须生成新包身份。真实资料和派生文本的公开边界见[数据政策](PUBLIC_REPOSITORY_DATA_POLICY.md)。

## X版候选整理

实际问题的候选、审核和事件写入独立运行状态的 `growth` 目录；不写冻结来源、知识卡、向量或正式索引。先复制运行状态快照，在另一个输出目录整理：

```powershell
python -m scripts.run_knowledge_growth_v1 --runtime-state <STATE_JSON> --trace-dir <TRACE_DIR> --source-manifest <CANDIDATE_MANIFEST_JSON> --candidate-hash <完整64位数据候选指纹> --output <独立输出目录>
```

历史记录不借当前版本补来源；技术、未分类以及范围外问题不自动产生业务候选。重复执行保留审核与事件，去重按提问编号、问题范围和来源版本处理；不支持会丢审核上下文的旧 `--rebuild` 用法。不要让离线脚本与服务同时写同一个候选目录。

X版新增合成测试在 `tests/public_release/test_controlled_growth.py`；通用自生长、试用反馈与存储测试亦须运行。当前286项公开回归、本机498项回归与各项限制见[X版说明](CONTROLLED_GROWTH_20261012.md)。
