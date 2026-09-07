# 企业知识库前端 V0.1

按《企业知识库前端搭建方案 V0.1》实现的独立知识框架前端原型。

## 当前范围

- React + TypeScript + Vite；
- 首页、知识框架页、知识空间、知识节点、专题知识、知识来源；
- 3 个一级板块：设计管理、技术管理、科技管理；
- 3 个横向专题：EPC、价值创造、AI；
- 知识框架、知识空间和来源页面当前主要使用 `src/data/mock` Mock 数据；其中“技术管理 → 施工组织设计 → 总体施组”已完成 Domain、Category、KnowledgeNode、KnowledgeCard、Source、Case 的单对象图样板；
- “AI问答”页面已接入 Internal Trial 的 `/api/v2/query`、`/api/v2/feedback` 和反馈闭环接口；不接入复杂权限。

## 启动

```powershell
cd D:\AI智能体\AI设计管理RAG-V1\knowledge-ui
npm install
npm run dev
```

独立开发模式默认访问：`http://127.0.0.1:5173/`。

当前已构建并挂载到 Internal Trial Service：

```text
http://127.0.0.1:8010/knowledge-os
```

批量验收工作台：

```text
http://127.0.0.1:8010/batch
```

工作台支持本机文件夹选择上传、来源目录只读预览、批量批准进入 Shadow、自动生成结构化验收题、批量回归和异常清单。浏览器文件夹上传后会自动批准进入 Shadow、生成验收题并批量回归；服务器路径仍需手动点击一次批准。批处理数据只写入 `data/shadow/batch_workflow`，不自动发布正式知识。

原来的 Trial 问答页保留在：

```text
http://127.0.0.1:8010/trial
```

## 验证

```powershell
npm run build
```

## 数据边界

知识节点、专题、覆盖度、缺口、增长、热门内容与资料来源仍主要为 V0.1 Mock 数据；AI问答和反馈闭环使用真实 Internal Trial API。

“总体施组”样板入口：

```text
http://172.16.110.17:8010/knowledge/technical-construction-1
```
