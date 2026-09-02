# V1.0 Internal Trial User Guide

## 1. 启动

双击：

```text
D:\AI智能体\AI设计管理RAG-V1\scripts\start_internal_trial.bat
```

或在 PowerShell 执行：

```powershell
& 'D:\AI智能体\AI设计管理RAG-V1\scripts\start_internal_trial.ps1'
```

启动成功后访问：

```text
http://127.0.0.1:8010/
```

Trial 不会自动启动或修改 `8000` 服务。

启动后首页为“企业知识库 / Knowledge OS”知识框架原型：

```text
/
```

原 Trial 问答页保留在：

```text
/trial
```

V0.1 知识框架页使用 Mock 数据，体现“知识框架 → 知识领域 → 知识节点 → 知识来源”的前端结构；不会替代现有 Trial 问答能力。

## 局域网访问

Trial Service 已监听局域网端口。与本机连接同一 Wi-Fi 的设备可访问：

```text
http://172.16.110.17:8010/
```

首次局域网访问前，请以管理员身份打开 PowerShell 后执行：

```powershell
& 'D:\AI智能体\AI设计管理RAG-V1\scripts\enable_internal_trial_lan.ps1'
```

该规则只允许本地子网访问 TCP 8010，不涉及正式 8000。

## 2. 可以试什么

- 证据检索和原文预览；
- 来源文件和定位查看；
- BA-002 确定性公式；
- BA-004 两种喷淋管材方案；
- BA-008 公司级 Direct Fact；
- BA-010 结构化 Fact Result；
- 安全拒答和生成服务不可用提示。

## 3. 建议试用问题

```text
设计效益增量的计算方式？
自动喷淋系统管材方案比选可采用哪几种方案进行比选？
2025年公司设计创效金额是多少元？
星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？
2026年设计示范项目的打造要求是什么？
```

## 4. 页面状态

- “已生成答案”：可以查看答案和引用；
- “当前知识库证据不足”：当前范围没有足够来源或权威依据；
- “已找到相关资料，但当前生成服务暂不可用”：Provider 依赖答案未开放，请查看 Evidence 原文，不要把它当成知识库没有答案。

Root-002 出现“Shadow资料 · 待审批”时，表示该资料尚未完成正式知识源审批。

## 5. 提交反馈

每题可选择：

- 正确；
- 部分正确；
- 错误；
- 没有回答我的问题；
- 引用不合适；
- 缺少资料。

反馈只写入：

```text
D:\AI智能体\AI设计管理RAG-V1\data\trial_feedback\feedback.jsonl
```

不会写回 `D:\设计管理`。

## 6. 停止

执行：

```powershell
& 'D:\AI智能体\AI设计管理RAG-V1\scripts\stop_internal_trial.ps1'
```

该脚本只停止 8010 Trial Service，不停止正式 8000 服务。
