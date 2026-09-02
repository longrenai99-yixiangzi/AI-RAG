# Answer Engine Shadow Implementation Report

> 本报告验证 Shadow Answer Engine 的 Answer Policy、Evidence Selection、Claim-Citation Map 和结构化响应。
> 本次不调用 LLM，不修改 app/answer.py、/api/chat、正式 Retriever、正式 Qdrant 或 8000 服务。

## 1. 实现模块

- app/answer_engine/answer_policy.py：Intent 到回答章节和证据偏好的映射。
- app/answer_engine/evidence_selector.py：从 Retriever Top-K 选择 Evidence Bundle。
- app/answer_engine/citation_map.py：建立 Claim → Evidence 映射并校验来源 ID。
- app/answer_engine/answer_response.py：输出 evidence-only 结构化响应，不生成模型结论。

## 2. 100题验证范围

- Gold Questions：100。
- Shadow Collection：4747 点。
- Shadow Chunk：4747。
- LLM 调用次数：0。
- 查询向量耗时：11.847 秒；Reranker：43.421 秒。
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU，CUDA：True。

## 3. 验证结果

| 指标 | 结果 |
|---|---:|
| 生成 Evidence Bundle 的问题 | 100/100 |
| Evidence 条目数 | 500 |
| Evidence 必要字段完整率 | 100.00% |
| Citation Map 有效率 | 100.00% |
| 预期文件进入 Evidence 率 | 12.00% |
| Intent 回答章节结构完整率 | 100.00% |

- Response 状态：{"EVIDENCE_ONLY": 100}。
- Intent 分布：{"POLICY_QUERY": 19, "METHOD_QUERY": 23, "CASE_QUERY": 15, "DISCIPLINE_QUERY": 30, "TEMPLATE_QUERY": 13}。
- Evidence 文档角色分布：{"管理指南": 115, "正式制度": 35, "汇报材料": 19, "项目案例": 256, "其他": 3, "标准模板": 63, "培训材料": 9}。

## 4. Evidence Bundle 字段

每条 Evidence 保留：source_id、chunk_id、document_role、authority_level、usage_scene、location、file_name、source_path、excerpt。

source_id 在 Evidence Selection 完成后按 S1、S2 顺序生成；Claim-Citation Map 只允许引用当前 Bundle 中实际存在的 source_id。

## 5. 按 Intent 的回答策略

| Intent | 回答章节 | 证据重点 |
|---|---|---|
| POLICY_QUERY | 结论、管理要求、依据 | 正式制度、管理指南、流程 |
| CASE_QUERY | 背景、措施、效果、经验 | 项目案例、复盘、经验总结 |
| METHOD_QUERY | 流程、步骤、注意事项 | 指南、方法、任务书 |
| TEMPLATE_QUERY | 模板用途、字段说明、使用方法 | 标准模板、表单、清单 |
| DISCIPLINE_QUERY | 专业结论、适用条件、检查点、依据与边界 | 专业指南、案例、标准 |

## 6. 当前边界

1. 当前响应为 evidence-only，不是 LLM 生成的最终答案。
2. Claim 是由 Evidence 摘录构造的结构化 Claim，用于验证映射链路，不能替代未来 LLM 的事实归纳。
3. 当前未执行 Claim 内容正确性判断；下一阶段应增加证据覆盖和拒答策略测试。
4. 生成模型接入必须经过 Response Schema、Citation validation 和失败回退。

## 7. TASK-014A 边界确认

| 验收项 | 结果 |
|---|---|
| Answer Policy | 已实现 |
| Evidence Selection | 已实现 |
| 保留 source_id/chunk_id/document_role/authority_level/location | 已实现 |
| Claim → Evidence Citation Map | 已实现 |
| 使用100题 Gold Questions | 已完成 |
| 调用 LLM | 否 |
| 修改 app/answer.py | 否 |
| 修改 /api/chat | 否 |
| 修改正式 Qdrant | 否 |

**TASK-014A：Answer Engine Shadow Implementation 完成。**
