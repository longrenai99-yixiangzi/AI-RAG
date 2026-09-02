# app/core/answer

未来职责：

- Answer Router；
- FACT、POLICY、CASE、METHOD、GENERAL 问题路由；
- 事实直答、证据型生成和无可靠依据时的拒答；
- 管理 LLM Provider 与答案生成策略。

迁移来源主要是当前 `app/answer.py` 和 `app/llm.py`。当前阶段保留原有调用链，不改变答案逻辑。
