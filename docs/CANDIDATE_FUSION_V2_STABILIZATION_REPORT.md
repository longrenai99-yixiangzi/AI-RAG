# CANDIDATE FUSION V2 STABILIZATION REPORT

> TASK-020D.1。只读复核既有020D Trace；未调用模型或Provider，未修改候选、权重、RRF、Gold、Index或Qdrant。

## 1. 根因结论

- BA-001：正式手册的 Evidence Dense、Section 与 Document 支持共同进入前列，故从原候选 Rank 4 提升至 Rank 1。
- BA-008：Planner正确识别公司、2025和创效金额；但Top候选中存在多个同为公司/2025/创效金额的不同事实值。粗粒度 Scope= MATCH 无法区分事实口径。
- BA-008 Reranker输入缺少显式组织、项目、年份和角色字段，确认为 `RERANKER_SCOPE_BLINDNESS`。
- 该问题同时属于 `SAME_SCOPE_CONFLICT`：不引入任意业务偏好，不能只凭通用Soft Boost把某一份同范围报告指定为唯一正确答案。

## 2. Generic Gold可评价性

- 状态分布：`{'GENERIC_GOLD_MAPPING_MISSING': 30}`。只有 `GENERIC_EVALUABLE` 进入MRR分母；当前分母：0。
- 原30题的0.0667不能作为当前V2 Atomic Evidence质量结论，因为该集没有显式V2 Evidence/Location映射且非Owner Confirmed。

## 3. 修正决策

- 未应用Scope Guard：现有 BA-008 的核心冲突不是项目/年份/组织错配，而是同范围候选的事实值冲突。强行加分会构成对单题结果的隐式偏好。
- 未重新调用reranker：本TASK禁止Provider调用，因此只审计了既有reranker输入。

## 4. 验收

- Business MRR：0.85；要求 >0.85；结果：**NOT PASSED**。
- BA-008 Post-Rerank Rank：4；要求 <=3；结果：**NOT PASSED**。
- BA-001 / BA-002 / BA-004 / BA-010 保持既有安全状态；BA-010仍为 `LINEAGE_SAFETY_BLOCK` / `NO_AUTO_JOIN`。

TASK-020D.1 = COMPLETE

020D不接受；停止，不进入020E。
