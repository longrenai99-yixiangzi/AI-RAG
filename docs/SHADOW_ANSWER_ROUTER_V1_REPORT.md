# Shadow Answer Router V1 Report

> TASK-016E-4：只在 Shadow 环境验证 Claim Answer Path 与 Fact Answer Path 路由。
> Router 不调用 LLM，不修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF 或 Reranker。

## 1. Fact Capability

- Structured Table Source：`True`
- Target Document：`方案比选与价值创造清单方案比选及价值创造.xlsx`
- Target Sheet：`价值创造`
- Field Mapping：`['专业类别', '利润']`
- Business Semantics：`{"benefit_semantics": "增加效益", "mapped_field": "利润", "operator": ">", "threshold": 0, "source": "business_owner_confirmation"}`
- Deterministic Aggregation：`True`
- Supported Operations：`['LIST_DISTINCT', 'GROUP_BY', 'COUNT', 'FILTER']`

## 2. BA-001～BA-010 路由结果

| ID | 问题 | Expected Route | Actual Route | Intent | Operations | Final Path | Status |
|---|---|---|---|---|---|---|---|
| BA-001 | 设计任务书需要包含哪些内容？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | TEMPLATE_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-002 | 设计效益增量的计算方式？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | GENERAL_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-003 | 厂房产品线的方案比选案例包含哪些专业？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | CASE_QUERY | LIST_DISTINCT | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-004 | 自动喷淋系统管材方案比选可采用哪几种方案进行比选？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | GENERAL_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-005 | 特殊环境条件下集电线路电气设计的图审要点有哪些？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | DISCIPLINE_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-006 | 2026年局设计与技术系统的责任状要求DOP平台电子图形文件数据中心上传数量是多少？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | FACT_QUERY | COUNT | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE |
| BA-007 | 2026年设计示范项目的打造要求是什么？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | POLICY_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-008 | 2025年公司设计创效金额是多少元？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | FACT_QUERY | COUNT | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE |
| BA-009 | 2026年4月EPC项目双周推进会上，给土木公司的督办是什么？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | DISCIPLINE_QUERY | - | CLAIM_ANSWER_PATH | ROUTED_TO_CLAIM_PATH |
| BA-010 | 星谷科创中心项目，设计策划中的设计价值创造清单，包含了哪几个专业，每个专业分别有多少条，增加效益的有多少条？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | FACT_QUERY | LIST_DISTINCT,GROUP_BY,COUNT,FILTER | FACT_ANSWER_PATH | DETERMINISTIC_FACT_RESULT_AVAILABLE |

## 3. 新增 20 题路由结果

| ID | 问题 | Expected Route | Actual Route | Operations | Final Path |
|---|---|---|---|---|---|
| R-001 | 设计管理制度中的项目设计任务书评审要求有哪些？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-002 | 设计任务书编制流程包括哪些步骤？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-003 | EPC设计管理复盘案例中有哪些常见经验？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-004 | 特殊环境下集电线路电气图审要点有哪些？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-005 | 设计任务书模板需要填写哪些内容？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-006 | 设计价值创造有哪些主要做法？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-007 | 星谷项目有多少条价值创造策划？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | COUNT | FACT_ANSWER_PATH |
| R-008 | 按专业统计星谷价值创造清单有多少条？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | GROUP_BY,COUNT | FACT_ANSWER_PATH |
| R-009 | 星谷项目每个专业分别多少条？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | GROUP_BY,COUNT | FACT_ANSWER_PATH |
| R-010 | 星谷项目利润大于0的增加效益有多少条？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | COUNT,FILTER | FACT_ANSWER_PATH |
| R-011 | 星谷项目价值创造条目合计多少金额？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | COUNT,SUM | FACT_PATH_UNAVAILABLE |
| R-012 | 2026年有多少个设计示范项目？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | COUNT | FACT_PATH_UNAVAILABLE |
| R-013 | 设计示范项目有哪些要求？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-014 | 公司2025年设计创效金额是多少元？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | COUNT | FACT_PATH_UNAVAILABLE |
| R-015 | 按项目统计2026年设计示范项目数量？ | FACT_PATH_UNAVAILABLE | FACT_PATH_UNAVAILABLE | GROUP_BY,COUNT | FACT_PATH_UNAVAILABLE |
| R-016 | 设计示范项目的管理要求和职责是什么？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-017 | 价值创造清单中有哪些专业？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | LIST_DISTINCT | FACT_ANSWER_PATH |
| R-018 | 利润大于0的价值创造条目有哪些？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | FILTER | FACT_ANSWER_PATH |
| R-019 | 设计价值创造清单的利润字段如何理解？ | CLAIM_ANSWER_PATH | CLAIM_ANSWER_PATH | - | CLAIM_ANSWER_PATH |
| R-020 | 星谷项目价值创造有哪些专业并合计多少条？ | FACT_ANSWER_PATH | FACT_ANSWER_PATH | LIST_DISTINCT,COUNT | FACT_ANSWER_PATH |

## 4. Router 指标

- Route Accuracy：**30/30 (100.0%)**
- False Fact Route：`0`
- False Claim Route：`0`
- FACT_PATH_UNAVAILABLE：`6`
- Provider Failure 分类：`{"source": "TASK-016E-3.1 upstream stability", "provider_failures": 1, "classification": "I PROVIDER_FAILURE", "router_provider_calls": 0}`；Router 本身未调用 Provider，未将 Provider Failure 转换成业务失败。

## 5. 重点验收

- BA-007：必须且实际为 `CLAIM_ANSWER_PATH`。
- BA-010：必须且实际为 `FACT_ANSWER_PATH`，使用已验证的确定性 Fact Result。
- “设计价值创造有哪些主要做法？”进入 Claim，不因“价值创造”单词误触发 Fact。
- “2026年有多少个设计示范项目？”进入 FACT_PATH_UNAVAILABLE，不回退让 LLM 计算。
- “星谷项目有多少条价值创造策划？”进入 FACT_ANSWER_PATH。

## 6. 输出边界

- Router 决策未使用 BA 编号或完整问题文本硬编码；BA 编号只用于测试 Expected Route 对账。
- Fact 路由只在结构化来源、字段映射、业务语义和确定性聚合能力同时存在时可用。
- 事实统计数字仍由 Fact Answer Path 产生，Router 不计算数字。
- 本任务未接入正式 8000 服务。
