# Shadow 原子证据 Retrieval A/B 验证报告

> 本报告只比较既有 Shadow Chunk 证据和原子证据候选，不调用 LLM，不写 Qdrant，不把候选命中当作 Gold 真值。

- 原子证据：`D:\AI智能体\AI设计管理RAG-V1\data\shadow\atomic_evidence\records.jsonl`
- 逐题结果：`D:\AI智能体\AI设计管理RAG-V1\evaluation\atomic_evidence\retrieval_ab.jsonl`
- 当前 BA Gold 的 `expected_files` 为空，因此本报告不计算 Recall，不宣称检索准确率提升。

## 1. A/B 结果

| 问题 | Gold Scope | 基线状态 | 基线首条来源 | 原子首条候选 | 原子定位 | 原子与基线文件重合 |
|---|---|---|---|---|---|---|
| BA-001 | GOLD_UNCONFIRMED | GENERATED | 设计任务书.md | 202407幕墙设计专业培训.pptx | `{'slide': 23, 'title': '定义文件编制', 'text_index': 5}` | - |
| BA-002 | GOLD_UNCONFIRMED | NO_EVIDENCE | EPC设计管理经验总结（光谷实验中学）.docx | 2025年设计管理总结.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-003 | GOLD_UNCONFIRMED | STRUCTURE_INVALID | 《项目设计管理手册》.pdf | 产品线设计方案比选典型案例汇编（厂房）.md | `{'line_start': 1, 'line_end': 1}` | 产品线设计方案比选典型案例汇编（厂房）.md |
| BA-004 | GOLD_UNCONFIRMED | STRUCTURE_INVALID | 设计方案比选提示清单7.23.xlsx | 设计方案比选提示清单7.23.xlsx | `{'sheet_name': 'Sheet1', 'row_start': 89, 'row_end': 89, 'column_count': 10, 'header_row': 2}` | 设计方案比选提示清单7.23.xlsx |
| BA-005 | GOLD_UNCONFIRMED | NO_EVIDENCE | EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx | 2025年半年总结.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-006 | GOLD_UNCONFIRMED | NO_EVIDENCE | 关于印发中建三局2026年设计与技术工作计划的通知.pdf | 2025年年度总结.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-007 | GOLD_UNCONFIRMED | GENERATED | 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf | 2025年年度总结.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-008 | GOLD_UNCONFIRMED | GENERATED | EPC设计管理经验总结（丰台崔村旧改项目）.pptx | 2025年饶淇述职.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-009 | GOLD_UNCONFIRMED | NO_EVIDENCE | 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf | 2025年设计管理总结.md | `{'line_start': 7, 'line_end': 7}` | - |
| BA-010 | GOLD_UNCONFIRMED | FACT_RESULT | 方案比选与价值创造清单方案比选及价值创造.xlsx | 新洲星谷科创中心价值创造清单.md | `{'line_start': 1, 'line_end': 1}` | - |

## 2. 可解释统计

| 指标 | 数量 |
|---|---:|
| 题目数 | 10 |
| `GOLD_UNCONFIRMED` | 10 |
| 基线存在精确定位 | 5 |
| 原子候选存在精确定位 | 10 |
| 原子首条候选为登记页 | 2 |
| 原子候选与基线文件有重合 | 2 |

## 3. 结论

1. 原子层已经能够把证据细化到 Markdown 行、XLSX 行、PDF 页内行、DOCX 段落/表格行和 PPTX 文本行。
2. 原子层仍会被年度总结等通用文本干扰；因此必须继续加入实体、年份、指标字段和来源角色约束。
3. BA-003、BA-010 等问题只能命中登记页时，说明 Source Closure 仍未完成，不能把登记页当正文。
4. 在 `expected_files` 补齐前，本报告只能作为定位能力诊断，不能作为 Recall 评价。

## 4. 下一步

将原子证据搜索与文档实体、年份、字段和 authority 进行 Shadow 融合，先做 A/B，再考虑接入正式 Retriever。
