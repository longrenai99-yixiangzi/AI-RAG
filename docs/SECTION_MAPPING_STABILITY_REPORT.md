# Section Mapping Stability Report

> TASK-016E-3.1：Shadow Section Mapping Hardening 与 BA-007 30 次稳定性回归。
> 未修改 Retriever、Evidence Selection、Embedding、RRF、Reranker、正式 Qdrant、8000 服务或 BA-010 Fact Answer Path。

## 1. 基线复现

- 基线文件：`evaluation/answer_stability/BA-007/run_05.json`
- available_claim_ids：`['C1', 'C2']`
- available_evidence_ids：`['S1', 'S2', 'S3', 'S4', 'S5']`
- invalid_section_references：`[{'field': 'evidence', 'id': 'S1', 'error': 'EVIDENCE_ID_IN_SECTION_MAP'}]`
- 原始问题：section_map.evidence 使用 S1；S1 属于 Evidence namespace，不属于 Claim namespace。

## 2. Namespace 规则

- Claim ID namespace：`C1、C2、C3...`
- Evidence ID namespace：`S1、S2、S3...`
- `section_map`：只允许 Claim ID。
- `claims[].evidence_ids`：只允许 Evidence ID。

## 3. 30 次稳定性结果

- 状态分布：`{"GENERATED": 29, "LLM_ERROR": 1}`
- SECTION_MAP_ONLY_REPAIR 触发：0
- Repair 成功：0
- EVIDENCE_ID_IN_SECTION_MAP：0
- UNKNOWN_CLAIM_ID：0
- Claim Validator 通过：29/30
- Citation Validator 通过：29/30
- Unsupported Claim：0
- Invalid Evidence ID：0
- Provider Error：1
- 验收结论：**未达到30/30，保留失败样本继续诊断**

## 4. 失败样本

- `BA-007-run-22`：status=`LLM_ERROR`；stage=`{'primary': 'I PROVIDER_FAILURE', 'secondary': []}`；raw=`evaluation/section_mapping_stability/BA-007/run_22.json`

## 5. Repair 安全检查

- Repair 只允许改变 section_map；脚本验证 claims、claim_text、evidence_ids 和 evidence_insufficient 未改变。
- 未执行 S1→C1 等位置替换；Repair 必须基于实际 Claim IDs 重新生成映射。
- Repair 失败保持 STRUCTURE_INVALID，不强制改为 GENERATED。

## 6. 路径结论

- BA-007：仅对 Shadow Prompt 增加 Section Map namespace 约束，并增加 Section Map Validator 与受限 Repair；未修改正式 Answer Engine。
- BA-010：未运行、未修改、未重新计算；Fact Answer Path 保持原有确定性结果。
- 通过本次验收后，BA-007 才可继续作为 Shadow 普通知识问答路径；正式接入仍需单独审批。
