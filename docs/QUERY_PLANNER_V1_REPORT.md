# QUERY PLANNER V1 REPORT

> 规则式 Planner，只提供软约束；未使用LLM，也不执行候选硬过滤。

- Query Type Accuracy：{'numerator': 8, 'denominator': 10, 'rate': 0.8}
- Entity Detection Rate：{'numerator': 3, 'denominator': 5, 'rate': 0.6}
- Year Detection Rate：{'numerator': 4, 'denominator': 4, 'rate': 1.0}
- Organization Detection Rate：{'numerator': 3, 'denominator': 3, 'rate': 1.0}
- Specialty Detection Rate：{'numerator': 2, 'denominator': 2, 'rate': 1.0}
- Subquestion Coverage Rate：{'numerator': 4, 'denominator': 10, 'rate': 0.4}

Planner Error 与 Retrieval Error 分开记录；Planner 漏识别不会删除候选。
