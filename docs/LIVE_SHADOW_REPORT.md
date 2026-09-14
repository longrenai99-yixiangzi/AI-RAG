# V2.6 Live Shadow Report

- V2.5 后台分支：`WIRED`
- 接入后有效样本：131（目标 100；最低有效样本 30）
- 样本门：`PASS`
- Live Shadow Gate：`SHADOW_GATE_FAIL`

## 口径

only requests received after V2.5 background branch wiring; pre-wiring real requests remain historical baseline and are not relabeled

## 当前限制

接入后唯一样本达到 131，但发现 2 条 V2.5 Shadow 异常，需先修复并复核。

V1 继续给用户返回原有答案；V2.5 仅在后台运行并写入对照记录。New Hit、Lost Hit 和 Citation 变化必须人工审核，不能自动判定。
