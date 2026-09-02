# Full Corpus Shadow Embedding Report

> 本报告仅记录 Document Pipeline → Chunk/Metadata → BGE-M3 CUDA → 独立 Shadow Qdrant 构建结果。
> 未写入正式 `data\qdrant`，未影响 8000 端口服务，未执行最终 Evaluation。

## 1. 构建摘要

| 指标 | 结果 |
|---|---:|
| 知识库路径 | `D:\设计管理` |
| Shadow Qdrant 路径 | `D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant` |
| Collection | `full_corpus_shadow_bge_m3` |
| 文件数量 | 498 |
| Document 数量 | 498 |
| Chunk 数量 | 4747 |
| Embedding 数量 | 4747 |
| Embedding 失败数量 | 0 |
| 异常文件数量 | 3 |
| 扫描/流水线错误数量 | 0 |

## 2. CUDA 与耗时

- CUDA 可用：`True`
- GPU：`NVIDIA GeForce RTX 4060 Laptop GPU`
- Torch：`2.12.1+cu132`，CUDA Runtime：`13.2`
- Embedding 阶段耗时：`176.303` 秒
- 全流程耗时：`259.815` 秒
- GPU 峰值 allocated：`1532433920` bytes
- GPU 峰值 reserved：`2933915648` bytes

## 3. 模型与索引

- BGE-M3 路径：`D:\AI智能体\AI设计管理RAG-V1\models\bge-m3`
- Qdrant 向量维度：`1024`
- Qdrant Collection：`full_corpus_shadow_bge_m3`
- 写入向量数：`4747`
- Payload 包含：chunk_id、document_id、source_path、file_name、heading_path、location、text 和 Metadata。

## 4. Document Pipeline 统计

- Metadata 完整 Chunk：`4747`
- location 有效 Chunk：`4747`
- 状态分布：`{"parsed": 495, "needs_ocr": 2, "front_matter_error": 1}`
- 文件类型分布：`{".md": 423, ".pptx": 37, ".xlsx": 10, ".pdf": 16, ".docx": 12}`

## 5. 异常文件

| 文件 | 状态 | Chunk | 错误 |
|---|---|---:|---|
| `D:\设计管理\raw\设计管理体系\培训与能力建设\设计能力提升培训5.9\培训工作满意度调查表.pdf` | needs_ocr | 1 |  |
| `D:\设计管理\raw\设计管理体系\培训与能力建设\设计能力提升培训7.31\培训工作满意度调查表.pdf` | needs_ocr | 2 |  |
| `D:\设计管理\templates\entity.md` | front_matter_error | 0 | YAML front matter error: while constructing a mapping
  in "<unicode string>", line 2, column 10:
    created: {{date}}
             ^
found unhashable key
  in "<unicode string>", line 2, column 11:
    created: {{date}}
              ^ |

## 6. Embedding 失败 Chunk

| Chunk | 文件 | 错误 |
|---|---|---|
| 无 | - | - |

## 7. 边界与后续

1. 本索引仅供 Shadow Retrieval 使用，未替换旧 Retriever。
2. 本任务只完成全库 Embedding 与 Shadow Qdrant 构建；最终 Evaluation 按任务要求未执行。
3. 正式切换前仍需单独完成 Shadow Retrieval Evaluation、Metadata Filter 验证和发布审批。
