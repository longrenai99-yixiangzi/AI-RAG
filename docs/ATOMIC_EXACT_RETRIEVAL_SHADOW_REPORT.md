# 带项目、年份、指标和字段约束的 Shadow 精确检索

## 1. 结论

已在 Shadow/Trial 范围完成第一版精确证据检索。它解决的是“从文件中的具体行、段落、表格行找证据”，不是把候选证据直接当成答案。

当前没有接入正式 Retriever、正式 Qdrant 或正式 8000 服务；没有调用 LLM，也没有新增依赖。

## 2. 当前实现

实现文件：

- `app/ingestion/atomic_evidence.py`
- `app/ingestion/atomic_search.py`
- `app/trial/main.py`（仅 Trial 的 Shadow 证据回退）

原子证据粒度：

- Markdown：非空行，保留标题路径和行号；
- PDF：页内文本行，保留页号和页内行号；
- DOCX：段落或表格行；
- PPTX：幻灯片文本行；
- XLSX：工作表有效行，保留表头、单元格值、Sheet 和行号。

查询会动态提取四类约束：

1. 年份：识别 `20xx`，对匹配年份加分，对缺失年份软扣分；
2. 项目实体：从“XX项目/中心/医院/馆/园/厂房/学校”等语言结构识别，年份不会并入项目名；
3. 指标：工期、金额、效益、创效、利润、比选、责任状、示范项目等；
4. 字段：总工期、设计工期、创效金额、上传数量、专业、利润等。

排序采用软约束：

- 原子正文词项的 IDF 权重；
- 查询短语只在正文中精确匹配；
- 文件名、标题路径、来源路径匹配；
- 年份、正文指标、字段、项目实体分别加权；
- 缺少年份/指标/字段只降低分数，不直接删除候选；
- 登记页、Wiki 链接和标题行降权，不能冒充真实正文。

因此，检索链是：

`Query Facets → 原子证据候选 → 软约束排序 → 精确 location → Evidence`

不是：

`命中标题 → 直接生成答案`

## 3. 回放结果

数据：`D:\AI智能体\AI设计管理RAG-V1\data\shadow\atomic_evidence\records.jsonl`

| 指标 | 结果 |
|---|---:|
| 支持文件数 | 498 |
| 原子证据数 | 29,027 |
| 有完整 location 的证据 | 29,027 |
| 真实业务问题 | 10 |
| 原子层存在精确定位的问题 | 10 |
| 既有基线存在精确定位的问题 | 5 |
| Gold Scope 已确认的问题 | 0 |

当前 `expected_files` 尚未补齐，10 道题均为 `GOLD_UNCONFIRMED`。因此本阶段只报告定位能力，不报告 Recall、准确率或业务回答正确率。

详细逐题结果：

- `evaluation/atomic_evidence/real_business_queries.jsonl`
- `evaluation/atomic_evidence/retrieval_ab.jsonl`
- `docs/KNOWLEDGE_ATOMIC_QUERY_REPLAY_REPORT.md`
- `docs/ATOMIC_RETRIEVAL_AB_REPORT.md`

## 4. 重要边界

`D:\设计管理` 当前是 Root-001 原子证据范围。Root-002 已批准的外部文件仍由 Trial 的受控读取和专用确定性回退处理，尚未混入 Root-001 原子 JSONL。

这意味着：

- 对普通文本问题，Provider 未开放时，系统可以返回匹配正文证据，但不会擅自生成确定结论；
- 对已经确认字段的日期、工期、排水方案等问题，Trial 可以走已有确定性回答；
- 对跨多行、分组、合计、利润筛选等问题，仍必须走结构化 Fact Path，不能用普通文本检索代替计算。

## 5. GitHub 方案对本项目的实际借鉴

- LightRAG 的段落语义切分强调标题、段落和表格行边界，并保留父级标题上下文；这对应本项目的 heading path、表格行和原子定位设计：
  [LightRAG Paragraph Semantic Chunking](https://github.com/HKUDS/LightRAG/blob/main/docs/ParagraphSemanticChunking.md)
- agentic-rag 将结构化数据与可搜索文本分开，并采用过召回、元数据约束和可解释引用；这对应本项目把 XLSX 行作为结构化证据，而不是把整张表压成一段文本：
  [Rohianon agentic-rag](https://github.com/Rohianon/agentic-rag)
- agentic-rag-verified-citations 强调逐条检查引用、表格行级引用和冲突处理；这对应本项目每条原子记录保留 evidence id 与行/段/页位置：
  [agentic-rag-verified-citations](https://github.com/deepeshgupta12/agentic-rag-verified-citations)
- regulated-rag 把生成前证据门禁、生成后引用校验和 typed refusal 分开；这对应本项目 Provider 不可用时返回可核查 Evidence，而不是编造答案：
  [regulated-rag](https://github.com/RZ-Logic/regulated-rag)

## 6. 下一步

1. 为真实业务问题补齐 `expected_files`、目标行/段/Sheet 等 Gold 定位，才能计算真正的 Recall；
2. 将 Root-002 通过审批的文件以同样的原子结构加入独立 Shadow Root-002，保留 root 边界；
3. 对“多少条、按专业统计、合计金额、利润大于 0”等问题，沿用 Fact Query 路径；
4. Shadow A/B 通过后，再讨论是否接入正式 Retriever。
