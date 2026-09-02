# Shadow 原子证据真实业务问题回放报告

> 本回放只对原子证据 JSONL 做透明关键词匹配，不调用 LLM、不重新运行向量检索，也不把关键词候选直接视为正确答案。

- 原子证据：`D:\AI智能体\AI设计管理RAG-V1\data\shadow\atomic_evidence\records.jsonl`
- 回放结果：`D:\AI智能体\AI设计管理RAG-V1\evaluation\atomic_evidence\real_business_queries.jsonl`
- 问题数量：10

## 1. 回放结果

| 问题 | 基线状态 | 原子层结果 | 候选数 | 最高候选 | 位置 |
|---|---|---|---:|---|---|
| BA-001 | GENERATED | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 202407幕墙设计专业培训.pptx | `{'slide': 23, 'title': '定义文件编制', 'text_index': 5}` |
| BA-002 | NO_EVIDENCE | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年设计管理总结.md | `{'line_start': 7, 'line_end': 7}` |
| BA-003 | STRUCTURE_INVALID | REGISTRATION_ONLY_CANDIDATE | 5 | 产品线设计方案比选典型案例汇编（厂房）.md | `{'line_start': 1, 'line_end': 1}` |
| BA-004 | STRUCTURE_INVALID | BODY_ATOMIC_CANDIDATE | 5 | 设计方案比选提示清单7.23.xlsx | `{'sheet_name': 'Sheet1', 'row_start': 89, 'row_end': 89, 'column_count': 10, 'header_row': 2}` |
| BA-005 | NO_EVIDENCE | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年半年总结.md | `{'line_start': 7, 'line_end': 7}` |
| BA-006 | NO_EVIDENCE | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年年度总结.md | `{'line_start': 7, 'line_end': 7}` |
| BA-007 | GENERATED | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年年度总结.md | `{'line_start': 7, 'line_end': 7}` |
| BA-008 | GENERATED | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年饶淇述职.md | `{'line_start': 7, 'line_end': 7}` |
| BA-009 | NO_EVIDENCE | LOW_CONFIDENCE_CONTENT_CANDIDATE | 5 | 2025年设计管理总结.md | `{'line_start': 7, 'line_end': 7}` |
| BA-010 | FACT_RESULT | REGISTRATION_ONLY_CANDIDATE | 5 | 新洲星谷科创中心价值创造清单.md | `{'line_start': 1, 'line_end': 1}` |

## 2. 解释

- `BODY_ATOMIC_CANDIDATE`：目标词也出现在文件名、标题或路径中，原子层找到了正文候选，仍需人工确认是否就是回答问题的证据。
- `LOW_CONFIDENCE_CONTENT_CANDIDATE`：只命中正文中的通用词，不能据此认定找到了答案。
- `REGISTRATION_ONLY_CANDIDATE`：只找到登记页、链接或 Wikilink，不能当作外部正文。
- `NO_ATOMIC_CANDIDATE`：当前 Root-001 的 Markdown/XLSX 原子层没有找到候选，不代表全库绝对没有答案；还可能在未纳入的 PDF/DOCX/PPTX、外部 Root-002 或尚未拆解的内容中。

## 3. 结论

- `BODY_ATOMIC_CANDIDATE`：1 题
- `LOW_CONFIDENCE_CONTENT_CANDIDATE`：7 题
- `REGISTRATION_ONLY_CANDIDATE`：2 题

当前回放只能证明原子证据层的覆盖边界，不能替代正式 Retriever 评价。下一阶段应先扩展 PDF/DOCX/PPTX 的细粒度证据，再做 Shadow A/B 检索。
