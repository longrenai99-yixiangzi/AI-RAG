# BA-004 Answer Structure Hardening Report

> 本报告仅记录 Shadow Answer Structure 验证；未修改 Retriever、BM25、Dense、RRF、Embedding、Reranker、Router、Scope Guard、正式 Qdrant 或 BA-010 Fact Path。

## 1. Failure Reproduction

- 冻结输入：`evaluation\v1_business_acceptance\BA-004.json`
- 历史状态：`STRUCTURE_INVALID`
- 历史问题：`section_map.evidence_boundary` 使用自然语言，而不是 Claim ID。
- available_claim_ids：`['C1']`
- available_evidence_ids：`['S1', 'S2', 'S3', 'S4', 'S5']`
- 错误类型：`['UNKNOWN_CLAIM_ID']`
- 历史快照未持久化原始 LLM 文本，因此本次复现使用已保存的 parsed_response；未伪造 raw_llm_response。

## 2. Frozen Evidence and Atomic Claims

- 文件：`设计方案比选提示清单7.23.xlsx`
- Sheet：`Sheet1`
- 原始位置：第 89 行
- Evidence ID：`S2`
- 方案一：传统镀锌钢管
- 方案二：新型材料加强氯化聚氯乙烯(PVC-C)管材
- 原表备注：根据实际情况选用，建议选用方案二
- 目标行摘录：第89行：设计方案比选提示清单：86 | 列2： | 列3：管材变更 | 列4：自动喷淋系统采用传统统镀锌钢管 | 列5：自动喷淋系统采用新型材料加强氯化聚氯乙烯(PVC-C)管材 | 列6：/ | 列7：方案一为传统施工方法及材质，方案二为C-PVC为新型材质，施工方便， 提高工效，新型材料重新认价（DN80以下支管可用） | 列8：方案一人工安装费高，效率低，方案二人工成本降低4. 71元/m（15定额），材料效益增加2. 79元/m（含谷项目为例） | 列9：根据实际情况选用，建议选用方案二 | 列10：施工图设计阶段

新 Shadow Schema 使用独立 Claim：

- `OPTION`：每种方案一个 Claim；
- `RECOMMENDATION`：推荐意见独立成 Claim；
- `EVIDENCE_BOUNDARY`：证据范围独立成 Claim；
- `claims[].evidence_ids` 只能使用 Evidence ID；`section_map` 只能使用 Claim ID。

### Atomic Claims（以最终生成记录为准）

```json
[
  {
    "claim_id": "C1",
    "claim_type": "OPTION",
    "claim_text": "自动喷淋系统采用传统镀锌钢管",
    "evidence_ids": [
      "S2"
    ]
  },
  {
    "claim_id": "C2",
    "claim_type": "OPTION",
    "claim_text": "自动喷淋系统采用新型材料加强氯化聚氯乙烯(PVC-C)管材",
    "evidence_ids": [
      "S2"
    ]
  },
  {
    "claim_id": "C3",
    "claim_type": "RECOMMENDATION",
    "claim_text": "根据实际情况选用，建议选用方案二",
    "evidence_ids": [
      "S2"
    ]
  }
]
```

### Final Section Map

```json
{
  "conclusion": [],
  "options": [
    "C1",
    "C2"
  ],
  "recommendation": [
    "C3"
  ],
  "evidence_boundary": []
}
```

## 3. Section Map and Repair Trace

处理顺序：Parse → Schema Validation → Claim Validation → Section Map Validation → Citation Validation。

- 20 次状态：`{'GENERATED': 20}`
- Section Map Repair：`0` 次
- Deterministic Claim Render：`0` 次
- Claim Validator：`20/20`
- Section Map Validator：`20/20`
- Citation Validator：`20/20`
- Unsupported Claim：`0`
- Invalid Evidence ID：`0`

Repair 与确定性渲染均记录 `claims_changed=false`、`new_facts_added=false`；没有执行 S1→C1 的位置替换。

## 4. 20 次稳定性结果

| Run | Final Status | Repair Type | Claim | Section Map | Citation | Fact Stability |
|---:|---|---|---|---|---|---|
| BA-004-run-01 | GENERATED | - | True | True | True | True |
| BA-004-run-02 | GENERATED | - | True | True | True | True |
| BA-004-run-03 | GENERATED | - | True | True | True | True |
| BA-004-run-04 | GENERATED | - | True | True | True | True |
| BA-004-run-05 | GENERATED | - | True | True | True | True |
| BA-004-run-06 | GENERATED | - | True | True | True | True |
| BA-004-run-07 | GENERATED | - | True | True | True | True |
| BA-004-run-08 | GENERATED | - | True | True | True | True |
| BA-004-run-09 | GENERATED | - | True | True | True | True |
| BA-004-run-10 | GENERATED | - | True | True | True | True |
| BA-004-run-11 | GENERATED | - | True | True | True | True |
| BA-004-run-12 | GENERATED | - | True | True | True | True |
| BA-004-run-13 | GENERATED | - | True | True | True | True |
| BA-004-run-14 | GENERATED | - | True | True | True | True |
| BA-004-run-15 | GENERATED | - | True | True | True | True |
| BA-004-run-16 | GENERATED | - | True | True | True | True |
| BA-004-run-17 | GENERATED | - | True | True | True | True |
| BA-004-run-18 | GENERATED | - | True | True | True | True |
| BA-004-run-19 | GENERATED | - | True | True | True | True |
| BA-004-run-20 | GENERATED | - | True | True | True | True |

验收：**20/20 最终答案可用**

## 5. 最终实际答案

## 结论
- 可以采用以下 2 种方案进行比选：[S2]
## 可比选方案
- 自动喷淋系统采用传统镀锌钢管 [S2]
- 自动喷淋系统采用新型材料加强氯化聚氯乙烯(PVC-C)管材 [S2]
## 补充说明
- 根据实际情况选用，建议选用方案二 [S2]
## 证据边界
- evidence_insufficient

### Citation

- 来源文件：`设计方案比选提示清单7.23.xlsx`
- Sheet：`Sheet1`；位置：第 89 行；Evidence：`S2`
- 原始证据摘录：第89行：设计方案比选提示清单：86 | 列2： | 列3：管材变更 | 列4：自动喷淋系统采用传统统镀锌钢管 | 列5：自动喷淋系统采用新型材料加强氯化聚氯乙烯(PVC-C)管材 | 列6：/ | 列7：方案一为传统施工方法及材质，方案二为C-PVC为新型材质，施工方便， 提高工效，新型材料重新认价（DN80以下支管可用） | 列8：方案一人工安装费高，效率低，方案二人工成本降低4. 71元/m（15定额），材料效益增加2. 79元/m（含谷项目为例） | 列9：根据实际情况选用，建议选用方案二 | 列10：施工图设计阶段

## 6. 通用 OPTION_QUERY 结构测试

测试使用不同已持久化 Evidence Bundle，仅验证通用选项结构，不以 LLM 内容质量作为通过条件。

| Case | Policy | Evidence 数 | Schema | Claim | Section Map | Citation | Result |
|---|---|---:|---|---|---|---|---|
| OPTION-01 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-02 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-03 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-04 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-05 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-06 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-07 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-08 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-09 | OPTION_QUERY | 5 | True | True | True | True | PASS |
| OPTION-10 | OPTION_QUERY | 5 | True | True | True | True | PASS |

- 通用测试通过：`10/10`
- 这些测试未写入 BA-004 专用材料名、问题全文或正确答案；OPTION_QUERY 识别只使用通用列举表达。

## 7. BA 回归快照

以下为既有 Shadow 产物读取快照，没有重新检索或重新改写其他 BA 题：

| Question | Existing Status | Artifact |
|---|---|---|
| BA-001 | GENERATED | `evaluation\v1_business_acceptance\BA-001.json` |
| BA-002 | GENERATED | `evaluation\ba002_formula_semantic_alignment\BA-002.json` |
| BA-007 | GENERATED | `evaluation\section_mapping_stability\BA-007\run_30.json` |
| BA-008 | GENERATED | `evaluation\scope_guard_leakage_cleanup\BA-008.json` |
| BA-010 | True | `evaluation\answer_stability\BA-010\run_10.json` |

- BA-002：保留公式语义边界；
- BA-008：保留 Scope Guard 结果；
- BA-010：未重新解析 Excel，保留既有 FACT_RESULT；
- BA-001、BA-007：仅读取既有 Shadow 结果；
- BA-003、BA-006、BA-009：未改写。

## 8. 结论

BA-004 的根因位于 Answer Structure：自然语言被写入 `section_map`，破坏了 Claim/Evidence 两个 ID namespace。当前 Shadow 修复只允许一次 Section Map Repair；若 Claims、Evidence 和 Citation 均有效，则可以使用 Deterministic Claim Render，但不修改 Claim、不新增事实、不放宽 Validator。
