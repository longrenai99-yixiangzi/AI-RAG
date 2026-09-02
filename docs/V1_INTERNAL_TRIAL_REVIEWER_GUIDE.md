# V1.0 Internal Trial Reviewer Guide

## 1. 评价顺序

1. 先看回答状态，不要把 Provider 不可用误判为知识库没有答案；
2. 再看 Evidence 文件名、Root、治理状态、Document Role 和 Authority Level；
3. 最后按页码、行号、段落、表格、Sheet/Row 或 Slide 回查原文；
4. 对制度问题，检查是否被案例或培训材料替代；
5. 对案例问题，检查是否误用了制度结论；
6. 对统计问题，检查是否显示事实权威来源和原始行范围。

## 2. Root 判断

| Root | 业务解释 |
|---|---|
| Root-001 | 正式知识基线 / 只读 |
| Root-002 | Shadow资料 · 待审批 |
| Root-003 | Trial不可用 |

Root-002 的内容可以用于本轮 Shadow 试用审查，但不能作为正式制度或正式知识源发布依据。

## 3. BA-010 专项

确认页面同时提供：

- `Fact Authority Source`；
- `Retrieval Context`；
- Workbook、`价值创造` Sheet、source rows、source locations、Evidence ID；
- 总有效明细 80 条；
- 利润 > 0 的增加效益 37 条；
- 利润为空/未判定 43 条；
- 第 88 行汇总公式不作为明细。

“43 条利润为空/未判定”不能评分为“43 条没有效益”。

## 4. 反馈建议

业务意见应尽量说明：

- 是检索错、证据不完整，还是回答表达问题；
- 正确来源文件名称和位置；
- 是否需要补充 Root-001 资料或审批 Root-002；
- Citation 是否能够回查原文；
- 是否存在制度/案例/模板混淆。

## 5. 汇总导出

随时执行：

```powershell
D:\AI智能体\AI设计管理RAG-V1\.venv\Scripts\python.exe D:\AI智能体\AI设计管理RAG-V1\scripts\export_trial_feedback.py
```

汇总文件：

```text
D:\AI智能体\AI设计管理RAG-V1\evaluation\internal_trial\trial_feedback_summary.json
```

