# DOCUMENT INTELLIGENCE V2 REPORT

> TASK-020B完成Document / Section / Table / Lineage结构基础建设。未切换Retriever，未执行新的Retrieval A/B，未调用Live Provider。

## 1. 执行边界

- Root-001只读扫描：`D:\设计管理`。
- Root-002只使用已有020A Owner Approved Artifact兼容性样本，治理继续为`PENDING_APPROVAL`。
- 未修改正式8000、Retriever、BM25、Dense、RRF、Reranker、Router、Scope Guard、Preflight、Fact Path或Answer Engine。
- 未重建正式Qdrant，未生成正式Collection Embedding，Provider HTTP Requests=0。

## 2. Root-001结构指标

| 指标 | 值 |
|---|---:|
| Document Count | 498 |
| Document Object Coverage | 1.0 |
| Heading Coverage | 0.8775 |
| Section Coverage | 0.998 |
| Document→Section Parent Integrity | 1.0 |
| Table Header Coverage | 1.0 |
| Location Coverage | 1.0 |
| Atomic Evidence Parent Mapping | 1.0 |
| Document Role Coverage | 1.0 |
| Authority Coverage | 1.0 |
| Scope Coverage | 1.0 |
| Version Known Coverage | 0.0643 |
| Lineage Object Coverage | 1.0 |
| Metadata Conflicts | 5 |
| Registration Page Sample Accuracy | 1.0 |

## 3. Gold结构回放

- 达到 `STRUCTURE_REPRESENTABLE`：10/10。
- BA-001、BA-002、BA-004、BA-005、BA-006、BA-007、BA-008、BA-009、BA-010均具备Document/位置表达。
- BA-003虽Runtime为SOURCE_SCOPE_GOLD，但已有Gold Artifact仍可结构化表达。
- BA-010 Lineage：`LINEAGE_PARTIAL`，自动Join：`False`。

## 4. 结构化存储

写入 `data/shadow/document_intelligence_v2/`：documents、headings、sections、paragraphs、tables、table_rows、lineage、metadata_conflicts、atomic_evidence、legacy_evidence_id_map，以及 compatibility_samples。

## 5. 指标解释

Heading Coverage、Scope/Version Coverage等指标反映结构/字段是否存在，不等于分类准确率；Lineage Coverage低不代表失败，未声明来源关系的文档保持NOT_APPLICABLE。
本任务不宣称检索效果提升；Document-level/Section-level Retrieval A/B留给TASK-020C/020D。

- 构建耗时：14.579秒。

## 6. 停止点

TASK-020B = COMPLETE。等待架构评审，不启动020C，不修改正式系统。
