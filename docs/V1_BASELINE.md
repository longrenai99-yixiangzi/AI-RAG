# AI设计管理知识库 V1.0 工程基线

> 任务：TASK-002 V1 工程基线确认  
> 基线目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 基线日期：2026-08-22  
> 基线分支：`rag-v1-refactor`

## 1. 基线结论

当前正式工作目录已经确认，不创建新的代码副本：

```text
D:\AI智能体\AI设计管理RAG-V1
```

该目录作为后续 V1 重构的唯一基线，保留现有 V0.1 业务代码和 V1 审计/路径文档。

本任务只完成工程基线确认和 Git 基线提交，不修改业务代码、不重构目录、不升级依赖、不安装新包。

## 2. 当前目录结构

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
│  └─ static/            前端 HTML、JavaScript、CSS
├─ scripts/
│  ├─ doctor.py          依赖、Python、CUDA 和路径体检
│  └─ index_vault.py     全量/预检索引命令
├─ tests/
│  ├─ test_core.py       切片、RRF、引用校验测试
│  └─ test_indexer.py    staging 索引发布测试
├─ docs/
│  ├─ 两份 V1 执行依据
│  ├─ PATH_ALIGNMENT.md
│  ├─ V1_CODE_AUDIT.md
│  └─ V1_BASELINE.md
├─ data/                 运行时缓存、索引、Qdrant 和报告目录
├─ .env.example
├─ .gitignore
├─ README.md
└─ requirements.txt
```

当前尚不存在以下 V1 目标目录或脚本，作为后续重构基准记录：

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
- `pyproject.toml`
- `environment.yml`

`.venv/`、`__pycache__/`、`.pytest_cache/` 和主要运行数据按 `.gitignore` 排除，不作为业务源码基线内容。

## 3. 当前运行方式

### 3.1 FastAPI 与前端入口

```text
FastAPI 模块：app.main
FastAPI 对象：app.main:app
前端页面：app/static/index.html
根路径：/
静态资源：/static/style.css、/static/app.js
```

`app/main.py` 当前创建 FastAPI `0.1.0` 应用，并初始化 SQLite、Qdrant Local、BM25、BGE-M3、Reranker、LLM 和 Retriever。

### 3.2 Server 启动命令

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000
```

### 3.3 当前索引命令

```powershell
# 全量索引
.\.venv\Scripts\python.exe -m scripts.index_vault

# 只解析和统计，不发布索引
.\.venv\Scripts\python.exe -m scripts.index_vault --preflight
```

当前没有独立 Worker，文件扫描、解析和索引由 `scripts.index_vault` 手动执行。索引时需按 README 要求关闭 Web 服务，因为 Qdrant Local 不能被两个进程同时打开。

### 3.4 当前 API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/` | 返回前端页面 |
| GET | `/api/status` | 返回知识源、模型和索引统计 |
| GET | `/api/health` | 检查 LLM、Embedding、Qdrant 和知识源目录 |
| POST | `/api/chat` | 执行检索、答案生成和 Citation 校验 |

## 4. 当前 Python 环境

### 4.1 虚拟环境

```text
虚拟环境目录：D:\AI智能体\AI设计管理RAG-V1\.venv
Python 可执行文件：D:\AI智能体\AI设计管理RAG-V1\.venv\Scripts\python.exe
Python 版本：3.12.13
Python 实现：CPython
虚拟环境状态：已确认，sys.prefix 与 sys.base_prefix 不同
基础 Python：C:\Users\liu\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none
```

### 4.2 Torch/CUDA

本次只读检查结果：

```text
torch：2.13.0+cpu
torch CUDA 构建：None
torch.cuda.is_available()：False
```

当前虚拟环境使用 CPU 版 Torch，CUDA 不可用。本任务未改变 Python、Torch 或 CUDA 环境。

## 5. 当前依赖

### 5.1 依赖文件

| 文件 | 状态 |
|---|---|
| `requirements.txt` | 存在，当前唯一依赖清单 |
| `pyproject.toml` | 不存在 |
| `environment.yml` | 不存在 |

### 5.2 requirements.txt 约束

```text
fastapi>=0.128,<1
uvicorn[standard]>=0.40,<1
httpx>=0.28,<1
qdrant-client>=1.19,<2
FlagEmbedding>=1.3,<2
torch>=2.6,<3
rank-bm25>=0.2.2,<1
jieba>=0.42,<1
PyYAML>=6,<7
PyMuPDF>=1.26,<2
python-docx>=1.2,<2
openpyxl>=3.1,<4
python-pptx>=1.0,<2
pytest>=8,<10
```

### 5.3 当前虚拟环境已安装版本

以下版本通过项目 `.venv` 的只读包元数据检查获得，未执行安装或升级：

| Distribution | 当前版本 |
|---|---:|
| fastapi | 0.141.1 |
| uvicorn | 0.52.4 |
| httpx | 0.28.1 |
| qdrant-client | 1.19.0 |
| FlagEmbedding | 1.4.0 |
| torch | 2.13.0+cpu |
| rank-bm25 | 0.2.2 |
| jieba | 0.42.1 |
| PyYAML | 6.0.3 |
| PyMuPDF | 1.28.2 |
| python-docx | 1.2.0 |
| openpyxl | 3.1.5 |
| python-pptx | 1.0.2 |
| pytest | 9.1.1 |

依赖约束文件和当前已安装版本未在本任务中调整。

## 6. 当前 Git 状态

### 6.1 基线前状态

TASK-002 开始时，当前目录没有 `.git`，只读执行 `git status` 和 `git log` 返回“not a git repository”，不存在可用的分支、提交或远程状态。

### 6.2 基线仓库状态

为满足 TASK-002 的基线提交要求，已在当前正式工作目录初始化本地 Git 仓库：

```text
仓库位置：D:\AI智能体\AI设计管理RAG-V1\.git
分支：rag-v1-refactor
```

基线提交包含当前源码、测试、脚本、README、requirements.txt 以及 V1 文档；`.gitignore` 排除的虚拟环境、缓存、Qdrant 和运行报告不纳入源码基线。基线提交完成后应保持工作树 clean。

## 7. 后续重构基准

1. 唯一工作目录保持为 `D:\AI智能体\AI设计管理RAG-V1`，不再创建新的代码副本。
2. 保留当前 FastAPI `/api/chat` 兼容入口，逐步接入新的 Answer Router 和 Retrieval Pipeline。
3. 保留 BGE-M3、BM25、RRF、Reranker、Qdrant Local、SQLite、staging 构建和回滚机制。
4. 不重新安装 CUDA/PyTorch；环境变更必须另行获得明确授权。
5. 以 `V1_CODE_AUDIT.md` 的保留/重构边界作为模块迁移依据。
6. 每个后续 Task 单独测试、说明和 Git 提交。
7. `D:\设计管理` 继续作为只读知识源，不得由系统写回、移动、删除或重命名。

## 8. TASK-002 验收结果

| 验收项 | 结果 |
|---|---|
| 检查当前项目目录结构 | 已完成 |
| 检查 Git 状态 | 已完成；已建立本地 Git 基线仓库 |
| 确认当前 Python 虚拟环境 | 已完成 |
| 确认 requirements.txt | 已完成 |
| 确认 pyproject.toml | 已确认不存在 |
| 确认 environment.yml | 已确认不存在 |
| 确认 FastAPI 入口 | 已完成 |
| 确认前端入口 | 已完成 |
| 确认启动命令 | 已完成 |
| 建立 V1 基线提交 | 已完成 |
| 未修改业务代码 | 是 |
| 未重构目录 | 是 |
| 未升级依赖 | 是 |
| 未安装新包 | 是 |

**TASK-002：完成。**
