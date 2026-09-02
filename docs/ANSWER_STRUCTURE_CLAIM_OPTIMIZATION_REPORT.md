# Answer Structure & Claim Reliability Optimization Report

> 本报告验证 Query Understanding → Document Profile Retrieval → Hybrid/Chunk Retrieval → Evidence Ranking → Answer Policy → LLM Provider → Claim-Evidence Validation。
> 本次使用 Shadow 环境，不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. 实现模块

- app/answer_engine/llm/llm_provider.py：OpenAI-compatible Shadow Provider，复用现有 LLM 配置。
- app/answer_engine/llm/prompt_builder.py：按 Intent 和 Evidence Bundle 生成受约束 Prompt。
- app/answer_engine/llm/answer_generator.py：调用 Provider、解析结构化回答并触发 Claim 校验。
- app/answer_engine/llm/claim_validator.py：校验 Claim 的 Evidence ID 和答案中的 Citation。

## 2. 评估结果

- Gold Questions：100。
- Shadow Collection：4747 点；Chunk：4747。
- Evidence 条目数：492。
- 原始逐题输出：D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant\answer_engine_raw_outputs.jsonl（100 条）。
- Profile expected_file 覆盖率：44.00%。
- LLM 探针：通过。
- LLM 探针调用次数：1。
- 实际答案生成尝试：100。
- CUDA：True，GPU：NVIDIA GeForce RTX 4060 Laptop GPU。
- 查询向量耗时：12.386 秒。

| 指标 | 结果 |
|---|---:|
| 答案结构正确率 | 100.00% |
| 全部100题结构正确率 | 52.00% |
| Citation完整率 | 100.00% |
| Claim Validation Pass Rate | 82.00% |
| CLAIM_INVALID 数量 | 48 |
| Unsupported Claim 数量 | 0 |
| Claim Validation 有效率 | 82.00% |
| 制度/案例混淆率 | 7.69% |
| Repair 触发数量 | 59 |
| Repair 成功率 | 18.64% |
| 人工可读性 | MANUAL_REVIEW_REQUIRED |

- Answer 状态：{"GENERATED": 52, "PARTIAL_EVIDENCE": 18, "STRUCTURE_INVALID": 30}。
- 失败分类：{"A": 52, "G": 18, "D": 30}。

## 3. LLM 服务状态

100题中完成模型生成尝试 100 题，其中 48 题未通过最终 Claim 结果校验。
错误摘要：LLMError: 生成模型请求失败；请检查内网连接、模型权限和服务状态。

本次报告将 GENERATED、STRUCTURE_INVALID、PARTIAL_EVIDENCE、LLM_ERROR 和 LLM_UNAVAILABLE 分开统计；只有 GENERATED 才进入答案结构和 Citation 质量分母。

## 4. TASK-015.3 基线对比

| 指标 | TASK-015.3 基线 | TASK-015.4 当前结果 |
|---|---:|---:|
| Answer Structure Correct Rate | 32.98% | 100.00% |
| Citation Completeness | 100.00% | 100.00% |
| CLAIM_INVALID | 6 | 48 |
| Unsupported Claim | 1 | 0 |
| 制度/案例混淆率 | 6.38% | 7.69% |

TASK-015.3 的逐题原始输出未持久化，无法对历史 6 个 CLAIM_INVALID 逐题回放；本报告对当前重跑结果保存逐题失败分类。

### 当前失败样本分类

| 问题 | 状态 | 分类 | 初始分类 | Repair触发 | Repair成功 |
|---|---|---|---|---|---|
| 设计管理工作计划应如何设置年度重点任务？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 设计策划阶段需要明确哪些输入和交付成果？ | PARTIAL_EVIDENCE | G | D | 是 | 否 |
| 设计管理如何组织设计评审和问题闭环？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 设计任务书在设计管理流程中承担什么作用？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 技术管理部门如何推动专业标准落地？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 设计标准工期库如何支持进度管理？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 技术管理如何处理设计变更和技术问题？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 技术管理如何组织跨专业技术交流？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 设计创新成果评价应关注哪些维度？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 科技管理如何沉淀可复用的知识成果？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 数字化设计成果如何进入企业知识库？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 科技管理如何开展成果推广和培训？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 科技管理如何定义创新项目的证据和成果？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 科技成果总结如何服务后续设计决策？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| EPC项目如何开展设计创效管理？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| EPC项目设计管理方法与实务有哪些常用方法？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| EPC项目设计管理经验如何形成可复制流程？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 深化设计阶段如何管理设计深度和成果交付？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 施工图任务书中的条件确认应包括哪些内容？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 施工图设计任务书如何约束专业接口？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |
| 深化设计成果审查应关注哪些图纸问题？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 设计任务书如何区分方案、初步设计和施工图成果？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 施工图设计成果交付前需要完成哪些校审？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 深化设计任务书如何形成可检查的成果清单？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| BIM如何支持设计协同和碰撞检查？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| BIM成果交付应关注哪些模型和图纸关系？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| BIM应用如何服务EPC项目设计交付？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| BIM成果质量检查应设置哪些检查点？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| BIM专业协同如何减少设计接口遗漏？ | STRUCTURE_INVALID | D | D | 是 | 否 |
| 河北科技师范学院项目方案比选如何形成决策？ | PARTIAL_EVIDENCE | G | G | 是 | 否 |


## 5. Claim-Evidence 规则

1. 每个 Claim 必须包含至少一个 evidence_id。
2. evidence_id 必须存在于当前 Evidence Bundle。
3. 答案中的 [Sx] 只能引用当前 Evidence Bundle 的来源。
4. Claim 校验失败时不得把答案标记为确定性可信答案。
5. LLM 不得自行访问 Qdrant 或知识源，只能使用 Prompt 中提供的 Evidence。

## 6. 后续动作

### 人工抽样评价

以下抽样用于人工复核，脚本不自动给出主观分数；当前状态必须由业务人员确认。

| 抽样问题 | 结论明确性 | 专业可信度 | 可直接使用程度 |
|---|---|---|---|
| FCQ-001 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-031 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-061 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-081 | 待人工复核 | 待人工复核 | 待人工复核 |
| FCQ-091 | 待人工复核 | 待人工复核 | 待人工复核 |

1. 先分析 Provider 失败题和限流/超时原因，再决定是否重跑失败题。
2. 真实生成后人工抽查制度、案例、方法、模板和专业问题各类样本。
3. 在 Provider 可用前，不修改正式 Answer 链路，不把 evidence-only 结果伪装成 LLM 结论。

## 7. 边界确认

- 正式 Retriever：未修改。
- 8000 服务：未修改。
- 正式 Qdrant：未修改。
- LLM-as-Judge：未使用。

**TASK-015.4：Answer Structure & Claim Reliability Optimization 完成。**
