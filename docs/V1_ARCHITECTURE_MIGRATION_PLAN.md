# AI设计管理知识库 V1.0 架构迁移计划

> 任务：TASK-003 V1 架构骨架重构准备  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 状态：仅完成骨架和计划，未执行代码迁移

## 1. 当前基线原则

当前 `app/main.py` 继续作为兼容入口，现有扁平模块继续保留，当前阶段不移动核心业务文件、不修改现有运行逻辑。

已建立的目标目录只承担未来职责说明：

```text
app/api
app/core
app/core/retrieval
app/core/answer
app/core/citation
app/ingestion
app/storage
worker
```

## 2. 当前模块到未来模块的对应关系

| 当前模块 | 当前职责 | 未来模块 | 迁移策略 |
|---|---|---|---|
| `app/main.py` | FastAPI 装配、生命周期、API 路由 | `app/api` | 先保留兼容入口，再逐步抽取路由和应用装配 |
| `app/static/*` | 当前问答前端 | `app/api` 配套静态资源 | 先原位保留，后续按 API 兼容性调整 |
| `app/config.py` | 环境变量、路径和运行设置 | `app/core` | 保留兼容读取，后续拆分 Server/Worker 配置 |
| `app/domain.py` | SourceBlock、Chunk、ParsedDocument、SearchHit | `app/core` | 扩展领域对象，避免一次性替换旧对象 |
| `app/retriever.py` | Dense/BM25/RRF/Reranker 链路 | `app/core/retrieval` | 先包裹现有 Retriever，再增加分析、过滤、Debug |
| `app/bm25.py` | BM25 分词、构建、搜索 | `app/core/retrieval` | 保留实现，增加领域词和调试输出 |
| `app/vector_store.py` | Qdrant Local 封装 | `app/storage` 与 `app/core/retrieval` | 存储适配与检索策略分离，保留 Qdrant Local 约束 |
| `app/embeddings.py` | BGE-M3 和 Reranker 加载/推理 | `app/core/retrieval` | 保留模型环境，后续由 Worker/检索服务分别调用 |
| `app/answer.py` | 上下文、LLM 生成、Citation 校验 | `app/core/answer`、`app/core/citation` | 先拆测试边界，再抽取 Router 和 Citation |
| `app/llm.py` | OpenAI 兼容生成接口 | `app/core/answer` | 保留 Provider，避免成为事实查询唯一入口 |
| `app/parsers.py` | 文件扫描和五类格式解析 | `app/ingestion` | 按 Loader/Parser/Quality Check 分步迁移 |
| `app/chunker.py` | 文本切片和 overlap | `app/ingestion` | 保留切片行为，增加版本和 Metadata 继承 |
| `app/indexer.py` | 全量构建、staging、发布、回滚 | `worker`、`app/storage` | 先保持命令可用，再提取 Worker 编排 |
| `app/database.py` | SQLite documents/chunks | `app/storage` | 先增加 Schema 迁移，再拆 Repository |
| `scripts/index_vault.py` | 索引命令入口 | `worker` / `scripts` | 保留旧命令，后续改为 Worker 调度入口 |
| `scripts/doctor.py` | 环境体检 | `scripts` | 继续保留，后续补充 Server/Worker/模型状态 |

## 3. 迁移顺序

迁移顺序遵循“先有兼容边界，再移动职责”的原则：

### 阶段 A：骨架与兼容保护（当前 TASK-003）

- 创建目标目录和职责 README；
- 保留 `app/main.py`；
- 不导入新骨架模块，不改变启动链路；
- 保留当前 BGE-M3、BM25、RRF、Reranker、Qdrant、SQLite 和 staging 能力。

### 阶段 B：Document Engine（TASK-004、TASK-005）

- 先为现有 Parser 增加测试和质量边界；
- 按 Loader → Parser → Quality Check → Chunk → Metadata → Index 形成新接口；
- 逐步将 `parsers.py`、`chunker.py` 的能力接入 `app/ingestion`；
- 增加编码失败、OCR 判断、解析失败和文档状态；
- 旧解析入口在新链路验证前继续保留。

### 阶段 C：Retrieval Engine（TASK-006、TASK-007）

- 先将现有 `Retriever` 包装到 `app/core/retrieval`；
- 保持 Dense + BM25 → RRF → Reranker 的结果兼容；
- 增加 Query Analysis、Metadata Filter、软过滤和全库回退；
- 增加完整 Retrieval Debug 数据；
- 通过测试后再调整 API 返回结构。

### 阶段 D：Answer 与 Citation（TASK-008、TASK-009）

- 在 `app/core/answer` 增加 Answer Router；
- 事实问题先接 Facts 直查，制度/案例/方法问题再使用证据生成；
- 将 `app/answer.py` 的引用记录和校验逻辑抽到 `app/core/citation`；
- 保留 `/api/chat` 兼容响应，避免现有前端立即失效。

### 阶段 E：Server/Worker 拆分（TASK-010、TASK-011）

- 将扫描、OCR、解析、切片和索引编排接入 `worker`；
- Server 只负责网页、API、问答和已发布索引读取；
- 增加 start/stop/check 脚本；
- 保留失败隔离、staging 发布和回滚；
- 明确 Qdrant Local 单进程边界，必要时再评估独立 Qdrant Server。

### 阶段 F：Storage、Metadata、Facts（TASK-012、TASK-014）

- 将 SQLite 基础能力逐步迁入 `app/storage`；
- 扩展 documents、chunks、metadata、entities、facts；
- Facts 必须绑定原文 Evidence；
- 旧 Schema 通过 staging 或迁移策略升级，不直接破坏旧索引。

### 阶段 G：Metadata 与测试评测（TASK-013、TASK-015、TASK-016）

- 建立配置化 Metadata 规则；
- 增加解析器、检索、答案、Citation、状态和 Server/Worker 测试；
- 建立 50 个 Gold 问题和确定性评测；
- 在不引入 LLM-as-Judge 的前提下统计 Hit、MRR、引用准确率和拒答率。

### 阶段 H：V1 验收（TASK-017）

- 按手册检查格式支持、检索链、事实回答、引用、拒答、启动和查询性能；
- 保留旧系统可回退路径；
- 只在测试、评测和兼容性证据充分后宣布 V1 验收。

## 4. 风险点与控制措施

| 风险 | 影响 | 控制措施 |
|---|---|---|
| `app/main.py` 入口被破坏 | 现有 Web 问答无法启动 | 全程保留兼容入口，迁移后先做启动和 API 回归 |
| 新旧模块循环导入 | 服务启动失败 | 先定义核心类型边界，逐层抽取，不同时双向导入 |
| 检索排序变化 | 现有问题命中下降 | 保留 RRF/Reranker 旧链路，新增黄金问题对比 |
| Metadata 硬过滤 | 错误标签导致零召回 | 软过滤优先，无结果自动回退全库 |
| Qdrant Local 进程锁 | Server/Worker 相互阻塞或索引失败 | 保留单进程限制，先隔离生命周期再并行化 |
| 模型路径与环境漂移 | BGE/Reranker 无法加载 | 不改当前 Torch/CUDA；固定模型配置和缓存检查报告 |
| SQLite Schema 直接替换 | 旧索引不可读、回滚失效 | 使用 staging、迁移或兼容读取，保留旧产物 |
| OCR/解析失败传播 | 单文件问题拖垮全量任务 | 文档级状态和异常隔离，Worker 失败不影响 Server |
| Citation 字段不一致 | 答案无法追溯或评测失败 | 统一 Evidence/Citation 模型，覆盖页码、Sheet、章节和片段 |
| 旧文件直接移动/删除 | 代码回退困难、运行逻辑改变 | 当前阶段不移动文件；迁移完成前保留旧实现 |
| 运行数据误提交 | 仓库膨胀或泄露本地数据 | 继续使用 `.gitignore` 排除 `.venv`、data 索引和缓存 |

## 5. TASK-003 边界确认

本任务只建立目录 README 和迁移计划：

- 未删除任何现有 `app` 模块；
- 未移动核心业务文件；
- 未修改现有运行逻辑；
- 未升级依赖；
- 未修改模型或 CUDA 环境；
- 未执行代码迁移。

**TASK-003：骨架准备完成，代码迁移留待后续 Task。**
