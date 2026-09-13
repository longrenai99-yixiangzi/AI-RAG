# Knowledge OS V2.6 Final Release Report

## 当前状态

**BLOCKED — STOP_AFTER_T03_LIVE_SHADOW_GATE**

T00 基线已冻结，T01 Source Version Gate 已通过。随后检查真实试用记录：去重后只有 15 个有效问题，低于任务书规定的最低 30 个；同时 V2.5 答案分支尚未接入 8010，因此不能把离线检索预览冒充 Live Shadow。

按门禁规则，T04 Rollback Drill、8010 受控切换、Immediate Smoke、Canary 均未执行。

## A. Source Version

五个 Owner Gold Source 均由用户明确批准：以当前物理文件 SHA-256 作为 `CONTENT_HASH effective_version`，`approval_status=APPROVED`。

- Source Version Gate：`PASS`
- 已记录 reviewer、reviewed_at、SHA-256 与 BA 追溯关系。
- 该确认不等于授权切换 8010。

## B. Live Shadow

本次从 `logs/trial/trial_audit.jsonl` 与 `data/trial_feedback/feedback.jsonl` 提取真实历史问题，去重后得到：

- 有效唯一问题：15
- 目标样本：100
- 最低有效样本：30
- 自动造题：无
- 重复刷题：无
- 状态：`SHADOW_INSUFFICIENT_SAMPLE`

当前只完成了 BM25 诊断预览，未运行 V2.5 Live Answer Engine，因此不能给出 Verified New Hit、Verified Lost Hit 或可比延迟结论。

8010 当前仍是 V1 Primary，监听 `127.0.0.1:8010`；8000 未监听。

## C. Rollback Drill

未执行真实 `V1 → V2.5 → V1` 演练。V2.5 原有 Rollback Preparation 仍是 READY，但本轮不能将 READY 冒充 PASS。

## D. Candidate Integrity

V2.5 Candidate 保持冻结，未创建新的 V2.6 Retrieval Candidate：

- Candidate hash：`26928685b69d167a99289a26776b6e0712531f79eaed71effc553bd37543ce03`
- Source/semantic-chunk hash：`850748257c8e5f31263933f0ee76bd43fae39c4ab7f340862e03532b824fc714`
- Dense embedding hash：`c1a4e81b7e2541e9d5534265c6adbfd709d0eb753ff219a53ecae461ee0be4af`
- Candidate manifest hash：`3aabe7cb218f9b025815b2a4182e42398460c830159491a3f0c4ef4368057136`

## E. Controlled Switch

未获得“允许切换 8010”的授权，且 Live Shadow Gate 未通过，因此没有切换。V1 Config、V1 Index、V1 Runtime Package 保持不变。

## F. Immediate Smoke

未执行。必须在 Live Shadow Gate、Rollback Drill Gate 及明确切换授权通过后执行。

## G. Canary

未执行。没有把离线 Holdout、历史 Regression 或 BM25 预览冒充 Canary。

## H. Final Status

`BLOCKED`

阻塞项：

1. Live Shadow 有效唯一问题样本仅 15 个，低于最低门槛 30。
2. V2.5 答案引擎尚未接入 8010 Live Runtime。
3. 任务书禁止重复刷题、自动造题或以 Offline Shadow 冒充 Live Shadow。

## T00 基线

| 项目 | 值 |
|---|---|
| Git HEAD | `a1a4fe835a32ed40c1f894c8f8aeadd28cab5c0a` |
| V1 runtime config hash | `32157ac3ff5c517acd7df38751e07eed628420a17856b59a10eec7e4e3af84e3` |
| V1 index hash | `bec5d84131181d0149e29382c2e0079764d4f5462fe4f454a615c1e631a125bf` |
| 8010 | V1 Primary，LISTENING |
| 8000 | OFF，未监听 |
| 正式 Qdrant/SQLite 写入 | OFF |

## 下一步

需要继续积累至少 30 个不重复的真实业务问题，并将 V2.5 答案分支以只读 Shadow 方式接入 8010。达到条件后，才能继续 T04 Rollback Drill。

## 交付物

- `evaluation/knowledge_os_v2_6/release_baseline.json`
- `evaluation/knowledge_os_v2_6/source_version_policy.json`
- `evaluation/knowledge_os_v2_6/owner_source_version_approval.json`
- `evaluation/knowledge_os_v2_6/live_shadow_runs.jsonl`
- `evaluation/knowledge_os_v2_6/live_shadow_report.json`
- `evaluation/knowledge_os_v2_6/final_release_gate.json`
- `docs/LIVE_SHADOW_REPORT.md`
- `docs/8010_CONTROLLED_SWITCH_PLAN.md`
- `docs/8010_ROLLBACK_PLAN.md`
