# AI设计管理知识库 · V0.2

这是一个本地运行、对 `D:\设计管理` 只读的 RAG 问答程序。

V0.2 在不更换 V0.1 RAG 底座的前提下增加知识治理和检索诊断：

```
只读解析资料 → 章节/页码级切片 → BGE-M3 向量检索 + BM25 → RRF 融合
→ 可选重排 → 内网 DeepSeek 生成答案 → 来源引用校验
```

问题分析和 Metadata 软过滤位于混合检索之前；过滤没有候选时自动回退全库，避免错误标签造成零召回。

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

每次索引报告还会记录 `new`、`modified`、`unchanged`、`deleted` 四类文件状态。V0.2 仍保留全量 staging 重建和发布前校验，状态检测用于报告和 V0.3 增量写入准备。

Metadata 规则位于 `config/metadata_rules.yaml`，由路径、文件名、标题和正文关键词生成；缺失 Metadata 不会阻止索引。结果会同时写入 SQLite 的 Document 和 Chunk。

默认 OCR Provider 为 `disabled`。PDF 文字层不足时会明确标记 `needs_ocr`；配置 `RAG_OCR_PROVIDER=paddleocr` 后才启用可选 PaddleOCR 适配器。OCR 失败只影响该 PDF，不会让整批索引失败。

若预检发现切片数超过 18,000，程序不会改写已有索引，而是生成报告并停止。这是 Qdrant Local 的单机安全边界；此时应切换为独立 Qdrant Server，而不是强行继续。

如果想在下载模型前先准确检查全部资料能解析出多少切片，可运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.index_vault --preflight
```

## 启动问答页面

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后在浏览器打开 `http://127.0.0.1:8000`。

`/api/health` 会对生成模型发送一个不含业务数据的轻量健康检查；实际提问时，仅将最终检索到的少量证据发送到内网模型接口。

页面和 `/api/chat` 返回中会显示当前问题的意图、Metadata 过滤、Dense/BM25 命中数、RRF 后结果、重排是否启用和过滤回退状态。

## 受控知识生长

当问题没有召回、引用校验失败或回答明确表示证据不足时，系统会：

1. 将问题、意图、检索数量和回答状态写入 SQLite；
2. 用规则归一化相同主题，累计重复问题频次；
3. 在 `data/growth/candidates/` 生成待审核候选草稿和当前证据清单；
4. 通过页面“知识生长”查看、审核中标记和解决标记。

候选草稿带有 `formal_write: forbidden`，系统不会自动改写 `D:\设计管理` 或正式知识。正式知识写回仍需人工审核和明确目标。

“知识管理”页面通过 `/api/documents` 只读展示索引文件、解析/索引状态、OCR状态和主要 Metadata；它不提供源文件移动、删除或改写操作。

## 检索质量评估

Golden Questions 位于 `tests/golden_questions.yaml`，只评价可验证的文件命中、关键词和 Metadata，不使用 LLM-as-Judge：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

报告写入 `data/reports/`，包含 Recall@5、Recall@10、Metadata Filter 影响和重排前后结果。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

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
- 不支持旧版 `.doc/.xls/.ppt`、RAR 与图片；扫描件会进入 OCR 待处理统计，不会伪造文字。
- V0.2 只完成增量状态检测，不改变 Qdrant Local 的全量 staging 发布策略；真正的在线增量写入仍需在 V0.3 处理进程锁、删除和回滚边界。
- Metadata 是检索辅助信号，不是事实证明；事实仍必须以可定位来源和引用校验为准。
