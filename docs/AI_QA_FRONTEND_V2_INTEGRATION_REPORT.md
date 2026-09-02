# AI QA FRONTEND V2 INTEGRATION REPORT

## 页面与接口

- 工作台路由：`/ai`，直接渲染 `AIChat`，不再使用V0.1 Placeholder。
- V2接口：`POST /api/v2/query`、`POST /api/v2/feedback`。
- UI组件：本机对话历史、主问答区、引用来源、右侧来源详情、部分/冲突状态、反馈和折叠检索详情。

## 8010实际验证

- BA-001：ANSWERED；引用 1 条；状态正确=True
- BA-002：ANSWERED；引用 2 条；状态正确=True
- BA-004：ANSWERED；引用 1 条；状态正确=True
- BA-008：CONFLICTING_ANSWER；引用 3 条；状态正确=True
- BA-010：PARTIAL_ANSWER；引用 8 条；状态正确=True
- 反馈提交：True；Growth Proposal：FG_6ec4acd2963e527f

## 安全边界

- 8010 localhost试用；8000未改动。
- 前端不复制Retriever逻辑；未调用Provider、未注入Gold、未发布知识。

TASK-020H.1 = COMPLETE
