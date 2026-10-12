# AI设计管理知识库 · 本地受控运行

这是一个本地运行的设计管理知识库/RAG应用。开发和最新成果分支为 `rag-v1-refactor`；公开仓库保存通用源码、合成测试、操作手册和脱敏成果状态。业务原件、摘录、知识卡正文、模型、向量、运行日志及Owner逐题复核保留受控本机。

## 当前成果入口

- [当前发布与验收状态](docs/CURRENT_RELEASE_STATE.md)
- [NEW-01～12及部署任务台账](docs/NEXT_WORK_STATUS.md)
- [逐步操作指导手册](docs/KNOWLEDGE_BASE_OPERATIONS_HANDBOOK.md)
- [本轮成果与验证范围](docs/COMPLETED_RESULTS.md)
- [本地启动、引用、反馈及恢复说明](docs/LOCAL_OPERATION_GUIDE.md)
- [公共仓库数据政策](docs/PUBLIC_REPOSITORY_DATA_POLICY.md)

截至2026-10-12，正式8000采用已获准的C包 `2cd04d6c`；最新X包 `2a9e3c62` 在8022试用，尚未采用为正式版本。源码包括既有通用功能、W版回答覆盖修复及X版受控自生长候选工作台；上传代码不切换正式服务。

已实现文件/正文分开搜索、项目资料查阅、年度与期间完整记录、Word正文与表格修复、问题对象及答案覆盖检查、制度版本区分、历史评估记录查阅，以及任务书草稿、评估缺项交接和方案比选准备。具体边界见[成果总表](docs/COMPLETED_RESULTS.md)。

此前18项检查的后续处理见[W版说明](docs/SHARED_JUDGMENT_REPAIR_20261012.md)。最新X版公开回归286项、本机回归498项、在线21项、实际浏览器7项及收尾21项通过，详见[受控自生长第一批说明](docs/CONTROLLED_GROWTH_20261012.md)。候选不自动变成知识，两套回归也不相加或换算全库正确率；业务验收、自然使用观察及独立外部备份继续。

## 公开源码与本机系统的关系

本机正式服务来自具体获准的私有固定包；公开源码不能自动重建其业务数据。私有封包装配的通用实现位于[deployment/private_package](deployment/private_package/README.md)。旧V1入口和底部基础索引命令属于源码开发流程，不能替代当前本机已部署包的批准启动入口。

当前基础检索闭环为：

```
只读解析资料 → 章节/页码级切片 → BGE-M3 向量检索 + BM25 → RRF 融合
→ 可选重排 → 内网 DeepSeek 生成答案 → 来源引用校验
```

原始知识来源保持只读；运行数据写入受控运行目录。公开副本的私有数据装配步骤见[装配说明](docs/PRIVATE_DATA_ASSEMBLY.md)。

## 先决条件

- Windows 11
- 已有的 Python 3.12（本机已检测到）
- Windows 用户环境变量：`RAG_API_BASE_URL`、`RAG_CHAT_MODEL`、`RAG_API_KEY`
- 首次下载模型时可访问 Hugging Face；若网络受限，可先准备本地模型缓存后再运行

> 本程序会优先读当前进程环境变量；若 Codex 尚未重启，也会回退读取 Windows“用户环境变量”。不会打印 API Key。

## 安装

在本目录打开新的 PowerShell：

```powershell
$python = "[LOCAL_PATH_REDACTED]"
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

下面是旧V1源码开发入口，使用独立开发端口；已部署的正式8000应继续使用其获准固定包入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

然后在浏览器打开 `http://127.0.0.1:8011`。先确认端口没有被其他服务占用。

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
- 旧版 `.xls/.ppt`、RAR、图片与扫描件仍不支持；`.doc` 通过 LibreOffice 或 Windows Word COM 转换为临时 `.docx` 后解析，原始文件不改写。
- 当前索引仍采用全量 staging 构建与发布，不做在线增量写入；这是为了避免 Qdrant Local 进程锁和部分写入风险。
- `knowledge-ui` 当前仍主要使用 Mock 数据；真实知识接入要等 V2 试用和业务验收稳定后再做。
