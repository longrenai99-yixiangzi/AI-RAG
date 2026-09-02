# V1 CUDA 环境迁移报告

> 任务：TASK-012.6 CUDA 环境迁移方案  
> 正式代码目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 历史 CUDA 环境：`D:\AI设计管理知识库\.venv`  
> 检查日期：2026-08-22

## 1. 结论

历史环境已经验证可用，可以直接复用，不需要复制模型、修改业务代码或重建 Document Pipeline。当前 V1 自有 `.venv` 仍为 CPU 环境，因此本次采用“V1 代码目录 + 历史 CUDA Python”方案，不宣称已替换 V1 `.venv`。

## 2. 两个虚拟环境对比

| 项目 | V1 当前环境 | 历史 CUDA 环境 |
|---|---|---|
| Python 路径 | `D:\AI智能体\AI设计管理RAG-V1\.venv\Scripts\python.exe` | `D:\AI设计管理知识库\.venv\Scripts\python.exe` |
| Python 版本 | 3.12.13 | 3.12.13 |
| Torch | 2.13.0+cpu | 2.12.1+cu132 |
| Torch CUDA 构建 | None | 13.2 |
| `cuda.is_available()` | False | True |
| GPU 数量 | 0 | 1 |
| GPU | 未被 Torch 使用 | NVIDIA GeForce RTX 4060 Laptop GPU |

除 Torch 和 Transformers（5.15.0 vs 5.15.1）外，FastAPI、Qdrant、FlagEmbedding、解析器、BM25、PyYAML 和测试依赖版本一致。

## 3. GPU 与模型验证

系统 `nvidia-smi` 已识别：

| 项目 | 结果 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| 驱动 | 610.74 |
| NVIDIA CUDA UMD | 13.3 |

历史 CUDA Python 实际验证：

| 测试 | 结果 |
|---|---|
| `torch.__version__` | `2.12.1+cu132` |
| `torch.version.cuda` | `13.2` |
| `torch.cuda.is_available()` | `True` |
| `torch.cuda.get_device_name(0)` | RTX 4060 Laptop GPU |

### 3.1 BGE-M3

模型路径：`D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3`

使用历史环境、FP16 和单样本查询验证成功：

- `cuda=True`；
- 返回有效 Dense 查询分数；
- CUDA 显存约 1.15 GB 已分配；
- 未执行全库 Embedding。

### 3.2 Reranker

模型路径：`D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3`

使用历史环境、FP16 和单样本评分验证成功：

- `cuda=True`；
- 返回有效 Reranker 分数；
- CUDA 显存约 1.14 GB 已分配；
- 未执行全库 Embedding。

## 4. 推荐迁移方案：直接复用历史环境

代码仍位于：`D:\AI智能体\AI设计管理RAG-V1`。

启动 V1 Server：

```powershell
Set-Location 'D:\AI智能体\AI设计管理RAG-V1'
& 'D:\AI设计管理知识库\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

运行 V1 测试：

```powershell
Set-Location 'D:\AI智能体\AI设计管理RAG-V1'
& 'D:\AI设计管理知识库\.venv\Scripts\python.exe' -m pytest -q
```

该方案不创建新代码副本、不复制模型、不修改业务代码，并直接获得已验证 CUDA 能力。

## 5. 方案 B：重建 V1 独立 CUDA 环境

本次不执行方案 B。若后续必须让 V1 自有 `.venv` 的 `cuda.is_available()` 返回 True，应另行授权后：

1. 备份当前 V1 `.venv`；
2. 使用 Python 3.12.13；
3. 安装与驱动兼容的 CUDA Torch；
4. 对齐历史环境依赖；
5. 只做小样本 BGE/Reranker GPU 验证；
6. 通过后再决定是否保留独立环境。

本次没有生成 `requirements_cuda_migration.txt`，因为方案 A 已验证可以直接复用已有 CUDA 环境，且依赖基本一致。

## 6. 当前 V1 `.venv` 建议

不要继续在当前 V1 `.venv` 上重复下载大 Torch Wheel。当前 V1 `.venv` 可保留为 CPU 回退环境，但 GPU 启动入口必须明确使用历史 CUDA Python；后续启动脚本应先断言 `torch.cuda.is_available()`，失败则停止而不是静默回退 CPU。

## 7. TASK-012.6 验收结论

| 验收项 | 结果 |
|---|---|
| Python 环境路径 | 已确认 |
| Torch 版本对比 | 已完成 |
| CUDA 状态对比 | 已完成 |
| GPU 型号确认 | 已完成 |
| BGE-M3 GPU 单样本验证 | 通过 |
| Reranker GPU 单样本验证 | 通过 |
| 复用已有 CUDA 环境方案 | 已确认可行 |
| 未修改业务代码 | 是 |
| 未修改 Document Pipeline | 是 |
| 未修改 Retrieval 逻辑 | 是 |
| 未执行全库 Embedding | 是 |
| V1 自有 `.venv` 已替换为 CUDA | 否，保留原 CPU 环境 |

**TASK-012.6：历史 CUDA 环境复用方案和 GPU 模型验证完成。**
