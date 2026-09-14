# Knowledge OS V2.6 Final Release Report

## 当前状态

**BLOCKED — T03 Live Shadow Gate**

V2.5 已冻结，V2.5 后台分支已接入 8010，且不改变用户看到的主回答。接入后共形成 144 条原始对照记录，去重后 131 个真实问题，样本数量门通过。

但当前仍有 2 条 V2.5 Shadow 异常：

- 1 条是接入初期的 `UnboundLocalError`，代码已修复；
- 1 条是结构化证据引用校验失败，表行映射已修复。

历史异常仍保留在审计记录中，不能直接抹掉，因此 Live Shadow Gate 目前仍为 `SHADOW_GATE_FAIL`。T04 Rollback Drill、8010 切换、Immediate Smoke 和 Canary 未执行。

## A. Source Version

五个 Owner Gold Source 已由用户明确批准以当前物理文件 SHA-256 作为 `CONTENT_HASH effective_version`，Source Version Gate：`PASS`。该确认不等于授权切换 8010。

## B. Live Shadow

| 指标 | 结果 |
|---|---:|
| 原始对照记录 | 144 |
| 去重后有效样本 | 131 |
| 样本数量门 | PASS |
| 来源可比样本 | 119 |
| 来源 Agreement | 40/119（33.61%） |
| New Hit 候选 | 8（已核验 3 条 VERIFIED_NEW_HIT） |
| Lost Hit 候选 | 13（已核验 2 条 VERIFIED_LOST_HIT） |
| V1 Answered Rate | 57.25% |
| V2.5 Answered Rate | 53.44% |
| V1 Latency P50/P95 | 1085.341 / 1514.09 ms |
| V2.5 Latency P50/P95 | 111.98 / 158.648 ms |
| V1 Error Rate | 0.76% |
| V2.5 Error Rate | 1.53% |
| Live Shadow Gate | `SHADOW_GATE_FAIL` |

New Hit、Lost Hit 和 Citation 变化已由业务负责人审核。当前结果为 `VERIFIED_NEW_HIT=3`、`VERIFIED_LOST_HIT=2`、`NOT_VERIFIED=16`；其中 `NOT_VERIFIED=16` 明确表示两份重放答案的事实和来源定位均不正确。V2.5 当前以后台真实分支运行，不影响 V1 主回答。

## C. Rollback Drill

未执行真实 `V1 → V2.5 → V1` 演练。此前的 Rollback Preparation 仍为 READY，不能写成 PASS。

## D. Candidate Integrity

候选仍为 V2.5 Frozen Candidate，未创建新的 V2.6 Retrieval Candidate：

- Candidate hash：`26928685b69d167a99289a26776b6e0712531f79eaed71effc553bd37543ce03`
- Source/semantic-chunk hash：`850748257c8e5f31263933f0ee76bd43fae39c4ab7f340862e03532b824fc714`
- Dense embedding hash：`c1a4e81b7e2541e9d5534265c6adbfd709d0eb753ff219a53ecae461ee0be4af`

## E. Controlled Switch

未获得“允许切换 8010”的授权，且 Live Shadow Gate 未通过，因此没有切换。8010 保持 V1 Primary，8000 保持 OFF。

## F. Immediate Smoke / G. Canary

均未执行。必须在 Live Shadow Gate、Rollback Drill Gate 和明确切换授权通过后执行。

## H. Final Status

`BLOCKED`

阻塞项：

1. 2 条历史 V2.5 Shadow 异常仍需保留并完成处置记录；
2. 已确认 `VERIFIED_LOST_HIT=2`；另有 `NOT_VERIFIED=16`，两份重放答案的事实和来源定位均不正确；
3. V2.5 答案分支虽已接入，但 Release Gate 不能因样本量达标而跳过错误和引用审核。

## 下一步

先处置 2 条 `VERIFIED_LOST_HIT` 并完成历史异常的干净窗口验证；只有确认无 Verified Lost Hit、无 Critical Failure 后，才继续 T04 Rollback Drill。

## I. 根因修复进展（不改变发布闸门）

- `LSR-014`：确认冻结 V2.5 只有登记页，真实 PDF 未进入候选正文；新增来源已由 Owner 以 SHA-256 批准，并完成 34 个语义块的 BGE-M3 向量化。全候选重放已答对，待真实 Live Shadow 验证。
- `LSR-017`：确认 2025 年上半年 `3.31%` 与全年 `3.33%` 属于不同期间；已在查询计划、证据范围和同范围冲突检测中加入 `H1/FULL_YEAR`，并加入仅从既有、期间匹配证据中补回的开发候选机制。只读重放已返回 `3.31%`；无期间问题仍保留冲突保护。
- `V2.6.1_DEV_REMEDIATION` 的两条全候选重放均为 `ANSWERED` 且引用校验通过，但不计入 Live Shadow 或 Release Gate。
- 本轮修复未写入 8000、未切换 8010，也未改写冻结 V2.5；修复验证通过后仍须重跑干净 Live Shadow 窗口。

## 主要交付物

- `evaluation/knowledge_os_v2_6/live_shadow_runs.jsonl`
- `evaluation/knowledge_os_v2_6/live_shadow_report.json`
- `evaluation/knowledge_os_v2_6/final_release_gate.json`
- `docs/LIVE_SHADOW_REPORT.md`
- `docs/LIVE_SHADOW_REMEDIATION_DIAGNOSIS.md`
- `docs/V2_6_1_REMEDIATION_REPLAY.md`
- `docs/V2_6_1_FULL_CANDIDATE_REPLAY.md`
- `docs/LIVE_SHADOW_V2_6_1_DEV_REPORT.md`
- `docs/8010_CONTROLLED_SWITCH_PLAN.md`
- `docs/8010_ROLLBACK_PLAN.md`
