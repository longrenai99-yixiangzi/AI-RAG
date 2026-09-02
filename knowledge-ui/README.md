# 企业知识库前端 V0.1

按《企业知识库前端搭建方案 V0.1》实现的独立知识框架前端原型。

## 当前范围

- React + TypeScript + Vite；
- 首页、知识框架页、知识空间、知识节点、专题知识、知识来源；
- 3 个一级板块：设计管理、技术管理、科技管理；
- 3 个横向专题：EPC、价值创造、AI；
- 当前仅使用 `src/data/mock` Mock 数据；其中“技术管理 → 施工组织设计 → 总体施组”已完成 Domain、Category、KnowledgeNode、KnowledgeCard、Source、Case 的单对象图样板；
- 不接入 RAG、Embedding、向量数据库、真实 AI 或复杂权限。

## 启动

```powershell
cd D:\AI智能体\AI设计管理RAG-V1\knowledge-ui
npm install
npm run dev
```

独立开发模式默认访问：`http://127.0.0.1:5173/`。

当前已构建并挂载到 Internal Trial Service：

```text
http://172.16.110.17:8010/knowledge-os
```

原来的 Trial 问答页保留在：

```text
http://172.16.110.17:8010/trial
```

## 验证

```powershell
npm run build
```

## 数据边界

所有知识节点、专题、覆盖度、缺口、增长、热门内容与资料来源均为 V0.1 Mock 数据，后续才会接入真实知识库。

“总体施组”样板入口：

```text
http://172.16.110.17:8010/knowledge/technical-construction-1
```
