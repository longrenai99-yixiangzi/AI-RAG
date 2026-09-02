# Document Intelligence V2 Schema

所有对象使用 `schema_version=document_intelligence.v2`。

## 对象层级

`Document → Heading Tree → Section → Paragraph/Table → Atomic Evidence`。

## Document

包含 `document_id`、`knowledge_root_id`、`source_path`、`file_name`、`file_type`、`content_hash`、`document_profile`、`source_lineage`、`structure`、`metadata_quality`。

## Profile

`document_type`、`document_role`、`business_domain`、`organization`、`project`、`specialty`、`year`、`version`、`status`、`authority_level`、`applicable_scope`、`entities`、`metrics` 均保存 `value/source/confidence`。

## Section / Paragraph / Table

Section独立保存父子关系和起止位置；Paragraph保存 `section_id`、文本、顺序、位置和样式；Table同时保存语义表示与结构化表示。

## Atomic Evidence

保留既有 `evidence_id`，新增 `document_id`、`section_id`、`paragraph_id/table_id`、`parent_heading_path`。当前未生成新的Evidence ID，因此映射为同ID不变。

## Lineage

支持 `LINEAGE_CONFIRMED`、`LINEAGE_PARTIAL`、`LINEAGE_NOT_CONFIRMED`、`LINEAGE_NOT_APPLICABLE`，关系包括 `REGISTER_POINTS_TO`、`DERIVED_FROM`、`SUPPORTING_SOURCE`、`STRUCTURED_DETAIL_OF` 等。
