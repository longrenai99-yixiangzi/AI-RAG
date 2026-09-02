# FINAL FAILURE ATLAS REPORT

> TASK-020A.3 是诊断基线，不是修复任务。Provider关闭不归类为 Generation Failure。

## 1. 结论

- 测试：10题。
- Primary Failure：`{"NO_FAILURE": 1, "DOCUMENT_MISSED": 2, "SOURCE_SCOPE_MISSING": 5, "SECTION_MISSED": 1, "SOURCE_LINEAGE_FAILURE": 1}`。
- Runtime Status：`{"PROVIDER_DISABLED_BY_TEST_POLICY": 4, "SOURCE_SCOPE_MISSING": 5, "FACT_RESULT": 1}`。

## 2. Failure Atlas

| BA | Gold Type | Runtime Source | Document | Section | Selected Evidence | Primary | Secondary | Business Flag |
|---|---|---:|---:|---:|---:|---|---|---|
| BA-001 | `FULL_GOLD` | True | True | True | True | `NO_FAILURE` | `None` | `` |
| BA-002 | `FULL_GOLD` | True | False | False | False | `DOCUMENT_MISSED` | `None` | `` |
| BA-003 | `SOURCE_SCOPE_GOLD` | False | False | False | False | `SOURCE_SCOPE_MISSING` | `None` | `` |
| BA-004 | `FULL_GOLD` | True | True | False | True | `SECTION_MISSED` | `None` | `` |
| BA-005 | `FULL_GOLD` | False | False | False | False | `SOURCE_SCOPE_MISSING` | `None` | `` |
| BA-006 | `FULL_GOLD` | False | False | False | False | `SOURCE_SCOPE_MISSING` | `None` | `` |
| BA-007 | `FULL_GOLD` | False | False | False | False | `SOURCE_SCOPE_MISSING` | `None` | `` |
| BA-008 | `FULL_GOLD` | True | False | False | False | `DOCUMENT_MISSED` | `None` | `` |
| BA-009 | `FULL_GOLD` | False | False | False | False | `SOURCE_SCOPE_MISSING` | `None` | `` |
| BA-010 | `PARTIAL_GOLD` | True | True | False | False | `SOURCE_LINEAGE_FAILURE` | `GOLD_BOUNDARY_VIOLATION` | `GOLD_BOUNDARY_VIOLATION` |

## 3. 关键问题回答

1. Source Scope问题：5题。
2. Runtime有Source但Document未召回：2题。
3. Document已召回但Section丢失：1题。
4. Section存在但Evidence丢失：0题。
5. Evidence被排序/选择丢失：0题。
6. Evidence足够但Answer Coverage失败：0题。
7. Structured Query失败：0题。
8. Scope错误：0题。
9. Citation错误：0题。
10. 总体数量最多的是 Source Scope 缺口，但它是治理/运行范围问题，不应处罚 Retriever；在已进入 Runtime 的题目中，直接的“资料存在但答不到”断点是 Document Missed（2题）和 Section Missed（1题），BA-010另有Source Lineage边界越界。

## 4. Retrieval Baseline Metrics

```json
{
  "eligible_retrieval_questions": 5,
  "document_recall_at_1": {
    "numerator": 1,
    "denominator": 5,
    "rate": 0.2
  },
  "document_recall_at_3": {
    "numerator": 1,
    "denominator": 5,
    "rate": 0.2
  },
  "document_recall_at_5": {
    "numerator": 1,
    "denominator": 5,
    "rate": 0.2
  },
  "section_hit_rate": {
    "numerator": 1,
    "denominator": 5,
    "rate": 0.2
  },
  "gold_evidence_recall_at_5": {
    "numerator": 1,
    "denominator": 5,
    "rate": 0.2
  },
  "gold_evidence_recall_at_10": {
    "numerator": 2,
    "denominator": 5,
    "rate": 0.4
  },
  "gold_evidence_recall_at_20": {
    "numerator": 3,
    "denominator": 5,
    "rate": 0.6
  },
  "selected_gold_evidence_rate": {
    "numerator": 2,
    "denominator": 5,
    "rate": 0.4
  },
  "scope_accuracy": {
    "not_evaluated": true,
    "reason": "No new Scope Guard decision in this baseline run."
  },
  "citation_location_accuracy": {
    "numerator": 0,
    "denominator": 1,
    "rate": 0.0
  },
  "structured_fact_accuracy": {
    "numerator": 0,
    "denominator": 1,
    "rate": 0.0
  },
  "safe_refusal_accuracy": {
    "numerator": 1,
    "denominator": 1,
    "rate": 1.0
  },
  "partial_answer_accuracy": {
    "numerator": 0,
    "denominator": 1,
    "rate": 0.0
  }
}
```

## 5. TASK-020B Input Requirements

```json
{
  "schema_version": "task_020b_input_requirements.v1",
  "source_task": "TASK-020A.3",
  "no_implementation_in_this_task": true,
  "requirements": [
    {
      "failure_type": "SOURCE_SCOPE_MISSING",
      "count": 5,
      "priority": "P0",
      "requirement": "Document Intelligence V2 必须区分已批准运行范围与登记页/外部来源，保留 Source Scope 缺口，不误罚 Retriever。"
    },
    {
      "failure_type": "DOCUMENT_MISSED",
      "count": 2,
      "priority": "P1",
      "requirement": "增加 document-level profile、实体别名和文件级召回诊断。"
    },
    {
      "failure_type": "SECTION_MISSED",
      "count": 1,
      "priority": "P1",
      "requirement": "增强 heading tree、section boundary、页/表/行级定位和候选局部窗口。"
    },
    {
      "failure_type": "SOURCE_LINEAGE_FAILURE",
      "count": 1,
      "priority": "P0",
      "requirement": "建立来源版本、DOCX/XLSX行级血缘校验，禁止不确定来源拼接。"
    }
  ]
}
```

## 6. 安全边界

- 未修改 Retriever、Router、Scope Guard、Answer Engine、Embedding、正式 Qdrant、8000或8010运行逻辑。
- 未调用 Live Provider；`PROVIDER_DISABLED_BY_TEST_POLICY` 不产生 Generation Failure。
- 未扫描新 Root-002、未扫描 Root-003、未向检索过程注入Gold原文。

## 7. 停止点

TASK-020A = COMPLETE。等待架构评审，不自动进入 TASK-020B。
