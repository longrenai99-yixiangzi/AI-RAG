# Retrieval Trace Persistence Design Report

> TASK-016D-2A：在 Shadow 环境补充 BM25、Dense、RRF、Reranker 和 Evidence Selection 逐阶段轨迹持久化。
>
> 本任务只增加评估能力，不修改正式 Retriever 排序逻辑、Evidence Selection、Answer Engine、8000 服务或正式 Qdrant。

## 1. 执行范围

- Knowledge Root：`Root-002`
- Shadow 路径：`D:\AI智能体\AI设计管理RAG-V1\data\shadow\root002_import`
- Shadow Collection：`root002_shadow_bge_m3`
- Shadow Qdrant 当前点数：`1847`
- 轨迹问题数：`10`（BA-001～BA-010）
- Embedding：只调用已存在的 BGE-M3 Shadow 查询能力，不写向量。
- LLM：未调用。
- Reranker：按 C-3 实际口径记录为未执行，不加载、不调参。

## 2. 轨迹 Schema

每题一个 JSON 文件：`evaluation/traces/BA-XXX.json`。

### 2.1 BM25 Top20

字段：`chunk_id`、`document_id`、`file_name`、`source_path`、`score`、`rank`。

### 2.2 Dense Top20

字段：`chunk_id`、`document_id`、`file_name`、`source_path`、`score`、`rank`。

### 2.3 RRF Top20

字段：`chunk_id`、`rrf_score`、`rank`、`source_bm25_rank`、`source_dense_rank`，以及文件和定位字段。

### 2.4 Reranker

字段：`executed`、`items`、`reason`。本批结果为：`executed=false`，`items=[]`。

后续启用 Reranker 时，`items` 使用 `chunk_id`、`score`、`rank`、`document_id`、`file_name`。

### 2.5 Evidence Selection

字段：`selected`、`source_id`、`selection_score`、`reason`，以及文件、角色、权威等级和 location。

当前保持 C-3 口径：RRF Top10 进入 Evidence Selection，最多输出 5 条 Evidence；RRF 第 11～20 名记录为 `outside_selection_input_top10`。

当前 `reason` 是评估脚本基于最终 Bundle 的可解释归因，不改变 Evidence Selection 内部逻辑。若要获得完全精确的内部淘汰原因，未来应让 Selector 原样返回决策事件。

## 3. 本次生成统计

| 指标 | 结果 |
|---|---:|
| 轨迹文件 | 10 |
| 每题 BM25 条目 | 20 |
| 每题 Dense 条目 | 20 |
| 每题 RRF 条目 | 20 |
| Evidence Selection 选中总数 | 50 |
| 正式 Qdrant 写入 | 0 |

## 4. 使用方式

1. 先看 `bm25_top20` 与 `dense_top20` 是否包含 Gold 文件或 Gold Chunk；
2. 再看 `rrf_top20` 是否把 Gold Chunk 融合到前 10；
3. 再看 `reranker.executed`，避免把未运行的 Reranker 当作失败原因；
4. 最后看 `evidence_selection.items` 的 `selected` 与 `reason`；
5. 对 `GOLD_OUT_OF_SCOPE` 问题，不把未命中当前 Root 误判为排序失败。

## 5. 验收标准

- 每题存在 BM25 Top20、Dense Top20、RRF Top20；
- 每个 RRF 条目可回溯 BM25/Dense 来源排名；
- 每个 RRF Top20 条目都有 Evidence Selection selected/reason；
- Reranker 是否执行明确记录；
- Source path、file name、document id、chunk id、location 可回查；
- 轨迹目录不被正式服务读取，不写正式 Qdrant。

## 6. 后续用途

该轨迹为 TASK-016D-2B 的 Evidence Ranking Shadow A/B 对比提供输入。后续可以逐题回答：

- Gold Chunk 是否被 BM25 找到；
- Dense 是否补回 BM25 未命中的 Chunk；
- RRF 是否把正确 Chunk 推进 Top10；
- Reranker 是否实际参与；
- Evidence Selection 在哪一步淘汰了正确证据。

