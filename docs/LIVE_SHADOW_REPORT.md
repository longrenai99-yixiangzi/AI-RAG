# V2.6 Live Shadow Report

- 样本数：15（目标 100；最低有效样本 30）
- 执行方式：REPLAY_EXISTING_REAL_TRIAL_LOG_WITH_BM25_PREVIEW_ONLY
- Shadow Gate：`SHADOW_INSUFFICIENT_SAMPLE`

## 结果

- 来源 Agreement：1/15
- Verified New Hit：0（未判定，需业务审核）
- Verified Lost Hit：0（未判定，需业务审核）
- V2.5 答案引擎：未接入 8010，只有检索层回放
- V1/V2 延迟：未形成可比数据

## 停止原因

真实唯一问题样本少于30，且本次未重复刷题；V2.5答案引擎未接入8010 Live Runtime，不能把离线检索回放冒充Live Shadow。

本报告不把离线回放、Holdout 或重复刷题结果冒充 Live Shadow。样本达到 30 且 V2.5 分支接入真实请求后，才能继续形成 Live Shadow Gate。
