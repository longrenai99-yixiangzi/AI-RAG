# AI设计管理知识库 V1.0 环境与模型基准

> 任务：TASK-002.5 环境与模型基准确认  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 检查日期：2026-08-22  
> 检查方式：只读检查

## 1. 执行边界

本次只确认 V1 后续重构使用的运行环境，不进行环境变更：

- 未安装依赖；
- 未升级 Torch；
- 未修改 Python 虚拟环境；
- 未改变 CUDA；
- 未加载 BGE-M3 或 Reranker 权重；
- 未启动 FastAPI 服务；
- 未执行索引构建。

## 2. Python 环境

| 项目 | 当前值 |
|---|---|
| 项目目录 | `D:\AI智能体\AI设计管理RAG-V1` |
| 虚拟环境 | `D:\AI智能体\AI设计管理RAG-V1\.venv` |
| Python 可执行文件 | `D:\AI智能体\AI设计管理RAG-V1\.venv\Scripts\python.exe` |
| Python 实现 | CPython |
| Python 版本 | 3.12.13 |
| 虚拟环境状态 | 已确认，`sys.prefix != sys.base_prefix` |
| 基础 Python | `C:\Users\liu\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none` |

后续 V1 重构默认继续使用该虚拟环境，不重新创建环境。

## 3. Torch、CUDA 与 GPU 状态

### 3.1 Torch/CUDA 运行状态

通过当前 V1 `.venv` 只读检查：

```text
torch.__version__         = 2.13.0+cpu
torch.version.cuda        = None
torch.cuda.is_available() = False
```

结论：当前 V1 Python 环境是 CPU 版 Torch，不是 GPU/CUDA 版 Torch；当前 PyTorch 无法使用 CUDA。

### 3.2 物理 GPU 状态

只读枚举到以下显示适配器：

| 适配器 | 驱动版本 | 状态 |
|---|---|---|
| Intel(R) UHD Graphics | 31.0.101.5445 | OK |
| NVIDIA GeForce RTX 4060 Laptop GPU | 32.0.16.1074 | OK |

必须区分：机器上存在且驱动状态正常的 NVIDIA RTX 4060 Laptop GPU，但当前 V1 虚拟环境中的 Torch 没有 CUDA 构建，因此当前程序运行层面仍是 CPU。后续如需启用 GPU，必须另行授权，不能在本任务中安装或升级 Torch。

## 4. 执行边界结论

本文件只记录环境基线，不改变环境、不安装依赖、不加载模型、不启动服务。

## 5. Embedding 模型

### 5.1 V1 当前代码配置

`app/config.py` 固定配置：

```text
模型标识：BAAI/bge-m3
加载类：FlagEmbedding.BGEM3FlagModel
向量维度：1024
```

`app/embeddings.py` 在加载时将 `HF_HOME` 设置为：

```text
D:\AI智能体\AI设计管理RAG-V1\data\cache\huggingface
```

当前代码使用的是 Hugging Face 模型标识，并将缓存根目录指向 V1 项目数据目录；它不是一个已经写死的本地 `models/bge-m3` 路径。

### 5.2 磁盘实际检查

V1 项目中：

```text
D:\AI智能体\AI设计管理RAG-V1\data\cache\huggingface  存在
模型权重目录                                          未发现
```

当前 V1 目录没有 `models/`，缓存目录下也没有发现 `BAAI/bge-m3` 的本地权重目录。因此本报告不能确认 V1 当前目录已经具备可直接离线加载的 Embedding 权重。

另发现旧工作区存在：

```text
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3
```

该路径不属于 V1 正式工作目录，当前 V1 的 `Settings` 没有引用它，不应在后续重构中未经确认直接当作 V1 模型路径使用。

## 6. Reranker 模型

### 6.1 V1 当前代码配置

`app/config.py` 固定配置：

```text
模型标识：BAAI/bge-reranker-v2-m3
加载类：FlagEmbedding.FlagReranker
模式：RAG_ENABLE_RERANKER，默认 auto
```

`app/embeddings.py` 与 Embedding 共用以下 Hugging Face 缓存根目录：

```text
D:\AI智能体\AI设计管理RAG-V1\data\cache\huggingface
```

### 6.2 磁盘实际检查

V1 项目缓存中未发现 `BAAI/bge-reranker-v2-m3` 的本地权重目录。

另发现旧工作区存在：

```text
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3
```

该路径不属于 V1 正式工作目录，当前 V1 代码未引用它。当前基准结论是：V1 已配置 Reranker 模型标识，但 V1 本地实际权重路径尚未固定。

## 7. LLM 配置方式

### 7.1 配置来源

`app/config.py` 的读取顺序是：

1. 当前进程环境变量；
2. Windows 当前用户环境变量注册表；
3. 若无值则使用代码默认值。

当前检查显示以下配置来自当前进程环境变量：

| 配置项 | 当前状态 |
|---|---|
| `RAG_API_BASE_URL` | 已配置：`http://10.11.139.124:3000/v1` |
| `RAG_CHAT_MODEL` | 已配置：`deepseek_v4_pro_public` |
| `RAG_API_KEY` | 已配置；密钥内容不输出 |
| `Settings.api_ready` | `True` |

### 7.2 请求方式

`app/llm.py` 使用 OpenAI 兼容接口：

```text
POST {RAG_API_BASE_URL}/chat/completions
```

请求使用：

- `RAG_CHAT_MODEL` 作为 model；
- `RAG_API_KEY` 作为 Bearer Token；
- httpx；
- 连接超时 15 秒、总超时 60 秒；
- 最多重试 3 次。

当前项目没有发现 `.env` 自动加载逻辑；`.env.example` 仅用于说明变量格式。实际配置依赖当前进程环境变量或 Windows 用户环境变量。

## 8. Qdrant 存储位置

### 8.1 V1 配置位置

`app/config.py::Settings.qdrant_path` 指向：

```text
D:\AI智能体\AI设计管理RAG-V1\data\qdrant
```

`app/vector_store.py` 使用 Qdrant Local：

- collection：`design_management_chunks`；
- 向量维度：1024；
- 距离：COSINE；
- 单进程打开约束。

### 8.2 磁盘实际状态

当前 `data/qdrant` 目录存在，检查到：

```text
data/qdrant/collection/
data/qdrant/.lock
data/qdrant/meta.json
```

该目录属于运行数据，不纳入 Git 源码提交。索引构建和 Web 服务不能同时打开该 Qdrant Local 目录，后续 Server/Worker 拆分时必须保留并解决这一约束。

## 9. 基准判断

当前可确认的环境基线：

1. Python 3.12.13 虚拟环境可用。
2. Torch 为 `2.13.0+cpu`，CUDA 不可用。
3. 物理 NVIDIA RTX 4060 Laptop GPU 存在且驱动状态为 OK，但尚未被当前 Torch 使用。
4. Embedding 和 Reranker 的模型标识已配置，但 V1 目录内没有发现对应本地权重目录。
5. 旧工作区有模型文件，但不属于 V1 当前配置，不能直接视为 V1 模型路径。
6. LLM 通过当前进程环境变量配置，配置状态完整，密钥未输出。
7. Qdrant Local 使用 `D:\AI智能体\AI设计管理RAG-V1\data\qdrant`。

后续重构必须以以上事实为准，不得把“存在 GPU”误写成“当前 V1 已启用 GPU”，也不得把旧工作区模型路径误写成 V1 已配置路径。

**TASK-002.5：完成。**
