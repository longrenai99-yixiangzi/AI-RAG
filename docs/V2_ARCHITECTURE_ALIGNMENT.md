# V2.0 架构衔接结论

## 结论

`AI设计管理自生长知识库 V2.0` 可与当前 V1 Shadow 架构连续衔接，不需要重新搭建项目，也不需要推翻现有 RAG、Document Engine、Qdrant、BGE-M3 或 8010 Trial。

V2.0 不是替代方案，而是对已完成能力的重新组织：

| V2.0 层 | 已有实现 | 当前缺口 |
|---|---|---|
| Document Intelligence | Loader、Metadata、Document Profile、Atomic Evidence | Heading Tree、Section Object、Table Object、Source Lineage 未统一成正式 Shadow 数据模型 |
| 分层检索 | Profile Retrieval、Atomic Exact、BM25/Dense/RRF Shadow | Document → Section → Atomic 尚未形成统一 Candidate Pool |
| 表格双表示 | XLSX Loader、BA-010 Deterministic Fact Aggregator | Table Semantic Index 与 Structured Table Query 尚未统一 |
| 可信证据 | Evidence Selector、Claim/Citation Validator、Scope Guard | Subquestion Coverage、Conflict 和 Evidence Type 未统一 |
| 问答路由 | Router、Direct Fact、Derived Fact、Option、Evidence Only | Query Planner 与多子问题计划未统一 |
| 自生长 | Trial Feedback、Audit、Gold/Regression 基础 | Feedback → Failure Atlas → Growth Candidate → Review 尚未闭环 |

## V2.0 前置结论

V2.0 强制要求先执行 `TASK-020A`。当前 BA-001～BA-010 的 `expected_files`、`expected_locations` 均未由业务确认；因此不能进入 Document Intelligence 或 Retriever 改造，也不能用 Recall/MRR 声称系统变准。

## 当前执行状态

已启动：`TASK-020A — Business Gold + Failure Atlas`。

执行边界：

- 复用已持久化 Shadow Fresh Run 与 Atomic Locator；
- 不修改正式 Retriever；
- 不调用 LLM；
- 不修改 8000、正式 Qdrant、Root-001 源文件；
- Root-002 只使用既有冻结 Shadow Artifact，不扫描新目录。

## 后续顺序

```text
020A Business Gold + Failure Atlas
  ↓
020B Document Intelligence V2
  ↓
020C Query Planner + Hierarchical Retrieval
  ↓
020D Hybrid Candidate Fusion V2
  ↓
020E Verified Evidence Bundle V2
  ↓
020F Answer Engine Integration V2
  ↓
020G Knowledge Self-Growth Loop
  ↓
020H 8010 A/B Business Acceptance
```
