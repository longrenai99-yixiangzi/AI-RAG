# Dense Retrieval + Reranker Shadow 验证报告

> 任务：TASK-011 Dense Retrieval + Reranker Shadow 验证  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 验证日期：2026-08-22  
> 状态：Shadow 验证完成，未接入生产问答链路

## 1. 执行边界

本次验证严格限制在独立 Shadow 环境：

- 未修改 `app/retriever.py`；
- 未修改 `app/main.py`；
- 未连接生产 Qdrant collection；
- 未执行全量 Embedding；
- 未影响现有问答；
- 未修改 Python、Torch 或 CUDA 环境。

## 2. 新增实现

### 2.1 DenseProvider

新增：

```text
app/retrieval/dense_provider.py
```

实现 `BGEM3DenseProvider`：

- 使用本地 BGE-M3 权重；
- 生成 Chunk 和 Query Dense 向量；
- 使用 `QdrantClient(location=":memory:")`；
- collection 名称为 `gold_shadow_bge_m3`；
- 向量维度 1024，Cosine 距离；
- 只建立内存 collection，进程结束后释放；
- 不连接 `data/qdrant`，不连接生产 collection。

本次使用的本地模型路径：

```text
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3
```

该路径属于旧工作区的既有模型文件，本次只读使用，未复制、下载或修改。

### 2.2 Reranker

新增：

```text
app/retrieval/reranker_provider.py
```

实现 `BGERerankerProvider`：

- 使用本地 `bge-reranker-v2-m3`；
- 输入 Query + 候选 passages；
- 输出候选分数；
- 不负责 BM25、Qdrant 或向量写入；
- 在 Hybrid RRF Top-N 后执行。

本次使用的本地模型路径：

```text
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3
```

当前环境为 `transformers 5.15.0 + FlagEmbedding 1.4.0`，FlagEmbedding 旧调用依赖的 tokenizer 方法已被 Transformers 5 移除。Provider 内增加了兼容 shim，用等价的特殊 token、pair 拼接和截断逻辑适配，不升级任何依赖。

## 3. Shadow 检索流程

```text
Query
  -> Query Analysis
  -> BM25
  -> BGE-M3 Dense / 独立内存 Qdrant
  -> RRF
  -> Top-N
  -> bge-reranker-v2-m3
  -> Context Builder
  -> Citation
```

`HybridRetriever` 新增可选 Reranker 参数，但没有改动旧 `app/retriever.py`。未传入 Reranker 时仍保持 BM25 + Dense + RRF Shadow 行为。

## 4. 验证数据范围

测试读取：

```text
tests/gold_questions/golden_questions.yaml
```

本次使用 50 个 Gold Questions，并为每个问题建立 1 个独立 Gold Chunk，形成 50 Chunk Shadow Corpus：

- BM25-only：使用真实 BM25；
- Hybrid：使用真实 BGE-M3 Dense + 内存 Qdrant；
- Hybrid+Reranker：使用真实 BGE-M3 结果 + 真实 bge-reranker-v2-m3。

这不是全库评测。由于每个 Gold Chunk 包含对应问题和关键词，结果主要验证模型、接口、RRF、Reranker、Context 和 Citation 链路能够工作，不能外推为企业真实全库准确率。

## 5. 指标结果

| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation 完整率 |
|---|---:|---:|---:|---:|---:|
| BM25-only | 100% | 100% | 100% | 1.00 | 100% |
| Hybrid | 100% | 100% | 100% | 1.00 | 100% |
| Hybrid + Reranker | 100% | 100% | 100% | 1.00 | 100% |

### 5.1 结果解释

- 三组结果相同，说明在这个 50 Chunk 定向 Shadow Corpus 上，BM25 已能直接命中 Gold Chunk；
- 本次数据不能证明 Dense 或 Reranker 对真实全库有增益；
- 后续必须使用真实 Chunk、人工 expected_files 和更难的近义/跨文档问题评估增益；
- Citation 完整率 100% 表示 Top-K 结果的 chunk_id、file_name、source_path、location 能进入 Context 并通过 Citation 校验。

## 6. 测试执行

模型 Shadow 测试默认跳过，避免普通测试每次加载约 2.3GB 权重。显式验证命令为：

```powershell
$env:RUN_MODEL_SHADOW = "1"
$env:RAG_SHADOW_BGE_PATH = "D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3"
$env:RAG_SHADOW_RERANKER_PATH = "D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3"
.\.venv\Scripts\python.exe -m pytest tests/test_dense_reranker_shadow.py -q -s
```

执行结果：

```text
1 passed in 179.52s
```

普通完整测试集不加载真实模型，结果保持：

```text
61 passed
1 skipped（真实模型 Shadow，未设置 RUN_MODEL_SHADOW）
```

## 7. 当前限制与后续工作

1. 当前 Dense 验证使用独立内存 Qdrant，不验证生产 collection 一致性。
2. 当前只对 50 个 Gold Chunk 做模型链路验证，不代表真实库 Recall。
3. 当前 Reranker 的 Transformers 5 兼容 shim 需要在后续依赖升级前重新验证。
4. 当前没有将真实全库 Chunk 写入测试 Qdrant，避免执行全量 Embedding。
5. 后续应使用真实 50/100 个 Gold 问题和真实 Chunk，分别测 BM25、Hybrid、Hybrid+Reranker 的增益。
6. 只有 Shadow 指标稳定后，才考虑通过 feature flag 接入旧 Retriever 的旁路比较。

## 8. TASK-011 验收结论

| 验收项 | 结果 |
|---|---|
| BGE-M3 DenseProvider | 已完成 |
| 独立 Qdrant collection | 已完成，内存模式 |
| bge-reranker-v2-m3 Provider | 已完成 |
| BM25-only 对照 | 已完成 |
| Hybrid 对照 | 已完成 |
| Hybrid+Reranker 对照 | 已完成 |
| Recall@1/3/5 | 已完成 |
| MRR | 已完成 |
| Citation 完整率 | 已完成 |
| 未替换 `app/retriever.py` | 是 |
| 未修改 `app/main.py` | 是 |
| 未连接生产 Qdrant | 是 |
| 未执行全量 Embedding | 是 |

**TASK-011：完成。**
