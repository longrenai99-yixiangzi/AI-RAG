# Retrieval Pipeline V1 Shadow 实现说明

> 任务：TASK-010 Retrieval Pipeline V1 Shadow 实现  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 状态：Shadow 实现完成，未接入正式问答链路

## 1. 执行边界

本阶段只实现离线/测试用 Retrieval Pipeline：

- 未修改 `app/main.py`；
- 未替换 `app/retriever.py`；
- 未连接生产 Qdrant；
- 未执行全量 Embedding；
- 未改变现有问答链路。

## 2. 已实现模块

```text
app/retrieval/
├─ query_analyzer.py
├─ hybrid_retriever.py
├─ rrf.py
├─ reranker.py
├─ context_builder.py
└─ citation.py
```

## 3. Shadow 检索流程

```text
用户问题
  -> Query Analysis
  -> BM25 真实检索
  -> DenseProvider Mock
  -> RRF
  -> Context Builder
  -> Citation
```

当前没有 Reranker 实际调用；`DisabledReranker` 作为接口占位，后续可以接入现有 bge-reranker-v2-m3。

## 4. Query Analysis

### 4.1 问题类型

当前支持：

- `POLICY_QUERY`：制度、规定、规范、评审、变更；
- `CASE_QUERY`：案例、经验、复盘；
- `METHOD_QUERY`：如何、方法、步骤、编制、策划；
- `TEMPLATE_QUERY`：模板、任务书、表单、栏目；
- `DISCIPLINE_QUERY`：建筑、结构、机电、BIM、EPC；
- `GENERAL_QUERY`：无法明确识别时的回退类型。

显式意图优先级用于减少冲突：制度/案例优先，多专业词优先专业，模板词优先模板，最后才进入方法或通用类型。分类只影响检索辅助和 Debug，不直接造成硬过滤。

### 4.2 Metadata 候选

识别：

- `board`：设计管理、技术管理、科技管理；
- `knowledge_type`：制度、案例、方法、模板、会议资料、培训资料；
- `discipline`：建筑、结构、机电、BIM、EPC。

候选包含 `value`、`confidence`、`source`。第一阶段只记录候选，不执行 Metadata Filter，避免 Shadow 阶段因为规则误判造成零召回。

## 5. BM25 真实检索

`HybridRetriever` 接收内存中的 `BM25Index` 和 Chunk 列表：

- 使用现有 `app.bm25.tokenize()`；
- 真实执行 `BM25Index.search()`；
- 返回 `chunk_id`、BM25 分数和 rank；
- 通过 `chunk_id` 回查 Chunk；
- 不保存 BM25 文件，不修改正式索引。

## 6. Dense Mock 接口

定义：

```python
class DenseProvider(Protocol):
    def search(self, question: str, limit: int) -> list[tuple[str, float]]: ...
```

测试实现：

```python
MockDenseProvider({question: [(chunk_id, score)]})
```

它只返回预先配置的 Chunk ID，不加载 BGE-M3，不连接 Qdrant。未来真实 Dense Provider 只需实现同一接口即可接入 Shadow 测试。

## 7. RRF

使用独立 `rrf.py`：

```text
RRF(chunk_id) = Σ 1 / (k + rank_i)
```

约定：

- rank 从 1 开始；
- 默认 `k=60`；
- 同一 Chunk ID 合并一次；
- 分数相同按 Chunk ID 稳定排序；
- 返回各来源 rank，便于 Retrieval Debug。

## 8. Context Builder

`context_builder.py` 将最终 Top-K `SearchHit` 转换为：

- `context_text`：发送给 Answer Engine 的证据文本；
- `sources`：实际发送证据的来源字典。

每条证据分配 `[S1]`、`[S2]` 等来源标记，并保留：

- chunk_id；
- document_id；
- file_name；
- source_path；
- heading_path；
- location；
- excerpt。

超过上下文字符上限的候选不会进入 `sources`，因此不会被 Citation 错误引用。

## 9. Citation

`citation.py` 提供：

```python
build_citations(context_bundle)
validate_citations(citations, context_bundle)
```

校验内容：

- Citation 的 source ID 必须存在于 Context；
- source ID 不重复；
- 文件名和来源路径存在；
- location 存在；
- Citation 只能来自实际发送给 Answer Engine 的证据。

当前阶段不生成自然语言答案，只验证可引用证据结构。

## 10. Gold Question 验证

测试读取：

```text
tests/gold_questions/golden_questions.yaml
```

覆盖 50 个问题：

- 10 个制度问题；
- 10 个案例问题；
- 10 个方法问题；
- 10 个模板问题；
- 10 个专业问题。

每个问题验证：

1. Query Analysis 类型；
2. BM25 Top-K 非空；
3. Top-1 命中对应 Gold Chunk；
4. Chunk ID 存在；
5. Context 可生成；
6. Citation 校验通过；
7. 每个 Citation location 完整。

此外，Dense Mock 测试验证 Dense Chunk ID 能进入 RRF 融合结果。

## 11. 测试结果

```text
Retrieval Pipeline Shadow 测试：2 passed
完整项目测试集：61 passed
```

## 12. 与旧 Retrieval 的关系

当前旧链路保持不变：

```text
app/main.py
  -> app.retriever.Retriever
  -> Dense + BM25 + RRF + 可选 Reranker
  -> app.answer.generate_answer
```

新 Shadow 链路不被旧应用导入。后续迁移顺序：

1. 先补 Query Analysis 单元测试和真实 Gold 标注；
2. 再接入独立测试 Dense Provider；
3. 比较新旧 Top-K、Chunk ID、Metadata 和 Citation；
4. 通过 Shadow 后增加 feature flag；
5. 默认仍走旧 Retriever，小范围验证新链路；
6. 只有评价达标后才考虑替换默认实现。

**TASK-010：Retrieval Pipeline V1 Shadow 实现完成。**
