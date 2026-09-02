# V1.0 Internal Trial Conditions

> TASK-018 配套条件文件。适用于受控、只读、Shadow/Degraded Trial，不代表正式上线或 Root-002 正式授权。

## 1. Trial 结论

`CONDITIONAL_GO`

可以进行小范围内部试用，但必须采用 Provider Degraded Mode；Provider 依赖型普通 Claim Answer 暂不作为可用能力。

## 2. 允许范围

- 用户：建议 2–3 名设计管理/技术管理业务负责人，采用白名单和人工反馈机制。
- 默认知识源：Root-001 `D:\设计管理`，只读。
- Shadow 证据：Root-002 只能以 `frozen Shadow scope` 展示，`governance=PENDING_APPROVAL`，不得称为正式知识源。
- 可用能力：Evidence Preview、Citation 定位、BA-002 确定性公式、BA-004 OPTION、BA-008 Direct Fact、BA-010 Fact Result、安全拒答和状态诊断。
- 反馈：每题记录是否真正回答、引用是否合适、是否需要补源文件；业务负责人确认后再进入后续治理任务。

## 3. 三种用户可见状态

### NORMAL ANSWER

仅适用于 Provider 可用且通过 Schema、Claim、Citation 校验的普通 Claim Answer。

### SAFE REFUSAL

适用于来源范围不足、正文缺失、权威等级不足或证据不足。必须说明缺少什么，不得用相近案例冒充答案。

### GENERATION SERVICE UNAVAILABLE

适用于 Provider 临时失败、Circuit OPEN 或测试预算耗尽。应提示“已找到相关证据，但当前生成服务暂不可用”，同时允许查看 Evidence/Citation；不得显示“知识库没有答案”。

## 4. 必须关闭

- Provider 不稳定期间的普通生成式 Claim Answer；
- Root-002 未审批前的正式知识源使用；
- Root-003 自动导入；
- 新 Knowledge Root 自动发现和发布；
- 自动 OCR 生产化；
- 正式 8000 切换；
- 自动写回正式知识；
- 正式多人权限体系。

## 5. 运行约束

- 所有知识源、索引和事实结果只读；
- Provider 继续使用持久化 Budget Guard 和 Circuit Breaker；当前预算耗尽，不得重启脚本恢复额度；
- BA-010 只使用确认口径“增加效益 = 利润 > 0”，43 条利润为空/未判定不得说成无效益；
- Root-002 证据必须显示 Root、文件、位置和 Pending Approval 状态；
- 每次问题保留 route、retrieval、evidence、preflight、provider status、citation 和 final status。

## 6. 试用退出条件

满足任一条件立即停止对应试用能力：

- 发现来源越界、正式源文件被写入或未经批准的 Root 被读取；
- Citation 无法回查原始位置；
- 事实统计无法提供 source rows；
- Provider 状态被错误显示为 NO_EVIDENCE；
- 业务负责人发现制度、案例、模板被混用且无法人工纠正。

