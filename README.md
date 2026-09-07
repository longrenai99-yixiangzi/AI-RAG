# AI设计管理知识库 · V1.0 / V2 内部试用

这是一个本地运行、对 `D:\设计管理` 只读的 RAG 问答程序。当前唯一开发基线为 Git 分支 `rag-v1-refactor`；V2 仍处于 8010 内部试用，未切换正式 8000 服务。

## 当前状态

- 开发目录：`D:\AI智能体\AI设计管理RAG-V1`
- Git 基线：`rag-v1-refactor`，当前 HEAD 为 `0492754`
- 知识源：`D:\设计管理`，只读
- 正式服务：`127.0.0.1:8000`，保持未切换
- 内部试用：`127.0.0.1:8010`，V2 Verified RAG 已启用
- Provider 依赖的生成式回答：试用策略关闭；证据展示和确定性事实路径仍可用
- 生产状态：`PRODUCTION_READY = FALSE`

内部试用的冻结点、来源范围和安全边界见 [`docs/V2_INTERNAL_TRIAL_BASELINE.md`](docs/V2_INTERNAL_TRIAL_BASELINE.md)。

当前基础检索闭环为：

```
只读解析资料 → 章节/页码级切片 → BGE-M3 向量检索 + BM25 → RRF 融合
→ 可选重排 → 内网 DeepSeek 生成答案 → 来源引用校验
```

不会移动、删除、重命名或回写 `D:\设计管理` 中的任何文件。运行数据只写入本项目的 `data/`。

## 先决条件

- Windows 11
- 已有的 Python 3.12（本机已检测到）
- Windows 用户环境变量：`RAG_API_BASE_URL`、`RAG_CHAT_MODEL`、`RAG_API_KEY`
- 首次下载模型时可访问 Hugging Face；若网络受限，可先准备本地模型缓存后再运行

> 本程序会优先读当前进程环境变量；若 Codex 尚未重启，也会回退读取 Windows“用户环境变量”。不会打印 API Key。

## 安装

在本目录打开新的 PowerShell：

```powershell
$python = "C:\Users\liu\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
& $python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

先做安全体检（不会显示密钥）：

```powershell
.\.venv\Scripts\python.exe -m scripts.doctor
```

## 建立索引

索引时必须关闭 Web 服务；Qdrant Local 的数据目录不能被两个进程同时打开。

先用一个小样本验证解析、模型下载与 GPU/CPU 能力：

```powershell
.\.venv\Scripts\python.exe -m scripts.index_vault --limit 20
```

小样本确认后，重建全部支持资料的索引：

```powershell
.\.venv\Scripts\python.exe -m scripts.index_vault
```

支持 `.md`、`.pdf`、`.docx`、`.xlsx`、`.pptx`；默认排除 Obsidian、AI 工具和配置目录，跳过链接/重解析点、临时文件、超大文件。扫描版 PDF 会记为 `needs_ocr`，不会伪造文字。

若预检发现切片数超过 18,000，程序不会改写已有索引，而是生成报告并停止。这是 Qdrant Local 的单机安全边界；此时应切换为独立 Qdrant Server，而不是强行继续。

如果想在下载模型前先准确检查全部资料能解析出多少切片，可运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.index_vault --preflight
```

## 启动问答页面

正式 V1 服务（8000）沿用原入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后在浏览器打开 `http://127.0.0.1:8000`。

V2 内部试用服务（8010）使用：

```powershell
.\scripts\start_internal_trial.ps1
```

主试用页面：`http://127.0.0.1:8010/knowledge-os`；AI问答页面：`http://127.0.0.1:8010/ai`；批量验收工作台：`http://127.0.0.1:8010/batch`。停止服务使用 `scripts\stop_internal_trial.ps1`。启动前必须通过试用准备检查，且不得与索引任务同时运行。

批量验收工作台按“来源目录只读预览 → 批准进入 Root-002 Shadow → 自动生成结构化验收题 → 批量回归 → 异常清单”运行。浏览器选择文件夹上传后会自动批准进入 Shadow、生成验收题并批量回归；服务器路径仍需手动点击一次批准。批处理登记、上传会话和结果保存在 `data/shadow/batch_workflow`，不会自动写入正式知识库。

旧版 `/v2-trial` 仅作底层诊断备用入口，不作为日常提问入口。

`/api/health` 会对生成模型发送一个不含业务数据的轻量健康检查；实际提问时，仅将最终检索到的少量证据发送到内网模型接口。

## 可选 GPU 加速

当前隔离环境已验证 CPU 回退可用。若要对完整资料库进行更快的向量化，在网络条件允许时，按 PyTorch 官方 CUDA 13.2 源替换 CPU 版：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall torch --index-url https://download.pytorch.org/whl/cu132
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

预期最后一项为 True。该下载约 1.9GB；不需要单独安装完整 CUDA Toolkit。

## 已知边界

- Qdrant Local 仅限单进程：启动服务时只能用一个 worker；索引与服务不能同时运行。
- `BGE-M3` 和可选 `bge-reranker-v2-m3` 首次加载需要较多内存。程序采用小批量，重排模型加载失败时自动退回 RRF 排序，并在接口中提示。
- 不支持旧版 `.doc/.xls/.ppt`、RAR、图片与扫描件 OCR；这些会在索引报告中显式保留为后续处理项。
- 当前索引仍采用全量 staging 构建与发布，不做在线增量写入；这是为了避免 Qdrant Local 进程锁和部分写入风险。
- `knowledge-ui` 当前仍主要使用 Mock 数据；真实知识接入要等 V2 试用和业务验收稳定后再做。
