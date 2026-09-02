# DOCX STRUCTURED EVIDENCE LINKAGE REPORT

> TASK-020F.1.1：仅审计并使用冻结 Shadow 工件；未读取 Root-002 实体文件。

## 审计结论

- Status：`DOCX_STRUCTURED_ARTIFACT_INCOMPLETE`。
- 当前 Runtime 已定位 DOCX Table11，但 Document Intelligence V2 没有该 DOCX 的 Document/Table/Row/Atomic 行级工件。
- Runtime Table11 Evidence IDs：['e85d4bc4-b1be-5003-9e57-d1bbcd56016e', '77d66be8-8aa8-5301-b350-d36c33aa4fd2']；位置：{'table': 11, 'rows': 37, 'columns': 7}。
- DOCX 可用行 / 已映射行 / 已映射单元格：0 / 0 / 0。

## Owner Artifact 边界

- 检测到 Owner Gold 的 Table11 行定位 `4-37`，但其标记为 `artifact_only=true`、`gold_type=PARTIAL_GOLD`。
- 为保持 `Gold Runtime Injection=0`，这些行仅用于离线审计，不进入 Runtime Bundle、Claim、Citation 或聚合计算。
- DOCX/XLSX 继续 `LINEAGE_PARTIAL`；未执行自动关联。

## Runtime 行级事实

- 专业类别、各专业条数与总条数：均不可回答。
- 利润字段与增加效益条数：证据不足。
- BA-010 继续 `PARTIAL_ANSWER`；不会使用 XLSX 或 Gold 数字补足。

## Renderer 指标

- Raw Evidence Dump Rate：0.0
- Internal Column Label Leakage：0
- Malformed Unicode In Answer：0
- Rendered Claim Validation：1.0

## 后续前置条件

须在后续治理批准后，仅针对该确切 DOCX Owner Source 重新生成非 Gold 的 Table11 Row/Cell Structured Artifact；在此之前不得进入 020G。

TASK-020F.1.1 = COMPLETE

等待架构评审。
