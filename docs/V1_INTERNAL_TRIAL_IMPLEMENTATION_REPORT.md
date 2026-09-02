# V1.0 Internal Trial Implementation Report

> TASK-019：将已验收 Shadow 能力封装为独立、只读、可回退、可审计的内部试用环境。

## 1. Implementation Scope

- Trial Service：`app/trial/main.py`，独立监听 `127.0.0.1:8010`。
- Formal Service：未启动、未修改、未占用 `8000`。
- Provider：Provider-dependent Claim 默认关闭，不发起真实 Provider 请求。
- Root-001：`D:\设计管理`，只读。
- Root-002：只作为 `Shadow资料 · 待审批` 展示，`PENDING_APPROVAL`。
- Root-003：Trial 不可用。
- Output：审计写入 `logs/trial`，反馈写入 `data/trial_feedback`，汇总写入 `evaluation/internal_trial`。

## 2. Added Files

| 文件 | 职责 |
|---|---|
| `config/internal_trial.yaml` | Trial 模式、Root、端口和写入边界 |
| `config/trial_users.yaml` | 2–3 名业务负责人白名单 |
| `app/trial/config.py` | Trial 配置和用户读取 |
| `app/trial/read_only_guard.py` | 启动前端口、Root、Shadow、预算和写入策略检查 |
| `app/trial/main.py` | 8010 FastAPI Trial Service、问答、审计、反馈和统计接口 |
| `app/trial/static/index.html` | 最小 Trial UI |
| `scripts/trial_readiness_check.py` | 输出 `TRIAL READINESS CHECK` |
| `scripts/start_internal_trial.ps1` | Windows 11 启动、自检、等待就绪和打开浏览器 |
| `scripts/start_internal_trial.bat` | 双击启动入口 |
| `scripts/stop_internal_trial.ps1` | 只停止 8010 Trial Service |
| `scripts/export_trial_feedback.py` | 导出 Trial Feedback Summary |

## 3. Trial Pipeline

```text
Trial UI
  -> /api/query
  -> existing Shadow Integrated Pipeline
  -> Provider disabled by Trial Mode
  -> deterministic path / safe refusal / evidence preview
  -> logs/trial/trial_audit.jsonl
```

没有新增 Retrieval 算法，没有修改 Router、Scope Guard、Policy Facet、Preflight、Fact Path 或正式链路。

## 4. User-facing States

| 内部状态 | 页面显示 |
|---|---|
| `GENERATED` / `FACT_RESULT` | 已生成答案 |
| `NO_EVIDENCE` / `PARTIAL_EVIDENCE` | 当前知识库证据不足 |
| `PROVIDER_TEMPORARY_FAILURE` / `PROVIDER_CIRCUIT_OPEN` / `PROVIDER_TEST_BUDGET_EXHAUSTED` | 已找到相关资料，但当前生成服务暂不可用 |

页面不显示 Python Exception、HTTP 502 堆栈或 JSON Schema 错误。

## 5. Evidence and BA-010 Audit

Evidence Card 展示：

- Source ID、文件名、文件类型；
- Knowledge Root 和 Governance；
- Document Role、Authority Level；
- PDF 页码、Word 段落/表格、Excel Sheet/Row、PPT Slide、Markdown 行号；
- 原文 excerpt。

BA-010 额外分开：

- `Fact Authority Source`：结构化事实计算依据；
- `Retrieval Context`：普通检索上下文。

没有修改 BA-010 的 80/37/43 计算逻辑。

## 6. Validation

- 启动自检：`READY`；
- `GET /`：HTTP 200；
- `GET /api/health`：HTTP 200；
- `GET /api/readiness`：HTTP 200；
- `GET /api/stats`：HTTP 200；
- `GET /api/feedback-summary`：HTTP 200；
- BA-002：Deterministic Formula 正常；
- BA-003：Safe Refusal 正常；
- BA-004：两种 OPTION 正常；
- BA-005：Authority Safe Refusal 正常；
- BA-007：Provider 关闭时显示 Generation Service Unavailable + Evidence Preview；
- BA-008：Direct Fact 正常；
- BA-010：Fact Result 正常并返回 Fact Authority Source；
- UTF-8 反馈：成功写入 Trial 反馈目录；
- Formal 8000：未修改、未停止、未占用。

## 7. Known Boundary

- 当前 Trial Service 复用已有 Shadow Pipeline，首次查询会加载 Shadow 模型，启动后保持内存态；
- Provider-dependent 普通 Claim 不可用，页面只展示证据和服务不可用提示；
- Root-002 不得被解释为正式知识源；
- Trial Feedback 只是反馈数据，不会自动进入知识库；
- 本任务不执行正式 Cutover。

