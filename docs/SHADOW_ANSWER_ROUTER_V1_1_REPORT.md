# Shadow Answer Router V1.1 Report

> TASK-016E-4.1：区分 DIRECT_FACT 与 DERIVED_FACT，避免将直接事实误路由到 Fact Aggregator。
> 仅修改 Shadow Router；未修改正式 8000、Retriever、Qdrant、Embedding、RRF、Reranker、Claim Answer Engine 或 BA-010 Fact Path。

## 1. 路由定义

- `DIRECT_FACT`：源文档直接存在的单一事实，默认走 `CLAIM_ANSWER_PATH`。
- `DERIVED_FACT`：需要 COUNT、GROUP_BY、SUM、FILTER、LIST_DISTINCT 或跨记录/跨 Sheet 计算。
- `AMBIGUOUS_FACT`：无法判断是制度目标还是实际记录统计，安全返回 `FACT_PATH_UNAVAILABLE` 并标记 `ROUTE_AMBIGUOUS`。
- 数量、金额、比例等词本身不再直接触发 Fact Path。

## 2. 路由指标

- 测试题数：40
- Route Accuracy：**40/40 (100.0%)**
- Fact Mode Accuracy：**40/40 (100.0%)**
- Routing Status Accuracy：**40/40 (100.0%)**
- False Fact Route：0
- False Claim Route：0
- FACT_PATH_UNAVAILABLE：8
- ROUTE_AMBIGUOUS：1

## 3. 重点 BA 验收

- BA-006：fact_mode=`DIRECT_FACT`，route=`CLAIM_ANSWER_PATH`，operations=`[]`，status=`ROUTED_TO_CLAIM_PATH`
- BA-007：fact_mode=`NONE`，route=`CLAIM_ANSWER_PATH`，operations=`[]`，status=`ROUTED_TO_CLAIM_PATH`
- BA-008：fact_mode=`DIRECT_FACT`，route=`CLAIM_ANSWER_PATH`，operations=`[]`，status=`ROUTED_TO_CLAIM_PATH`
- BA-010：fact_mode=`DERIVED_FACT`，route=`FACT_ANSWER_PATH`，operations=`['LIST_DISTINCT', 'GROUP_BY', 'COUNT', 'FILTER']`，status=`DETERMINISTIC_FACT_RESULT_AVAILABLE`

## 4. 对照题检查

- 公司要求设计示范项目不少于多少个？→ DIRECT_FACT → CLAIM
- 当前项目台账里共有多少个设计示范项目？→ DERIVED_FACT → 当前能力不足时 FACT_PATH_UNAVAILABLE
- 2025年公司设计创效金额是多少？→ DIRECT_FACT → CLAIM
- 把2025年所有项目设计创效金额加起来是多少？→ DERIVED_FACT → 当前 SUM 能力不足时 FACT_PATH_UNAVAILABLE
- 设计效益率目标是多少？→ DIRECT_FACT → CLAIM
- 根据各项目金额计算公司平均设计效益率是多少？→ DERIVED_FACT → FACT_PATH_UNAVAILABLE

## 5. Provider Failure

Router 未调用 Provider，因此本次没有产生 Provider Failure。上游 BA-007 稳定性中的 Provider Error 保留为 `I PROVIDER_FAILURE`，未被 Router 转换为 NO_EVIDENCE 或 STRUCTURE_INVALID。

## 6. 输出边界

- 业务问题和测试编号只用于验收对账，Router 决策不读取 BA 编号。
- Router 不计算 80、37、43 等事实数字，只检查 Fact 能力是否可用。
- BA-010 保持 DERIVED_FACT → FACT_ANSWER_PATH，不回退。
- 本任务未接入正式 8000 服务。
