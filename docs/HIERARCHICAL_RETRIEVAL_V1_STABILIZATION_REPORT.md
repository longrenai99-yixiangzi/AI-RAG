# HIERARCHICAL RETRIEVAL V1 STABILIZATION REPORT

> TASK-020C.1。仅重建独立 Shadow 索引；未修改正式 Retriever、8000 服务、正式 Qdrant 或 Answer Engine；未调用 LLM/HTTP Provider；Root-002 仅复用既有 Frozen Shadow Artifact，未刷新；未扫描 Root-003。

## 1. 稳定化变更

- Document 阶段将文档自身表示与其最相关 Section 表示合并为同一文档候选的简单 RRF Trace，解决长文均值向量稀释；没有引入 020D 多路 Fusion。
- Section Dense 审计将空/纯结构节点排出 eligible 分母；其余 Section 显式标明为直接 Section 向量、父文档向量回退或缺失。
- Global Rescue 与主路径指标分开：救援候选不再覆盖上游 Document/Section/Table 失败分类。

## 2. 指标

- Document Recall@5：1.0
- Hierarchical-only Section Recall@5：1.0
- Rescue-inclusive Section Recall@5：1.0
- Hierarchical-only Evidence Recall@10：1.0
- Rescue-inclusive Evidence Recall@10：1.0
- Eligible Section Dense Coverage：1.0（direct=3426，parent fallback=1870，excluded=247）
- Registration Page Dominance：{'numerator': 0, 'denominator': 50, 'rate': 0.0}；Lineage Unsafe Join：0

## 3. Global Rescue 贡献

- 召回搜索执行：1.0；贡献独立候选：0.7；恢复 Gold：0.0；Gold Dependency：0.0。

## 4. Planner 指标口径

- Query Type Accuracy：{'numerator': 8, 'denominator': 10, 'rate': 0.8}；Entity Accuracy（检测率）：{'numerator': 3, 'denominator': 5, 'rate': 0.6}。
- Decomposition Required Queries：3；Subquestion Coverage on Eligible Queries：{'numerator': 3, 'denominator': 3, 'rate': 1.0}。

## 5. BA 检索矩阵

| BA | Document | Hierarchical Section | Rescue-inclusive Section | Table | Hierarchical Evidence | Rescue-inclusive Evidence | 分类 | Rescue |
|---|---:|---:|---:|---:|---:|---:|---|---|
| BA-001 | 2 | 1 | 1 | None | 4 | 4 | HIERARCHICAL_HIT | NOT_REQUIRED |
| BA-002 | 3 | 1 | 1 | None | 1 | 1 | HIERARCHICAL_HIT | NOT_REQUIRED |
| BA-003 | None | None | None | None | None | None | SOURCE_SCOPE_MISSING | NOT_REQUIRED |
| BA-004 | 5 | 3 | 3 | 3 | 1 | 1 | HIERARCHICAL_HIT | NOT_REQUIRED |
| BA-005 | None | None | None | None | None | None | SOURCE_SCOPE_MISSING | NOT_REQUIRED |
| BA-006 | None | None | None | None | None | None | SOURCE_SCOPE_MISSING | NOT_REQUIRED |
| BA-007 | None | None | None | None | None | None | SOURCE_SCOPE_MISSING | NOT_REQUIRED |
| BA-008 | 5 | 2 | 2 | None | 1 | 1 | HIERARCHICAL_HIT | NOT_REQUIRED |
| BA-009 | None | None | None | None | None | None | SOURCE_SCOPE_MISSING | NOT_REQUIRED |
| BA-010 | 3 | 1 | 1 | 1 | 1 | 1 | LINEAGE_SAFETY_BLOCK | NOT_REQUIRED |

## 6. 验收门槛

| 门槛 | 结果 |
|---|---|
| Document Recall@5 >= 80% | PASS |
| BA-001 Gold Document Top5 | PASS |
| BA-002 Gold Document Top10 | PASS |
| BA-008 Gold Document Top5 | PASS |
| Hierarchical-only Section Recall@5 >= 60% | PASS |
| Gold Evidence Recall@10 >= 80% | PASS |
| Eligible Section Dense Coverage >= 95% | PASS |
| Lineage Unsafe Join = 0 | PASS |
| Registration Page Dominance = 0 | PASS |

## 7. 边界与结论

- `HIERARCHICAL_HIT` 仅表示 Gold 已在 Document → Section/Table → Evidence 的实际窗口内命中；`GLOBAL_RESCUE_RECOVERED` 只作为救援状态单列，不能掩盖 `SECTION_MISSED` 或 `TABLE_MISSED`。
- `BA-specific runtime hardcoding=0` 与 `Gold runtime injection=0`：核心运行模块 `app/retrieval` 不含 BA-001～BA-010 判断、Gold 文件名或目标文件名注入。评估脚本中的 BA 编号只用于离线验收门槛展示，Gold 仅用于评价，不参与候选生成、排序或回答。
- Provider HTTP Requests=0；本次耗时 45.571s。

TASK-020C.1 = COMPLETE
