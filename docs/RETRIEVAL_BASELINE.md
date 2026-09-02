# Retrieval 基准准备报告

> 任务：TASK-008.5 迁移稳定性修复与 Retrieval 基准准备  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 抽样日期：2026-08-22

## 1. 执行边界

本次完成 Markdown Chunk 稳定化和 Gold Question 基准准备：

- 未替换 `app/indexer.py`；
- 未写正式 Qdrant；
- 未执行全量 Embedding；
- 未修改 `D:\设计管理`；
- Retrieval 对照只使用内存 BM25，不代表最终 Dense + RRF + Reranker 结果。

## 2. Markdown Shadow 修复结果

新增：

```text
app/ingestion/normalization/markdown_normalizer.py
```

统一内容：

- BOM；
- CRLF/CR 换行；
- 行尾空白；
- 章节内部空行保留；
- Chunk ID 计算前的文本边界。

五格式 Shadow fixture 重新验证：

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| Markdown 稳定 Chunk ID | 0/2 | 2/2 |
| 五格式稳定 Chunk ID | 3/7 | 5/7 |
| 五格式 Chunk ID 稳定率 | 42.86% | 71.43% |

剩余不稳定主要来自 XLSX 新旧切分粒度差异：新 Loader 按有效 Sheet 聚合，旧 Parser 按数据行切分。该差异保留到后续 Gold 检索验证，不在本任务强行改变 XLSX 设计。

## 3. Gold Question 测试集

新增：

```text
tests/gold_questions/golden_questions.yaml
```

共 10 个问题，覆盖：

| 类别 | 数量 |
|---|---:|
| 制度查询 `POLICY_QUERY` | 3 |
| 案例查询 `CASE_QUERY` | 2 |
| 方法查询 `METHOD_QUERY` | 2 |
| 模板查询 `TEMPLATE_QUERY` | 1 |
| 专业查询 `DISCIPLINE_QUERY` | 2 |

每个问题包含：

- `question`；
- `category`；
- `expected_keywords`；
- `expected_metadata`；
- `expected_files`（当前留空，待人工核验后补充）。

## 4. 旧系统与新 Pipeline 对照口径

当前 V1 环境没有可直接调用的旧 LLM 答案链路；因此本报告不伪造“旧系统答案”。旧侧记录为：

```text
旧 Parser + 旧 chunker + 内存 BM25 Top-1 证据
```

新侧记录为：

```text
新 Loader + 新 Pipeline Chunk + Metadata + 内存 BM25 Top-1 证据
```

两侧均未调用 Dense Embedding、Qdrant 或 Reranker。下面结果是 Retriever 正式实现前的词法检索基线，不是最终答案质量结论。

## 5. 同一批真实样本对照

抽样方法与 Metadata 规则优化保持一致：候选 498 个支持文件，随机种子 `20260822`，抽取 50 个真实文件。

| 指标 | 旧 Parser 投影 | 新 Pipeline |
|---|---:|---:|
| 文档数 | 50 | 50 |
| Chunk 数 | 428 | 332 |
| Gold 问题数 | 10 | 10 |
| 检索方式 | BM25-only | BM25-only |
| Qdrant/Embedding | 未使用 | 未使用 |

## 6. Gold Questions 检索记录

以下“旧系统答案”列按诚实边界记录为旧侧 BM25 证据，不冒充旧 LLM 生成答案；“新 Pipeline 检索结果”同样只记录 Top-1 证据。

| ID / 类别 | 问题 | 旧系统 BM25 Top-1 证据 | 新 Pipeline BM25 Top-1 证据 |
|---|---|---|---|
| GQ-001 制度 | 设计管理制度中，项目启动阶段如何开展设计策划并形成任务书？ | `天津华苑教育园项目（北京）.md`；第 3 页/段；行 34 | 同文件；第 3 页/段；行 34–38 |
| GQ-002 制度 | 设计变更和设计评审应如何形成闭环管理？ | `设计招采.md`；核心要点；行 12 | 同文件；核心要点；行 12–17 |
| GQ-003 制度 | EPC项目设计管理制度对设计接口、评审和交付有哪些要求？ | `荆州职业技术学院（华中）.md`；核心设计管理经验/第 12 页段；行 194 | 同文件；经验启示/复盘要点；行 194–201 |
| GQ-004 案例 | 从医院项目经验总结中，可以提炼出哪些设计管理问题和改进经验？ | `龙泉社区三期（华中）.md`；核心设计管理经验/第 12 页段；行 83 | 同文件；同章节；行 83–85 |
| GQ-005 案例 | 方案比选案例通常如何组织多方案评价，并形成最终决策依据？ | `公司医疗产品线设计创效案例汇编模板（案例示例） - 成果.pptx`；项目名称/西南某医院项目；幻灯片 37 | `产品线设计方案比选典型案例汇编（医疗）.md`；无标题段；行 1 |
| GQ-006 方法 | 施工图设计任务书应如何编制，至少需要明确哪些内容？ | `青岛河套项目.md`；设计管理工作中涉及的方面；行 12 | 同文件；同章节；行 12–15 |
| GQ-007 方法 | EPC项目设计策划如何按阶段拆解关键动作和交付成果？ | `荆州职业技术学院（华中）.md`；核心设计管理经验/第 12 页段；行 81 | 同文件；经验启示/复盘要点；行 194–201 |
| GQ-008 模板 | 设计管理任务书或管理模板应包含哪些栏目，如何保证后续可检查？ | `天津华苑教育园项目（北京）.md`；核心设计管理经验/第 25 页段；行 179 | 同文件；同章节；行 179–183 |
| GQ-009 专业 | 建筑专业从方案设计到施工图设计阶段，重点设计管理接口有哪些？ | `天津华苑教育园项目（北京）.md`；核心设计管理经验/第 25 页段；行 179 | 同文件；同章节；行 179–183 |
| GQ-010 专业 | 机电和结构专业在EPC项目中如何开展协同、审查和问题闭环？ | `天津华苑教育园项目（北京）.md`；核心设计管理经验/第 25 页段；行 179 | 同文件；同章节；行 179–183 |

## 7. 初步观察

1. Markdown 规范化后，新结果保留了更完整的 `line_end`，Citation 定位比旧侧更完整。
2. 多数问题在 50 文件小样本中能命中设计管理经验类材料，但制度/模板/专业问题存在案例材料占位，说明仅靠 BM25 不能替代 Metadata Filter、RRF 和 Reranker。
3. GQ-005 的新旧 Top-1 文件不同，属于后续 Retriever 重点对照样本。
4. GQ-007 新旧命中了同一文件的不同章节，后续需要评估章节定位和问题关键词覆盖。
5. GQ-009/GQ-010 命中同一经验段，说明专业条件尚未进入检索过滤；后续需结合 `discipline` 和 Query Analysis。

## 8. 后续 Retriever 基准使用方式

后续 TASK-006 之后的 Retriever 评测应：

1. 读取本 Gold Question YAML；
2. 分别运行旧基线和新 Retriever；
3. 记录 Top-1/Top-3/Top-5 文件与 Chunk；
4. 计算 Recall@5、MRR、Metadata Filter 影响和 Reranker 前后变化；
5. 对 expected_files 进行人工确认后再计算文件命中率；
6. 将“旧系统答案”与“新系统答案”分开记录，并保留 Citation 证据。

## 9. 测试结果

```text
Gold Question 结构测试：1 passed
Markdown Normalizer 测试：3 passed
Shadow 测试：2 passed
完整项目测试集：59 passed
```

## 10. TASK-008.5 验收结论

| 验收项 | 结果 |
|---|---|
| Markdown 规范化模块 | 已完成 |
| BOM/换行/空白统一 | 已完成 |
| Markdown Shadow 重新验证 | 已完成，稳定率 42.86%→71.43% |
| Gold Question 测试集 | 已完成，10 题 |
| 制度/案例/方法/模板/专业覆盖 | 已完成 |
| 旧侧基线记录 | 已完成，明确为旧 Parser+BM25 证据 |
| 新 Pipeline 检索记录 | 已完成，明确为 BM25-only 基线 |
| 未替换 `app/indexer.py` | 是 |
| 未写正式 Qdrant | 是 |
| 未执行全量 Embedding | 是 |

**TASK-008.5：完成。**
