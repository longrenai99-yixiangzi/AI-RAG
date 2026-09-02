# Knowledge Governance Optimization Report

> 本报告在独立 `full_corpus_shadow_bge_m3` 上评估文档角色、权威等级和使用场景治理。
> 不修改正式 Retriever、8000 服务或正式 Qdrant；治理字段在 Shadow 读取阶段派生。

## 1. Schema 与规则

新增字段：
- `document_role`：正式制度、管理指南、标准模板、项目案例、培训材料、汇报材料、其他。
- `authority_level`：L1 至 L6，分别对应正式制度到汇报材料；无法判断为 UNKNOWN。
- `usage_scene`：制度执行、管理指导、标准复用、项目复盘、模板填报、培训学习、汇报交流、专业设计、其他。

Document Priority：正式制度 > 管理指南 > 标准模板 > 项目案例 > 培训材料 > 汇报材料。

## 2. 评估范围

- Gold Questions：`100` 题，已补充三个 expected 治理字段，状态仍为 provisional。
- Shadow Collection：`4747` 点。
- Shadow Chunk：`4747`。
- GPU：`NVIDIA GeForce RTX 4060 Laptop GPU`，CUDA：`True`。
- 查询向量耗时：`5.108` 秒；Reranker：`42.667` 秒。

## 3. 检索指标对比

| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation完整率 | 未命中题数 |
|---|---:|---:|---:|---:|---:|---:|
| TASK-012.10 Precision baseline | 51.00% | 65.00% | 69.00% | 0.579 | 100.00% | 31 |
| TASK-012.11 Governance optimized | 51.00% | 65.00% | 69.00% | 0.579 | 100.00% | 31 |

## 4. 治理命中指标

| 指标 | Precision baseline | Governance optimized |
|---|---:|---:|
| document_role Top-1 精确匹配 | 25.00% | 25.00% |
| document_role Top-5 覆盖 | 42.00% | 42.00% |
| authority_level Top-1 匹配 | 25.00% | 25.00% |
| usage_scene Top-1 匹配 | 25.00% | 25.00% |
| 制度问题 Top-1 命中正式制度/管理指南 | 42.11% | 42.11% |
| 案例问题 Top-1 命中项目案例 | 86.67% | 86.67% |
| 模板问题 Top-1 命中标准模板 | 23.08% | 23.08% |

## 5. 角色分布

- Gold document_role：`{"管理指南": 53, "项目案例": 12, "汇报材料": 5, "标准模板": 21, "其他": 4, "正式制度": 5}`。
- Gold authority_level：`{"L2": 53, "L4": 12, "L6": 5, "L3": 21, "UNKNOWN": 4, "L1": 5}`。
- Gold usage_scene：`{"管理指导": 53, "项目复盘": 12, "汇报交流": 5, "标准复用": 21, "其他": 4, "制度执行": 5}`。
- Shadow Corpus document_role：`{"项目案例": 3193, "标准模板": 411, "其他": 241, "培训材料": 499, "正式制度": 89, "汇报材料": 128, "管理指南": 186}`。
- Intent 分布：`{"POLICY_QUERY": 19, "METHOD_QUERY": 23, "CASE_QUERY": 15, "DISCIPLINE_QUERY": 30, "TEMPLATE_QUERY": 13}`。

## 6. 候选配置结果

| 配置 | Recall@1 | Recall@3 | Recall@5 | MRR | role Top-1 | role Top-5 |
|---|---:|---:|---:|---:|---:|---:|
| governance_light | 51.00% | 65.00% | 69.00% | 0.579 | 24.00% | 42.00% |
| governance_safe | 50.00% | 65.00% | 69.00% | 0.576 | 24.00% | 42.00% |
| governance_balanced | 51.00% | 64.00% | 69.00% | 0.577 | 24.00% | 42.00% |
| role_priority_focus | 51.00% | 64.00% | 69.00% | 0.580 | 25.00% | 42.00% |
| selected: precision_baseline_fallback | 51.00% | 65.00% | 69.00% | 0.579 | 25.00% | 42.00% |

## 7. 是否进入正式 Retriever

当前结论：暂不进入正式 Retriever；治理排序未同时满足检索指标不下降和治理指标提升门槛。

## 8. 边界说明

- Gold 治理字段是基于 expected_files 和治理规则的候选复核结果，仍需内容负责人确认。
- Shadow 治理字段在读取 Qdrant Payload 时派生，未回写 Shadow Qdrant，也未执行全库 Embedding。
- 未修改正式 `app/retriever.py`、`app/main.py`，未影响 8000 端口。
- BGE-M3：`D:\AI智能体\AI设计管理RAG-V1\models\bge-m3`。
- Reranker：`D:\AI智能体\AI设计管理RAG-V1\models\bge-reranker-v2-m3`。
