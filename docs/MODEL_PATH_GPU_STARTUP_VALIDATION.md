# 模型路径与 GPU 启动验证报告

## 1. 验证范围

本报告对应 TASK-012.7，目标是统一 V1 模型资产路径并增加启动前 GPU 检查。

本次未修改业务逻辑、Document Pipeline 或 Retrieval 算法，未执行全库 Embedding，未清空或重建正式 Qdrant。

## 2. 模型资产

模型已复制到 V1 正式目录：

| 模型 | V1 路径 | 文件数 | 文件总大小 |
|---|---|---:|---:|
| BGE-M3 | `D:\AI智能体\AI设计管理RAG-V1\models\bge-m3` | 69 | 2,298,353,048 bytes |
| bge-reranker-v2-m3 | `D:\AI智能体\AI设计管理RAG-V1\models\bge-reranker-v2-m3` | 12 | 2,293,244,790 bytes |

复制来源为既有本地模型资产：

- `D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3`
- `D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3`

`models/` 已加入 `.gitignore`，避免模型权重进入 Git 版本库。

## 3. 路径配置

`app/config.py` 的默认配置已改为 V1 本地模型目录：

- `RAG_EMBEDDING_MODEL_PATH`，默认 `D:\AI智能体\AI设计管理RAG-V1\models\bge-m3`
- `RAG_RERANKER_MODEL_PATH`，默认 `D:\AI智能体\AI设计管理RAG-V1\models\bge-reranker-v2-m3`

仍可通过环境变量覆盖默认路径。`.env.example` 已补充这两个配置项示例。

## 4. GPU 运行环境

| 项目 | 验证结果 |
|---|---|
| GPU Python | `D:\AI设计管理知识库\.venv\Scripts\python.exe` |
| Python | 3.12.13 |
| Torch | 2.12.1+cu132 |
| Torch CUDA | 13.2 |
| `torch.cuda.is_available()` | `True` |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |

V1 自有 `.venv` 仍为原来的 `torch 2.13.0+cpu`，本任务未替换、升级或安装环境。GPU 启动脚本明确复用已经验证可用的历史 CUDA 环境。

## 5. 启动前检查

新增：

- `scripts/check_gpu.py`
- `scripts/start_gpu.ps1`

启动流程为：

```text
检查 CUDA 与模型目录
        ↓ 失败立即停止
使用 CUDA Python 启动 uvicorn app.main:app
```

正常启动命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_gpu.ps1
```

如需指定端口：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_gpu.ps1 -Port 8010
```

注意：旧服务仍占用 `8000` 且独占 `data\qdrant`。正式切换到 GPU 启动前，应先正常停止当前服务，避免两个进程同时打开同一个 Qdrant Local 目录。

## 6. 验证结果

### 6.1 GPU 前置检查

使用历史 CUDA Python 执行 `python -m scripts.check_gpu`：

- 状态：`ok`
- CUDA：可用
- GPU 数量：1
- BGE-M3 目录：存在
- Reranker 目录：存在

使用 V1 CPU `.venv` 做反向验证：

- `torch.cuda.is_available()`：`False`
- 检查脚本退出码：`1`
- 服务启动：被阻止

因此启动检查不会在 CPU 环境下静默降级运行。

### 6.2 BGE-M3 加载

使用 V1 本地路径和 CUDA 环境真实加载 BGE-M3，并执行单条查询向量化：

- 加载：通过
- 向量维度：1024
- 设备：CUDA

仅处理单条测试文本，没有执行知识库批量向量化。

### 6.3 Reranker 加载

使用 V1 本地路径和 CUDA 环境真实加载 `bge-reranker-v2-m3`，对单条候选文本打分：

- 加载：通过
- 返回分数：`4.5390625`
- 设备：CUDA

### 6.4 Retrieval Pipeline 调用

使用一个内存测试 Chunk 验证：

```text
BM25 / Dense → RRF → Reranker → Context Builder → Citation
```

结果：

- 命中数：1
- Dense 命中数：1
- Reranker：已使用
- Citation 校验：通过
- location：完整返回

本次使用的是内存 Qdrant 测试集合，没有连接生产 Qdrant collection。

### 6.5 V1 FastAPI 隔离启动

新增 `scripts/validate_startup.py`，仅用于本次安全验证：

- 使用同一份 V1 `app.main:app`
- 使用 CUDA Python
- 使用临时 Qdrant 数据目录
- 使用 `8010` 端口
- 不打开当前正式 `data\qdrant`

HTTP 验证结果：

```json
{
  "api_configured": false,
  "embedding_ready": true,
  "embedding_device": "cuda",
  "vector_db": true,
  "index": {
    "documents": 0,
    "chunks": 0
  }
}
```

服务已正常响应 `/api/status` 和 `/api/health`，验证进程随后已结束。健康状态为 `degraded` 的原因仅是隔离验证主动关闭了远程 LLM 网络探测；本地 Embedding 和 Vector DB 均通过。

## 7. 回归测试

```text
61 passed, 1 skipped in 3.53s
```

跳过项为真实模型 Shadow 测试的条件跳过项，不是本次路径配置失败。

## 8. 未完成与限制

1. V1 自有 `.venv` 仍是 CPU Torch，本任务没有替换它；GPU 运行依赖 `D:\AI设计管理知识库\.venv`。
2. 当前正式 `8000` 服务没有被强行重启，避免与其正在使用的 Qdrant Local 目录发生竞争；同一 V1 FastAPI 代码已通过隔离目录启动验证。
3. Reranker 在现有 FastAPI `/api/status` 中默认按需加载，真实 Reranker 加载已通过独立 Retrieval Pipeline 调用验证。
4. 远程 LLM 未作为本次本地 GPU 启动验收条件；本次没有发送问答请求，也没有执行全库 Embedding。

## 9. 变更文件

- `app/config.py`
- `.env.example`
- `.gitignore`
- `scripts/check_gpu.py`
- `scripts/start_gpu.ps1`
- `scripts/validate_startup.py`
- `docs/MODEL_PATH_GPU_STARTUP_VALIDATION.md`
