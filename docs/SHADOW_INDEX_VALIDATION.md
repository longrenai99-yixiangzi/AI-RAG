# Shadow Index Pipeline 实现验证报告

> 任务：TASK-008 Shadow Index Pipeline 实现验证  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 状态：Shadow 验证完成，未替换正式 indexer

## 1. 执行边界

本次验证不改变正式运行链路：

- 不替换 `app/indexer.py`；
- 不写正式 Qdrant；
- 不删除旧索引；
- 不生成全量 Embedding；
- 不修改 `D:\设计管理`。

新 Shadow 代码只进行内存读取、解析、Chunk/Metadata 比较和 AdapterPlan 生成。

## 2. 新增模块

```text
app/ingestion/shadow/
├─ README.md
├─ shadow_runner.py
├─ comparison.py
└─ report.py
```

### 2.1 Shadow Runner

`shadow_runner.py::run_shadow_pipeline()` 对同一批文件执行两条只读路径：

```text
同一批文件
  ├─ 新 Pipeline
  │   -> 新 Loader
  │   -> SourceBlock
  │   -> Chunk
  │   -> Metadata
  │   -> Staging JSON
  │   -> IndexAdapterPlan
  │
  └─ 旧 Parser 投影
      -> app.parsers.parse_file
      -> app.chunker.chunk_blocks
```

这里的“旧 Parser 投影”没有调用 `app/indexer.py`，只复用旧 Parser 和纯切片函数生成可比较结果。

### 2.2 Comparison

`comparison.py` 比较：

- 新旧文档数量；
- 新旧 Chunk 数量；
- 稳定 `chunk_id` 数量和比例；
- 文件级 source_path 一致性；
- 稳定 Chunk ID 范围内的 source_path 一致性；
- 新旧 location 完整性；
- 新 Metadata 完整性和覆盖率；
- 新旧异常文件数量；
- Qdrant payload、BM25 record 和 Chunk 数量。

### 2.3 Report

`report.py` 将比较结果渲染为 Markdown，不负责写文件；发布报告由任务执行层显式保存。

## 3. 五类 Fixture Shadow 验证

### 3.1 输入

使用测试 fixture 中同名正常文件：

- Markdown；
- PPTX；
- PDF；
- DOCX；
- XLSX。

新旧两条路径使用完全相同的 5 个文件路径。新路径先生成内存 Staging JSON，再由 Reader 读取并生成 AdapterPlan；旧路径不接触 Staging 写入或正式索引。

### 3.2 汇总结果

| 指标 | 新 Pipeline | 旧 Parser 投影 |
|---|---:|---:|
| 文档数量 | 5 | 5 |
| Chunk 数量 | 6 | 7 |
| location 完整数量 | 6/6 | 7/7 |
| 异常文件数量 | 0 | 0 |
| Metadata 完整数量 | 6/6 | 不提供正式 Metadata |
| Qdrant Adapter payload | 6 | 未生成 |
| BM25 Adapter record | 6 | 未生成 |

### 3.3 稳定性结果

| 指标 | 结果 |
|---|---:|
| 稳定 chunk_id | 5/7 |
| chunk_id 稳定率 | 71.43% |
| 文件级 source_path 匹配 | 5/5 |
| 文件级 source_path 匹配率 | 100% |
| 稳定 Chunk ID 范围内 source_path 匹配率 | 100% |

### 3.4 按文件类型

| 类型 | 新 Chunk | 旧 Chunk | 稳定 ID | 说明 |
|---|---:|---:|---:|---|
| Markdown | 2 | 2 | 2 | 规范化后保留章节内部换行，Chunk ID 稳定 |
| PPTX | 1 | 1 | 1 | 文本、页级定位和切片结果一致 |
| PDF | 1 | 1 | 1 | 文字页结果一致 |
| DOCX | 1 | 1 | 1 | 章节文本结果一致 |
| XLSX | 1 | 2 | 0 | 新 Loader 按 Sheet 聚合，旧 Parser 按数据行输出 |

## 4. 差异解释

### 4.1 Markdown 差异

TASK-008.5 新增 Markdown Normalizer，统一 BOM、CRLF/CR、行尾空白，并保留章节内部空行。重新执行 Shadow 后，Markdown 由 0/2 提升为 2/2 稳定 Chunk ID；五格式 fixture 总稳定率由 42.86% 提升到 71.43%。

后续仍需冻结规范化版本，并在规则变更时使用 `chunk_version` 或受控重建，不能无报告地混用不同文本规范。

### 4.2 XLSX 差异

新 XLSX Loader 的设计是“每个有效 Sheet 一个 SourceBlock”，再由 Chunk Strategy 按 Sheet/行窗口切分；旧 Parser 是“每个数据行一个 SourceBlock”。

这不是 source_path 丢失，而是粒度设计变化：

- 新路径保留 Sheet、表头、行范围和列数；
- 旧路径按行生成更多 Chunk；
- 正式切换前需要用检索 Gold 问题确认 Sheet 聚合是否优于旧行粒度；
- 不应只用 Chunk 数相等作为通过条件。

## 5. Metadata 与 AdapterPlan 验证

新路径每个 Chunk 都通过 Metadata Schema 校验：

```text
Metadata 完整率：6/6 = 100%
```

每个有效 Staging Chunk 都生成：

- 一个 Qdrant payload 计划；
- 一个 BM25 record 计划；
- 同一个 `chunk_id` 作为关联键。

本次只生成内存计划，没有创建 QdrantClient、没有调用 upsert、没有写 BM25 文件。

## 6. 异常文件验证

Shadow 测试另用损坏 PDF 验证新旧两条路径的异常统计：

| 指标 | 新 Pipeline | 旧 Parser 投影 |
|---|---:|---:|
| 异常文件数 | 1 | 1 |
| Chunk 数 | 0 | 0 |
| 正式发布计划 | 不生成 | 不生成 |

异常文件不得因为新旧状态不同而被静默发布；任何 `read_error`、编码错误或质量失败都应进入待处理报告。

## 7. 迁移门槛

当前 Shadow 结果不能直接授权替换旧 indexer，原因是：

1. XLSX Chunk 粒度与旧 Parser 不同，需要 Gold 问题验证检索效果。
2. Markdown 规范化已提高稳定率，但规范版本仍需冻结。
3. discipline/Metadata 需要继续人工标注和治理，不能仅靠结构数量判断。

建议正式切换前满足：

- 文件级 source_path 匹配 100%；
- 解析状态差异全部有解释；
- Chunk 粒度差异有明确迁移决策；
- Citation location 对比通过；
- Metadata Schema 校验 100%；
- Gold 问题的召回和引用不低于旧基线；
- staging、发布、备份和回滚演练通过。

## 8. 测试结果

Shadow 测试：

```text
tests/test_shadow.py：2 passed
```

完整测试集：

```text
59 passed
```

## 9. TASK-008 验收结论

| 验收项 | 结果 |
|---|---|
| 新 Pipeline 生成 Chunk | 已完成 |
| 新 Pipeline 生成 Metadata | 已完成 |
| 新 Pipeline 生成 IndexAdapterPlan | 已完成 |
| 与旧 Parser 投影比较 | 已完成 |
| 文档数量比较 | 已完成 |
| Chunk 数量比较 | 已完成 |
| chunk_id 稳定性比较 | 已完成 |
| source_path 一致性比较 | 已完成 |
| location 完整性比较 | 已完成 |
| Metadata 覆盖率比较 | 已完成 |
| 异常文件数量比较 | 已完成 |
| 未替换 `app/indexer.py` | 是 |
| 未写正式 Qdrant | 是 |
| 未删除旧索引 | 是 |
| 未生成全量 Embedding | 是 |

**TASK-008：完成。**
