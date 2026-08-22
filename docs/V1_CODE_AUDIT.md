# AI设计管理知识库 V1.0 项目审计报告

> 审计任务：TASK-001 当前系统审计  
> 审计对象：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（按项目约定只读）  
> 审计日期：2026-08-22  
> 执行边界：本报告仅基于代码、配置、测试、README 和已有运行报告进行静态审计；未修改源码，未安装依赖，未改变 Python/CUDA 环境，未启动服务，未执行索引构建。

## 1. 审计依据与路径说明

本审计只使用项目中实际找到并完整读取的两份 V1 文档：

1. `docs/AI设计管理知识库_V1.0_Codex执行手册_真实路径完整版.md`
2. `docs/AI设计管理知识库_V1.0_Codex任务拆解清单_Task_List版.md`

用户给出的文件路径使用了目录分隔形式，而项目实际文件名使用下划线：

- 用户描述的 `docs\AI设计管理知识库 V1.0 Codex执行手册\_真实路径完整版.md`，实际对应第一份文件。
- 用户描述的 `docs\AI设计管理知识库\_V1.0\_Codex任务拆解清单\_Task\_List版.md`，实际对应第二份文件。

两份执行依据现已统一使用同一个正式代码目录：`D:\AI智能体\AI设计管理RAG-V1`。本报告及后续 V1 文档均以该目录为唯一代码目录，避免副本分叉。

## 2. 总体结论

当前系统是一个可以作为 V1 重构基础的本地 V0.1 RAG 闭环，不是已经具备 V1 架构的系统。

已经存在并且值得保留的主链路是：

```text
D:\设计管理（扫描且不写回）
  -> 多格式解析
  -> SourceBlock
  -> Chunk
  -> BGE-M3 向量
  -> Qdrant Local
  -> BM25
  -> RRF
  -> 可选 Reranker
  -> LLM 生成
  -> [S1] 引用校验
```

当前最重要的 V1 缺口不是模型缺失，而是治理与边界缺失：

1. 文档解析、质量检测、索引构建尚未分层；没有独立 Worker。
2. Metadata、entities、facts 尚未建模，无法按板块、知识类型、专业等治理和过滤。
3. Retriever 没有 Query Analysis、Metadata Filter、完整检索 Debug 和证据阶段。
4. Answer 没有 FACT/POLICY/CASE/METHOD/GENERAL 路由，事实问题仍会进入统一 LLM 流程。
5. Citation 已有基础实现，但尚未形成统一的 Citation/Evidence 模块，也未覆盖 V1 要求的结构化标题等字段。
6. 质量检测不完整，Markdown 使用 `errors="replace"`，这与 V1 手册“禁止 errors="replace"、发现乱码标记失败”直接冲突。
7. 只有全量重建，没有文档状态检测、增量准备和删除检测。
8. 测试规模和类型不足，没有 50 个 Gold 问题及自动评测。
9. 当前项目目录没有 `.git`，Task List 要求的每个 Task Git 提交在当前副本中尚未具备执行条件。

因此，建议将本报告作为 TASK-002 至 TASK-017 的基线，不在 TASK-001 阶段直接实施上述改造。

## 3. 当前项目结构

静态文件清单显示当前目录主要结构如下：

```text
AI设计管理RAG-V1/
├─ app/
│  ├─ answer.py          答案生成、上下文组装、引用校验
│  ├─ bm25.py            BM25 索引
│  ├─ chunker.py         文本切片
│  ├─ config.py          环境变量和运行设置
│  ├─ database.py        SQLite documents/chunks
│  ├─ domain.py          文档、块、切片、检索命中对象
│  ├─ embeddings.py      BGE-M3 和 Reranker 加载/推理
│  ├─ indexer.py         全量索引、staging、发布和回滚
│  ├─ llm.py             OpenAI 兼容 chat/completions 客户端
│  ├─ main.py            FastAPI 应用和 HTTP API
│  ├─ parsers.py         多格式解析和文件扫描
│  ├─ retriever.py       Dense/BM25/RRF/Reranker 检索链
│  ├─ vector_store.py    Qdrant Local 封装
│  └─ static/            当前问答页面
├─ scripts/
│  ├─ doctor.py          依赖、Python、CUDA 和路径体检
│  └─ index_vault.py     全量/预检索引命令
├─ tests/
│  ├─ test_core.py       切片、RRF、引用校验测试
│  └─ test_indexer.py    staging 索引发布测试
├─ data/
│  ├─ cache/             运行时缓存目录
│  ├─ indexes/           BM25 等索引目录
│  ├─ qdrant/            Qdrant Local 目录
│  └─ reports/           JSON 索引报告
├─ docs/                 两份 V1 执行依据及本报告
├─ requirements.txt
├─ README.md             当前仍标注为 V0.1
├─ .env.example
└─ .gitignore
```

当前不存在 V1 手册规划的以下目录或文件：

- `worker/`
- `app/api/`
- `app/core/retrieval/`
- `app/core/answer/`
- `app/core/citation/`
- `app/ingestion/`
- `app/storage/`
- `scripts/start.ps1`
- `scripts/stop.ps1`
- `scripts/check.ps1`
- `models/`

项目根目录存在 `.venv`、`__pycache__` 和 `.pytest_cache` 等运行/缓存目录，但当前目录不是 Git 工作树：执行只读 `git status` 和 `git log` 均返回“not a git repository”。这不是源码缺陷，但会影响后续 Task 的副本管理和提交验收。

## 4. 启动入口与运行方式

### 4.1 当前 Server 入口

`app/main.py`：

- 在模块末尾创建 `app = create_app()`。
- `create_app()` 创建 FastAPI 应用，版本仍为 `0.1.0`。
- 挂载 `/static`，根路径 `/` 返回 `app/static/index.html`。
- lifespan 中初始化 `Settings`、SQLite、Qdrant Local、BM25、Embedding、Reranker、LLM 和 Retriever。
- 启动时会尝试加载 BGE-M3；失败时服务仍可创建，但向量检索不可用。
- Reranker 是按查询延迟加载的可选组件。

README 给出的实际启动命令是：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4.2 当前索引入口

`scripts/index_vault.py` 调用 `app.indexer.index_vault()`，支持：

- `--limit`：限制排序后的前 N 个文件。
- `--preflight`：只解析并统计，不下载模型、不发布索引。
- 默认行为：扫描、解析、切片、生成向量、写入 staging，再发布为活动索引。

README 明确要求索引时关闭 Web 服务，因为 Qdrant Local 目录不能被两个进程同时打开。当前索引过程和问答过程属于同一代码目录下的两个手工启动流程，没有 Worker/Server 隔离。

### 4.3 当前一键启动能力

当前没有 V1 要求的 `start.ps1`、`stop.ps1`、`check.ps1`。因此：

- Server 可以手动启动；
- Worker 尚不存在；
- Server 与索引构建不是并行安全架构；
- 普通用户还不能通过 V1 规定的一键脚本同时启动 Server 和 Worker。

## 5. API 入口

当前 `app/main.py` 暴露的 HTTP API 如下：

| 方法 | 路径 | 当前行为 | V1 相关评价 |
|---|---|---|---|
| GET | `/` | 返回静态问答页面 | 可保留为 Server UI 入口 |
| GET | `/api/status` | 返回知识源路径、API 配置状态、Embedding 状态、Reranker 状态、documents/chunks 数量 | 可作为状态 API 基础，但缺少 OCR、文件类型、Worker、Metadata 等统计 |
| GET | `/api/health` | 检查 LLM、Embedding、Qdrant、知识源目录 | 有用，但当前健康状态依赖 LLM，未区分 Server 与 Worker |
| POST | `/api/chat` | 接收 `question`，执行检索和统一答案生成 | 可保留兼容入口，但内部应接入 Answer Router 和 Retrieval Debug |

`POST /api/chat` 的请求模型只包含一个长度为 2 至 2000 的 `question` 字段，没有问题类型、过滤条件、调试模式或追问上下文参数。

## 6. 配置与模型加载

### 6.1 配置来源

`app/config.py` 的 `Settings.load()`：

- 优先读取当前进程环境变量；
- Windows 下若当前进程没有值，再读取用户环境变量注册表；
- 默认知识源是 `D:\设计管理`；
- 运行数据写入项目 `data/`；
- 没有看到 `.env` 加载实现，`.env.example` 只是示例文件；
- BGE-M3 和 Reranker 名称在代码中固定为 `BAAI/bge-m3`、`BAAI/bge-reranker-v2-m3`。

主要配置项：

| 配置 | 用途 | 当前状态 |
|---|---|---|
| `RAG_VAULT_PATH` | 知识源目录 | 默认 `D:\设计管理` |
| `RAG_API_BASE_URL` | OpenAI 兼容接口地址 | 必须由用户环境提供 |
| `RAG_CHAT_MODEL` | 生成模型名 | 必须由用户环境提供 |
| `RAG_API_KEY` | 生成接口密钥 | 必须由用户环境提供 |
| `RAG_ENABLE_RERANKER` | Reranker 自动/开关 | 默认 `auto` |
| `RAG_MAX_LOCAL_CHUNKS` | Qdrant Local 切片上限 | 默认 18000 |
| `RAG_MAX_FILE_SIZE_MB` | 单文件大小上限 | 默认 150 MiB |

### 6.2 Embedding

`app/embeddings.py` 的 `EmbeddingService`：

- 使用 `FlagEmbedding.BGEM3FlagModel`；
- 尝试检测 CUDA，CUDA 可用时使用 `cuda` 和 FP16，否则使用 CPU；
- 固定 `batch_size=4`、`max_length=1024`；
- 仅请求 dense vectors；BGE-M3 的 sparse/ColBERT 返回值被关闭；
- 向量库尺寸在 `app/vector_store.py` 中固定为 1024；
- 模型加载或向量化失败会抛出 `ModelUnavailable`。

BGE-M3 是 V1 手册要求保留的核心能力，当前实现可以作为基础保留。后续应将模型生命周期和 Worker 的批处理策略解耦，避免 Server 启动时同步加载重模型。

### 6.3 Reranker

`RerankerService`：

- 使用 `FlagEmbedding.FlagReranker`；
- 默认按查询第一次使用时加载；
- `off/false/0/no` 时禁用；
- `on` 模式加载或推理失败会抛出异常；
- `auto` 模式失败后退回 RRF 排序。

这一退化策略值得保留，但后续必须把是否使用 Reranker、失败原因、重排前后候选顺序写入 Retrieval Debug。

### 6.4 LLM

`app/llm.py` 调用 OpenAI 兼容的 `/chat/completions`：

- 最多重试 3 次；
- 连接超时 15 秒，总超时 60 秒；
- 失败时抛出 `LLMError`；
- `health_check()` 会发出“只回复 OK”的探测请求。

当前 LLM 是所有问题的统一生成后端，没有 V1 要求的事实直查和按问题类型分流。API Key 不会在报告和 doctor 输出中打印，这一点应保留。

## 7. Parser 与 Document Engine 审计

### 7.1 文件扫描

`app/parsers.py::iter_source_files()`：

- 支持 `.md`、`.pdf`、`.docx`、`.xlsx`、`.pptx`；
- 排除若干工具目录、`.git`、`.trash` 等目录；
- 跳过 `~$` 临时 Office 文件、`.tmp/.bak/.part`、符号链接和 Windows 重解析点；
- 通过 `stat` 获取文件大小和时间；
- 使用 SHA-256 生成文件指纹；
- 文档 ID 由规范化路径生成 UUID5。

文件扫描、解析、质量检测、切片、Metadata、索引目前集中在少数平面模块中，没有 V1 手册要求的 Loader → Parser → Quality Check → Chunk → Metadata → Index 分层。

### 7.2 Markdown

`_parse_markdown()`：

- 使用 UTF-8 读取；
- 去除最外层 YAML front matter；
- 按 Markdown 标题生成 heading path；
- 按章节形成 SourceBlock，记录起始行号。

关键问题：当前使用 `read_text(encoding="utf-8", errors="replace")`。这会把编码错误替换成替代字符并继续进入索引，无法满足 V1 执行手册的明确要求：禁止 `errors="replace"`，发现乱码必须标记失败。后续应改成可检测、可追踪的失败状态，而不是静默修复。

### 7.3 PDF

`_parse_pdf()` 使用 PyMuPDF 逐页读取文字：

- 每个有文字的页面生成一个 SourceBlock；
- location 记录 `page`；
- 没有提取出任何文字时返回 `needs_ocr`。

已具备扫描 PDF 的初步识别能力，但：

- 没有有效文字比例阈值；
- 没有 OCR Provider 接口；
- 没有 OCR 任务状态、重试、失败原因和待处理队列；
- “无文字页面”与“解析失败”没有细分。

### 7.4 DOCX

`_parse_docx()` 使用 `python-docx`：

- 读取段落；
- 识别 Heading/标题样式；
- 记录段落起点和标题路径；
- 将表格转换为按行拼接的文本，并记录表号。

可以保留为 DOCX 基础解析器，但目前没有独立 Loader、解析质量检查、页码/章节更精细的定位和乱码检测。

### 7.5 XLSX

`_parse_xlsx()` 使用 `openpyxl` 的只读、`data_only=True` 模式：

- 每个工作表第一个非空行作为表头；
- 后续非空行生成 SourceBlock；
- location 记录 Sheet、行号、表头行号。

可保留为基础实现。需要注意当前实现只保留计算后的值，不保存公式、单元格地址、合并单元格语义或隐藏行列信息；这些属于后续数据质量和引用精度风险。

### 7.6 PPTX

`_parse_pptx()` 使用 `python-pptx`：

- 提取文本框；
- 提取表格行；
- 尝试提取讲者备注；
- 每页生成 SourceBlock，location 记录 slide。

可保留为基础实现，但标题目前取页面第一段文本，不是可靠的标题识别。V1 Citation 要求显示 PPT 页号，当前已有 slide 位置基础。

### 7.7 解析状态与异常隔离

`parse_file()` 记录：

- 文件大小、修改时间、SHA-256；
- `parsed`、`needs_ocr`、`parse_error`、`skipped_large_file`、`unsupported` 等状态；
- 单个文件异常会被捕获并写入文档错误字段，不会直接终止全量解析。

但当前状态集合不是 Task List 要求的 `PENDING/PARSING/SUCCESS/FAILED/NEED_OCR`，也没有质量检测结果、乱码检测结果、OCR 状态或状态迁移记录。TASK-004/TASK-005 必须在保留当前异常隔离能力的基础上重构。

## 8. Chunk 与索引流程

### 8.1 Chunk

`app/chunker.py`：

- 使用本地估算 token 数，避免切片阶段额外下载 tokenizer；
- 优先按段落和句号、分号等边界切分；
- 默认目标 450 token、最大 800 token、重叠 80 token；
- 对超长单元递归拆分；
- Chunk ID 使用文档 ID、块序号、分片序号、标题和文本前缀生成 UUID5；
- 保留 heading path 和 location。

切片逻辑和重叠策略可以保留。V1 改造时应让 Chunk 带上文档 Metadata，并明确 chunk 版本，避免切片规则变化后无法判断旧索引是否需要重建。

### 8.2 全量 staging 索引

`app/indexer.py::index_vault()` 的主要流程：

1. 创建运行目录并确认知识源存在。
2. 扫描支持文件。
3. 逐个解析文件并切片。
4. 生成预检报告；超过 Qdrant Local 上限或没有可索引文本时不发布新索引。
5. 加载 Embedding 模型。
6. 在 `.build-<uuid>` staging 目录创建 SQLite、Qdrant Local、BM25。
7. 分批向量化并写入 Qdrant。
8. 写入 documents/chunks 和 BM25。
9. 校验 Qdrant 点数、SQLite chunk 数、BM25 可用性。
10. 将 staging 产物发布到活动路径；旧产物移动到 backup；发布失败时恢复旧产物。

这是当前最重要的稳定性资产，必须保留：

- staging 构建；
- 产物数量校验；
- 发布前不影响旧索引；
- 发布失败回滚；
- 模型失败不清空已有索引。

当前限制：

- 每次都是全量重建；
- 没有新文件、已修改、未变化、已删除报告；
- 没有增量写入；
- Qdrant Local 只能由单进程打开；
- 解析与索引任务仍在 Server 之外手工运行，没有独立 Worker。

已有静态运行报告 `data/reports/index-report-20260819-162931.json` 表明一次预检统计为 498 个支持文件、5362 个切片，文件类型为 Markdown 423、PPTX 37、XLSX 10、PDF 16、DOCX 12，解析状态均为 `parsed`，无错误；该文件是历史报告，不代表本次实时运行结果。

## 9. 数据库与存储结构

### 9.1 SQLite

`app/database.py::IndexDatabase` 当前初始化两张表：

#### documents

- `document_id` 主键
- `source_path` 唯一
- `file_name`
- `file_type`
- `file_size`
- `mtime_ns`
- `sha256`
- `parse_status`
- `index_status`
- `error`
- `indexed_at`

#### chunks

- `chunk_id` 主键
- `document_id` 外键字段
- `ordinal`
- `source_path`
- `file_name`
- `text`
- `heading_path`
- `location_json`

当前没有单独的 `metadata`、`entities`、`facts` 表，也没有事实证据绑定、冲突状态、文档版本、OCR 状态、质量检测结果、变更状态和删除状态。V1 手册第 10 节要求的知识管理实体尚未实现。

`IndexDatabase.reset()` 是全量删除操作，但当前索引发布使用 staging 数据库，不会先清空活动数据库，这是合理的安全设计。后续扩展 Schema 时应采用显式迁移或新 staging Schema，不应破坏旧索引回滚能力。

### 9.2 Qdrant Local

`app/vector_store.py`：

- 使用 Qdrant Local 文件路径；
- collection 名为 `design_management_chunks`；
- 向量尺寸固定 1024；
- 距离为 COSINE；
- payload 保存 document_id、文件名、源路径、标题路径和 location；
- 查询只返回 ID 和分数，不返回 payload，随后从 SQLite 读取 Chunk。

可以保留 Qdrant 封装和单进程安全边界。V1 需要将 Metadata 放入可过滤的 payload 或建立与 SQLite 一致的过滤策略，并在服务/Worker 拆分后解决 Local 锁问题。

### 9.3 BM25

`app/bm25.py`：

- 使用 jieba 分词；
- 额外保留英文标识符和数字编码；
- 使用 `rank_bm25.BM25Okapi`；
- 将 chunk ID 和分词语料保存到 JSON。

BM25 是 V1 必须保留的检索基础。当前没有对关键词分析、同义词、领域词典和检索调试信息做持久化。

## 10. Retriever 审计

当前 `app/retriever.py::Retriever.search()` 的链路是：

```text
问题
  -> EmbeddingService.embed_query
  -> Qdrant dense top 20
  -> BM25 top 20
  -> RRF
  -> 取融合候选
  -> SQLite 取 Chunk
  -> Reranker（可选）
  -> 按 reranker 或 RRF 分数排序
  -> 最终 top 8
```

已具备的能力：

- Dense 检索；
- BM25 检索；
- RRF 融合；
- 可选 Reranker；
- 返回 dense_hits、bm25_hits、fused_hits、reranker_used 统计；
- 保留 dense_rank、bm25_rank、reranker_score。

与 V1 Retrieval Engine 的差距：

1. 没有 Query Analysis；问题没有被识别为事实、制度、案例、方法等类型。
2. 没有关键词分析输出；BM25 只直接使用原问题分词。
3. 没有 Metadata Filter；无法按板块、知识类型、专业、业态、阶段过滤。
4. 没有“软过滤优先、无结果回退全库”的策略。
5. 没有独立的 Deduplicate 阶段；目前只有 chunk ID 层面避免同一 chunk 重复。
6. 没有最终 Evidence 阶段；检索命中直接交给 Answer 的 context 组装。
7. 没有保存完整的关键词召回、向量召回、RRF、rerank、final evidence 列表，因此无法在页面解释“为什么答错”。
8. 没有跨文档、同文档相邻 chunk、版本文档的去重和多样性控制。
9. Embedding 模型失败时没有 Retriever 级别的 BM25-only 降级；服务启动可能继续，但查询会因模型不可用失败。

当前 RRF 实现 `reciprocal_rank_fusion()` 是简单、可复用的纯函数，建议保留并纳入新的 Retrieval Pipeline。

## 11. Answer Engine 与 Citation 审计

### 11.1 当前答案流程

`app/answer.py::generate_answer()`：

1. 将最终 hits 组装为最多约 12000 字符的模型上下文。
2. 为上下文记录分配 `[S1]` 至 `[S8]`。
3. 使用统一系统提示词，要求只依据证据回答。
4. 要求输出“结论、制度/管理依据、实施建议、案例参考、来源”。
5. 校验模型输出中出现的来源标记是否属于本次上下文。
6. 校验失败时再请求一次修复。
7. 仍失败则返回引用校验失败提示及允许的来源记录。

`app/main.py` 捕获 `LLMError` 并返回 HTTP 503。因此在当前代码中，未配置或不可用的 LLM 不会进入 V1 要求的显式“无答案拒答”流程，而是被视为服务错误。

### 11.2 可保留能力

- 证据先于生成的上下文组装方式；
- 明确禁止编造制度名称、条款号和项目事实的系统提示；
- `[S1]` 等引用标记；
- `validate_citations()` 的来源 ID 校验；
- 引用记录包含文件名、源路径、标题路径、定位信息和原文摘录；
- LLM 请求失败不应伪造答案。

### 11.3 V1 差距

1. 没有 Answer Router。
2. 没有 `FACT_QUERY`、`POLICY_QUERY`、`CASE_QUERY`、`METHOD_QUERY`、`GENERAL_QUERY` 五类路由。
3. 没有事实库直查；事实问题会走 LLM。
4. 没有按问题类型确定“引用回答、案例总结、方法总结、无依据拒答”的策略。
5. 没有将原文片段、页码、标题、Sheet 等引用字段统一建模为 Citation 对象。
6. 没有引用准确率评测。
7. 没有基于证据充分性的明确拒答判定；“没有 hits”和“LLM 失败”混在不同异常路径中。

## 12. 前端现状

当前页面为单页、轻量问答界面：

- 显示服务状态；
- 显示 documents/chunks 数量；
- 输入问题并调用 `/api/chat`；
- 显示答案、耗时、引用校验状态；
- 展示来源文件、章节、定位和摘录。

页面可以作为 V1 Server 的兼容 UI 基础，但当前没有：

- Retrieval Debug 页面；
- 问题分类/Answer Router 展示；
- Metadata 筛选；
- 文档管理；
- OCR 待处理队列；
- Worker 状态；
- Facts 和证据关系展示；
- Gold 问题评测结果展示。

## 13. 测试现状

当前测试文件只有两个：

### `tests/test_core.py`

覆盖：

- 标题安全切片和文本保留；
- RRF 排序；
- Citation 标记校验；
- 大段落重叠处理；
- 上下文长度和来源记录边界。

### `tests/test_indexer.py`

覆盖：

- 使用假的 Embedding；
- 创建临时知识源；
- 构建 staging 索引；
- 检查 SQLite chunk 数；
- 检查 Qdrant 点数。

当前没有发现以下测试：

- PDF、DOCX、XLSX、PPTX、Markdown 解析器测试；
- 编码错误和乱码质量测试；
- OCR 状态测试；
- Metadata 测试；
- Query Analysis 测试；
- Metadata Filter 和回退测试；
- Reranker 前后变化测试；
- Answer Router 测试；
- Citation 字段完整性测试；
- Worker 与 Server 隔离测试；
- 删除/修改/未变化文档状态测试；
- 50 个 Gold 问题；
- Hit@1/3/5、MRR、引用准确率、拒答率自动评测。

本次按 TASK-001 的“代码分析”边界未执行测试，因此本报告不宣称当前测试已通过。后续 TASK-015 之前应建立可重复的 fixture 和独立测试数据，不能依赖真实公司文件。

## 14. 可保留模块

下表是“保留并迁移”，不是表示这些模块已经满足 V1：

| 当前模块 | 可保留部分 | V1 迁移方向 |
|---|---|---|
| `app/config.py` | Windows 用户环境读取、知识源默认路径、模型配置 | 拆成 Server/Worker 配置，增加 schema、OCR、状态和存储配置 |
| `app/domain.py` | SourceBlock、Chunk、ParsedDocument、SearchHit 基础对象 | 增加 Metadata、DocumentStatus、Evidence、Citation、Fact 等对象 |
| `app/parsers.py` | 文件扫描、PyMuPDF、DOCX、XLSX、PPTX、Markdown 基础解析 | 拆到 Loader/Parser/Quality Check；移除 `errors="replace"` |
| `app/chunker.py` | 段落/句子边界切片和 overlap | 增加版本、Metadata 继承和质量标记 |
| `app/embeddings.py` | BGE-M3、Reranker、CUDA/CPU 回退 | 由 Worker 管理批处理，Server 只使用已建索引 |
| `app/bm25.py` | jieba、代码/数字 token、BM25 持久化 | 接入 Query Analysis、领域词典和 Debug |
| `app/vector_store.py` | Qdrant Local collection、1024 维、点数校验 | 保留 Qdrant 能力，补 Metadata payload/过滤和 Server/Worker 锁策略 |
| `app/indexer.py` | staging、校验、备份、回滚 | 迁入 Worker，加入状态检测和增量准备 |
| `app/database.py` | SQLite 连接、documents/chunks 基础存储 | 扩展 metadata/entities/facts/quality/state/citation 结构 |
| `app/retriever.py` | RRF 纯函数、Dense/BM25/Reranker 主链路 | 重构为可调试的 Retrieval Pipeline |
| `app/answer.py` | 证据上下文、[S1] 引用、引用校验 | 拆成 Answer Router、事实直答、证据型生成和拒答 |
| `app/llm.py` | OpenAI 兼容请求、超时、重试、密钥不打印 | 保留为生成 Provider，不作为事实查询唯一入口 |
| `app/main.py` | FastAPI、静态页面、兼容 `/api/chat` | 只保留 Server/API 编排，将 Worker 逻辑移出 |
| `tests/` | 临时目录和 FakeEmbedding 思路 | 扩展为各模块 fixture、Gold 集和评测测试 |

## 15. 应替换或重构的模块

这里的“替换”指在 V1 副本中逐步迁移，不表示 TASK-001 可以删除旧代码。

| 目标 | 当前问题 | 后续任务 |
|---|---|---|
| Document Engine | `parsers.py` 同时承担扫描和解析，缺质量层，允许乱码替换 | TASK-003、004、005 |
| Worker | 索引是手工脚本，Server 与 Qdrant Local 进程边界不清 | TASK-003、010、011 |
| Retrieval Engine | 无 Query Analysis、Metadata Filter、Debug、Evidence | TASK-006、007、013 |
| Answer Engine | 所有问题统一进 LLM，无事实直查和拒答路由 | TASK-008、014 |
| Citation | 引用校验存在，但没有独立统一数据模型和准确率评估 | TASK-009、016 |
| Storage Schema | 只有 documents/chunks，缺 metadata/entities/facts | TASK-012、013、014 |
| State/Incremental | 仅记录索引时文件指纹，没有状态对比和删除报告 | TASK-005、010、015 |
| Tests/Evaluation | 只有少量单元测试，没有 50 Gold 问题 | TASK-015、016 |
| Startup/Operations | 没有 start/stop/check 脚本 | TASK-011 |
| Documentation | README 仍然是 V0.1，描述了不支持 OCR/增量 | TASK-017 |

## 16. 关键风险与约束

### 高风险

1. **乱码进入索引**：Markdown 的 `errors="replace"` 会掩盖真实编码问题，直接违背 V1 质量要求。
2. **Server 与 Local Qdrant 锁冲突**：当前 README 已提示索引时必须停止服务；如果直接并行化而不拆 Worker，会破坏运行稳定性。
3. **统一 LLM 路由导致事实幻觉风险**：没有 Facts 直查，项目事实问题无法做到程序直接回答。
4. **Metadata 引入后的零召回风险**：V1 必须采用软过滤和全库回退，不能把自动标签当硬门槛。
5. **路径必须保持唯一**：后续 V1 文档和任务均使用 `D:\AI智能体\AI设计管理RAG-V1`，不得重新引入其他代码目录。

### 中风险

1. BGE-M3 只启用 dense 返回值，当前 BM25 是独立词法检索；这不是错误，但不要误称为 BGE-M3 sparse hybrid。
2. `data/` 运行产物不在 Git 中，当前只看到历史预检报告，不能据此推断活动索引完整可用。
3. 当前目录没有 Git 元数据，后续无法按 Task List 直接执行阶段提交。
4. SQLite Schema 没有明确迁移版本，直接增加字段可能影响 staging、回滚和旧数据读取。
5. 当前 `/api/health` 对 LLM 做网络探测；若 LLM 不可用，服务整体会显示 degraded，但这不等于本地 Server、SQLite、BM25 和 Qdrant 都不可用。

### 低风险/可延后

1. 前端目前是轻量页面，不需要在早期重做视觉界面。
2. XLSX 公式、隐藏行列和 PPTX 精确标题可在基础链路稳定后提高。
3. 旧系统目录应保留，不应为 V1 清理或覆盖旧系统。

## 17. 建议的后续执行边界

本报告完成后停止，不执行后续 Task。按两份 V1 依据，下一步应先由项目负责人确认：

1. 正式代码目录固定为 `D:\AI智能体\AI设计管理RAG-V1`。
2. 当前目录是否需要初始化 Git 并建立 V1 分支；这属于 TASK-002，不应在本审计阶段隐式完成。
3. V1 是从当前目录复制旧系统，还是当前目录已经被指定为 V1 副本；这属于 TASK-002 的范围。

确认后，严格按 TASK-002 开始，先建立可回退副本，再创建 V1 目录结构。不得在 TASK-001 报告阶段修改 `D:\设计管理`、源码、依赖、Python、CUDA 或现有运行数据。

## 18. TASK-001 验收结论

| 验收项 | 结果 |
|---|---|
| 当前目录结构已审计 | 已完成 |
| 启动入口已审计 | 已完成 |
| API 入口已审计 | 已完成 |
| 模型加载已审计 | 已完成 |
| Parser 流程已审计 | 已完成 |
| Retrieval 流程已审计 | 已完成 |
| Answer 流程已审计 | 已完成 |
| 数据库结构已审计 | 已完成 |
| 可复用模块已识别 | 已完成 |
| 应替换模块已识别 | 已完成 |
| 未修改代码 | 是 |
| 未安装依赖 | 是 |
| 未改变 Python/CUDA 环境 | 是 |
| 输出审计报告 | 本文件 |

**TASK-001：完成。**
