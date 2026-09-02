# V1 GPU 环境验证报告

> 任务：TASK-012.5 Dense 运行环境统一  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 检查日期：2026-08-22  
> 状态：验证完成，但 CUDA Torch 尚未就绪

## 1. 执行边界

本次未修改业务代码、Document Pipeline、Retrieval 逻辑、模型文件或系统 CUDA 驱动。

为达到 `torch.cuda.is_available() == True` 曾尝试下载 CUDA Torch Wheel，但下载长时间无进展后已停止；当前虚拟环境仍保持原 CPU Torch，未完成环境切换。

## 2. Python 环境路径

| 项目 | 结果 |
|---|---|
| 项目虚拟环境 | `D:\AI智能体\AI设计管理RAG-V1\.venv` |
| Python 可执行文件 | `D:\AI智能体\AI设计管理RAG-V1\.venv\Scripts\python.exe` |
| Python 版本 | 3.12.13 |
| 实现 | CPython |

历史旧工作区虚拟环境也已只读核验，使用同样的 CPU Torch，不是可复用的 CUDA 环境。

## 3. 当前 Torch/CUDA 状态

当前 V1 `.venv` 实际结果：

```text
torch.__version__         = 2.13.0+cpu
torch.version.cuda        = None
torch.cuda.is_available() = False
torch.cuda.device_count() = 0
```

目标状态是 `torch.cuda.is_available() = True`，当前未达到，因此本 TASK 不能标记为环境验收通过。

## 4. 物理 GPU 与驱动

只读 `nvidia-smi` 检查：

| 项目 | 结果 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| 驱动版本 | 610.74 |
| NVIDIA CUDA UMD | 13.3 |
| 驱动状态 | 可被 `nvidia-smi` 识别 |

机器和驱动具备 GPU 条件，但当前 Python 环境中的 Torch 没有 CUDA 构建，不能把“驱动可见”误写成“PyTorch 已启用 GPU”。

## 5. 模型路径

V1 项目目录中没有本地模型目录：

```text
D:\AI智能体\AI设计管理RAG-V1\models\bge-m3              不存在
D:\AI智能体\AI设计管理RAG-V1\models\bge-reranker-v2-m3 不存在
```

旧工作区中存在可读取的模型文件：

```text
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-m3
D:\AI_ENV\Codex\workspaces\AI-RAG\models\bge-reranker-v2-m3
```

这些路径不属于 V1 正式目录，本次未复制或移动模型。

## 6. BGE-M3 GPU 加载测试

结果：**未通过/未执行 GPU 加载**。

原因：当前 `torch.version.cuda` 为 `None`，`torch.cuda.is_available()` 为 `False`。即使加载模型，也只能落到 CPU，不能证明 GPU 加载。

TASK-011 已验证 BGE-M3 可以在当前 CPU 环境加载并完成 Shadow 推理，但那不是 GPU 加载验证。

## 7. Reranker GPU 加载测试

结果：**未通过/未执行 GPU 加载**。

原因与 BGE-M3 相同：当前 Torch 没有 CUDA 构建，Reranker 不能在 GPU 上运行。

TASK-011 已验证 Reranker Provider 在当前 Transformers 环境下可以通过兼容 shim 在 CPU 上运行；这不等于 GPU 验收通过。

## 8. 环境切换阻塞

可用 CUDA Wheel 已查询到：

```text
torch 2.11.0+cu128
```

本次下载约 2.75 GB，长时间没有完成，已主动停止。停止后检查确认：

- 当前 torch 仍为 `2.13.0+cpu`；
- 没有 pip 安装进程残留；
- 业务代码没有变化。

要完成环境切换，后续需要重新执行 CUDA Torch 安装，并在安装后依次验证：

1. `torch.version.cuda` 非 `None`；
2. `torch.cuda.is_available()` 为 `True`；
3. `torch.cuda.get_device_name(0)` 为 RTX 4060；
4. BGE-M3 Provider 的 device 为 `cuda`；
5. Reranker Provider 的 device 为 `cuda`；
6. 各执行一次小样本推理，不执行全库 Embedding。

## 9. TASK-012.5 验收状态

| 验收项 | 结果 |
|---|---|
| Python 环境路径 | 已确认 |
| Torch 版本 | 已确认：2.13.0+cpu |
| CUDA 构建 | 未就绪：None |
| GPU 型号 | 已确认：RTX 4060 Laptop GPU |
| `torch.cuda.is_available()` 为 True | 未达到 |
| BGE-M3 GPU 加载 | 未通过 |
| Reranker GPU 加载 | 未通过 |
| 未修改业务代码 | 是 |
| 未修改 Document Pipeline | 是 |
| 未修改 Retrieval 逻辑 | 是 |
| 未执行全库 Embedding | 是 |

**TASK-012.5：环境检查完成；GPU Torch 切换被下载耗时阻塞，未宣称验收通过。**
