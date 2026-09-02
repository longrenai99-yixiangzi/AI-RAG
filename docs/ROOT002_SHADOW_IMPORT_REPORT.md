# ROOT-002 Shadow Import & Pipeline Validation Report

> TASK-016C-2 只对 TASK-016C-1 批准范围运行。结果写入独立 Shadow 目录，不进入正式 Retriever、8000 服务或正式 Qdrant。

## 1. 执行边界

- Knowledge Root：`Root-002` — `D:\工作\二公司技术部`
- Shadow 目录：`D:\AI智能体\AI设计管理RAG-V1\data\shadow\root002_import`
- Shadow Collection：`root002_shadow_bge_m3`
- 未修改正式 Retriever、`app/main.py`、8000 服务和正式 `data\qdrant`。
- 未自动导入个人资料、临时文件、微信文件、缓存文件和未审核草稿。

## 2. Root-002 审批快照

| 指标 | 结果 |
|---|---:|
| 批准目录数 | 5 |
| 快照文件数 | 47 |
| 跳过文件/目录数 | 6 |
| PDF | 12 |
| DOCX | 20 |
| XLSX | 12 |
| PPTX | 3 |
| Markdown | 0 |

快照字段：`path`、`filename`、`size`、`mtime`、`mtime_ns`、`sha256`、审批优先级和批准子目录。
快照文件：`data\shadow\root002_import\approval_snapshot.jsonl`

### 批准目录

| 优先级 | 子目录 | 路径 |
|---|---|---|
| P0 | 设计管理 | `D:\工作\二公司技术部\2026\各类文件\设计管理` |
| P0 | 设计服务台账 | `D:\工作\二公司技术部\2026\设计服务台账` |
| P0 | 新洲星谷 | `D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷` |
| P0 | 应城智汇港 | `D:\工作\二公司技术部\2026\概算及策划评审\应城智汇港` |
| P1 | 设计复盘 | `D:\工作\二公司技术部\2026\设计复盘` |

## 3. Source Resolver

| 指标 | 结果 |
|---|---:|
| Root-002 SourceRecord | 47 |
| source_status | BODY_AVAILABLE |
| Root-002 文件存在数 | 47 |
| Root-002 文件类型 | {".pdf": 12, ".docx": 20, ".xlsx": 12, ".pptx": 3} |

SourceRecord：`data\shadow\root002_import\source_records.jsonl`
SourceLink：`data\shadow\root002_import\source_links.jsonl`

## 4. Document Pipeline

| 指标 | 结果 |
|---|---:|
| Document | 47 |
| SourceBlock | 1411 |
| Chunk | 1847 |
| Metadata 完整 Chunk | 1847 |
| Citation location 有效 Chunk | 1847 |
| Pipeline 状态 | `{"parsed": 47}` |
| Pipeline 错误 | 0 |

Metadata staging：`data\shadow\root002_import\pipeline_staging.jsonl`

## 5. Excel 特殊处理

每个 XLSX 记录 Workbook、Sheet 名称、有效 Sheet、表头、行列范围和 SourceBlock location；不执行复杂公式计算，也不回写源文件。

| Workbook | Sheet | 有效 | 表头 | 行范围 | 列数 | 来源位置 |
|---|---|---|---|---:|---:|---|
| `设计策划评审意见表(1).xlsx` | `Sheet1` | 是 | 设计策划及概算评审意见表、列2、列3、列4、列5、列6、列7、列8 | 1-33 | 8 | `{"sheet_name": "Sheet1", "row_start": 1, "row_end": 33, "column_count": 8, "header_row": 1}` |
| `设计策划评审意见表(1).xlsx` | `Sheet2` | 否 |  | --- | - | `{}` |
| `设计策划评审意见表(1).xlsx` | `Sheet3` | 否 |  | --- | - | `{}` |
| `价值创造清单统计表2026.4.1评审修改版.xlsx` | `价值创造 ` | 是 | 专业类别、价值创造策划点、优化前做法、列4、优化后做法、列6、收入对比（万元）、效益对比（万元）、责任人、参与人员、完成时限、落实情况、备注、列14、列15、列16 | 2-106 | 16 | `{"sheet_name": "价值创造 ", "row_start": 2, "row_end": 106, "column_count": 16, "header_row": 2}` |
| `价值创造清单统计表2026.4.1评审修改版.xlsx` | `蓝色项明细` | 是 | 设计价值创造点清单、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16 | 1-107 | 16 | `{"sheet_name": "蓝色项明细", "row_start": 1, "row_end": 107, "column_count": 16, "header_row": 1}` |
| `方案比选测算项总结.xlsx` | `方案比选` | 是 | 专业类别、价值创造策划点、优化前做法、列4、优化后做法、列6、收入对比（万元）、效益对比（万元）、责任人、参与人员、完成时限、落实情况、备注 | 2-70 | 13 | `{"sheet_name": "方案比选", "row_start": 2, "row_end": 70, "column_count": 13, "header_row": 2}` |
| `方案比选测算项总结.xlsx` | `方案比选 (2)` | 是 | 专业类别、价值创造策划点、优化前做法、列4、优化后做法、列6、收入对比（万元）、效益对比（万元）、责任人、参与人员、完成时限、落实情况、备注 | 2-70 | 13 | `{"sheet_name": "方案比选 (2)", "row_start": 2, "row_end": 70, "column_count": 13, "header_row": 2}` |
| `02：附表4、5：估算、概算、快速预算与概算.xlsx` | `估算（概算划分）` | 是 | 附表4、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16、列17、列18、列19、列20、列21、列22、列23、列24、列25、列26 | 1-94 | 26 | `{"sheet_name": "估算（概算划分）", "row_start": 1, "row_end": 94, "column_count": 26, "header_row": 1}` |
| `02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷20260401(1).xlsx` | `估算（概算划分） (2)` | 是 | 附表4、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16、列17、列18、列19、列20、列21、列22、列23、列24、列25、列26、列27、列28、列29、列30、列31 | 1-94 | 31 | `{"sheet_name": "估算（概算划分） (2)", "row_start": 1, "row_end": 94, "column_count": 31, "header_row": 1}` |
| `专业限额重划分表.xlsx` | `Sheet1` | 是 | 专业限额重划分、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15 | 1-22 | 15 | `{"sheet_name": "Sheet1", "row_start": 1, "row_end": 22, "column_count": 15, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `方案比选` | 是 | 星谷科创中心设计方案比选、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16 | 1-103 | 16 | `{"sheet_name": "方案比选", "row_start": 1, "row_end": 103, "column_count": 16, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `方案比选 (2)` | 是 | 星谷科创中心设计方案比选、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14 | 1-103 | 14 | `{"sheet_name": "方案比选 (2)", "row_start": 1, "row_end": 103, "column_count": 14, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `价值创造` | 是 | 设计价值创造清单、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13 | 1-86 | 13 | `{"sheet_name": "价值创造", "row_start": 1, "row_end": 86, "column_count": 13, "header_row": 1}` |
| `02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷202604020.xlsx` | `估算（概算划分）` | 是 | 附表4、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16、列17、列18、列19、列20、列21、列22、列23、列24、列25、列26、列27、列28、列29、列30、列31 | 1-94 | 31 | `{"sheet_name": "估算（概算划分）", "row_start": 1, "row_end": 94, "column_count": 31, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `方案比选` | 是 | 星谷科创中心设计方案比选、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14、列15、列16 | 1-103 | 16 | `{"sheet_name": "方案比选", "row_start": 1, "row_end": 103, "column_count": 16, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `价值创造` | 是 | 设计价值创造清单、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14 | 1-94 | 14 | `{"sheet_name": "价值创造", "row_start": 1, "row_end": 94, "column_count": 14, "header_row": 1}` |
| `方案比选与价值创造清单方案比选及价值创造.xlsx` | `方案比选 (2)` | 是 | 星谷科创中心设计方案比选、列2、列3、列4、列5、列6、列7、列8、列9、列10、列11、列12、列13、列14 | 1-103 | 14 | `{"sheet_name": "方案比选 (2)", "row_start": 1, "row_end": 103, "column_count": 14, "header_row": 1}` |
| `设计策划评审意见表(1).xlsx` | `Sheet1` | 是 | 设计策划及概算评审意见表、列2、列3、列4、列5、列6、列7、列8 | 1-37 | 8 | `{"sheet_name": "Sheet1", "row_start": 1, "row_end": 37, "column_count": 8, "header_row": 1}` |
| `设计策划评审意见表(1).xlsx` | `Sheet2` | 否 |  | --- | - | `{}` |
| `设计策划评审意见表(1).xlsx` | `Sheet3` | 否 |  | --- | - | `{}` |
| `公司复盘EPC项目管理台账.xlsx` | `Sheet3` | 是 | 2026年需进行设计管理复盘（当年主体施工图审查完成后三个月内）、列2、列3、列4 | 1-43 | 4 | `{"sheet_name": "Sheet3", "row_start": 1, "row_end": 43, "column_count": 4, "header_row": 1}` |
| `公司设计服务管理台帐2026.xlsx` | `技术服务2025年` | 是 | 公司2026年度专家服务管理台帐、列2、列3、列4、列5、列6、列7、列8、列9 | 1-5 | 9 | `{"sheet_name": "技术服务2025年", "row_start": 1, "row_end": 5, "column_count": 9, "header_row": 1}` |
| `公司设计服务管理台帐2026.xlsx` | `技术服务2024年 ` | 是 | 公司   2024  年度投标与技术服务管理台帐、列2、列3、列4、列5、列6、列7、列8、列9 | 1-113 | 9 | `{"sheet_name": "技术服务2024年 ", "row_start": 1, "row_end": 113, "column_count": 9, "header_row": 1}` |
| `公司设计服务管理台帐2026.xlsx` | `次数统计` | 是 | 序号、单位、服务次数 | 1-17 | 3 | `{"sheet_name": "次数统计", "row_start": 1, "row_end": 17, "column_count": 3, "header_row": 1}` |

## 6. Shadow Embedding 与 Qdrant

| 指标 | 结果 |
|---|---:|
| CUDA 可用 | `True` |
| Torch | `2.12.1+cu132` |
| CUDA Runtime | `13.2` |
| GPU | `NVIDIA GeForce RTX 4060 Laptop GPU` |
| BGE-M3 路径 | `D:\AI智能体\AI设计管理RAG-V1\models\bge-m3` |
| Embedding 数量 | 1847 |
| Embedding 失败数量 | 0 |
| Embedding 耗时（秒） | 83.997 |
| GPU 峰值显存 allocated（bytes） | 1243272704 |
| GPU 峰值显存 reserved（bytes） | 1367343104 |
| Shadow Collection 存在 | `True` |
| Shadow Qdrant 数量 | 1847 |
| Payload Root-002 完整数量 | 1847 |
| Citation location 完整数量 | 1847 |
| Chunk ID 应有/已入 Shadow | 1847/1847 |
| Chunk ID 缺失 | 0 |

Shadow Qdrant 路径：`data\shadow\root002_import\qdrant`

## 7. 重点业务问题验证

### BA-007：中建三局2026年设计与技术工作计划

- SourceRecord `src-root002-2c49a126266b23fab8f9f689`：`D:\工作\二公司技术部\2026\各类文件\设计管理\关于印发中建三局2026年设计与技术工作计划的通知.pdf`；source_status=`BODY_AVAILABLE`；sha256=`a56636b99d1f0a1d140c7c0bd468a76dc695ec16a88223d16cf66a644b576800`
- Pipeline：`关于印发中建三局2026年设计与技术工作计划的通知.pdf`；status=`parsed`；SourceBlock=7；Chunk=7

### BA-009：2026设计服务管理台账

- SourceRecord `src-root002-8c2b4234f62bde227284fbfb`：`D:\工作\二公司技术部\2026\设计服务台账\公司设计服务管理台帐2026.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`e681a825f7f14ef5cd0bb803d8be517593bdbf39fbfea1ebfa62e23d8df68cf5`
- Pipeline：`公司设计服务管理台帐2026.xlsx`；status=`parsed`；SourceBlock=3；Chunk=15
  - Sheet `技术服务2025年`：有效=True，行=1-5，列数=9
  - Sheet `技术服务2024年 `：有效=True，行=1-113，列数=9
  - Sheet `次数统计`：有效=True，行=1-17，列数=3

### BA-010：星谷价值创造清单

- SourceRecord `src-root002-fe8d7b7b0e92396b116b72f4`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\02：附表4、5：估算、概算、快速预算与概算.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`ee596748d41b0e88c1ef5fc5c85694e266243adfdcc819dc5cc27df7fba3cc07`
- SourceRecord `src-root002-f62d592fc7f4f0b7b7c1387e`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷20260401(1).xlsx`；source_status=`BODY_AVAILABLE`；sha256=`ac252208ca81883faf0a8fee580cd7ca1f3b28df17d706319a4d0acc4b6456ef`
- SourceRecord `src-root002-9d47d4b66400f386f85d6634`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\专业限额重划分表.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`2d1fa1fe94aad0cb7c3de09178c8771e67c5c8d7c229fd7a22de57c6954f6f29`
- SourceRecord `src-root002-6082f0aa0cf8b0cbe142d075`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\关于召开应城市东马坊园区智汇港等项目设计策划集中评审会的通知.docx`；source_status=`BODY_AVAILABLE`；sha256=`abaaf2762e98485829605fb36952c8c77ba6dcdcd632e3ce379a8bd68b089bd4`
- SourceRecord `src-root002-f906aef3b7cc02ad164d5b62`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\关于召开应城市东马坊园区智汇港等项目设计策划集中评审会的通知.pdf`；source_status=`BODY_AVAILABLE`；sha256=`88fd0785461e40864eb332d71fbc46c502e62c4c18163f055b06ff2c8029f8e6`
- SourceRecord `src-root002-5e9883b9e36bccb62424c216`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\方案比选与价值创造清单方案比选及价值创造.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`5eccc20223c3b09d2b95658dfa3eca8a0dfe980618a0f6b80aecc4ae11a5af5a`
- SourceRecord `src-root002-3d3e2b43155106cc455ed617`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\星谷科创项目设计管理策划+设计示范项目打造方案\02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷202604020.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`c548aa032164e85693cb94e792a07d51e15ee468ee240cf59bbf786b3fdd7abc`
- SourceRecord `src-root002-807b85cb258788d2381c6f5d`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\星谷科创项目设计管理策划+设计示范项目打造方案\方案比选与价值创造清单方案比选及价值创造.xlsx`；source_status=`BODY_AVAILABLE`；sha256=`65887e3456e0c8e70f6a8a9122d3aaeed8e40f5436cc7f303088349a2b89fef1`
- SourceRecord `src-root002-2744a7b566ff840046cad5ca`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\设计策划评审意见表(1).xlsx`；source_status=`BODY_AVAILABLE`；sha256=`33fba6475dc41f7159d6d02e8d0c222d6ab1f41c90d8a93882d69d6cdfdc458e`
- SourceRecord `src-root002-e6917c7f254b5492128cb2d7`：`D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷\设计管理策划书-星谷科创中心项目.docx`；source_status=`BODY_AVAILABLE`；sha256=`53559b6093d63b9c6ac45cf1d61ebf42eab4159db598d78b477871b62df2f1bd`
- Pipeline：`02：附表4、5：估算、概算、快速预算与概算.xlsx`；status=`parsed`；SourceBlock=1；Chunk=16
  - Sheet `估算（概算划分）`：有效=True，行=1-94，列数=26
- Pipeline：`02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷20260401(1).xlsx`；status=`parsed`；SourceBlock=1；Chunk=17
  - Sheet `估算（概算划分） (2)`：有效=True，行=1-94，列数=31
- Pipeline：`专业限额重划分表.xlsx`；status=`parsed`；SourceBlock=1；Chunk=3
  - Sheet `Sheet1`：有效=True，行=1-22，列数=15
- Pipeline：`关于召开应城市东马坊园区智汇港等项目设计策划集中评审会的通知.docx`；status=`parsed`；SourceBlock=8；Chunk=8
- Pipeline：`关于召开应城市东马坊园区智汇港等项目设计策划集中评审会的通知.pdf`；status=`parsed`；SourceBlock=2；Chunk=2
- Pipeline：`方案比选与价值创造清单方案比选及价值创造.xlsx`；status=`parsed`；SourceBlock=3；Chunk=47
  - Sheet `方案比选`：有效=True，行=1-103，列数=16
  - Sheet `方案比选 (2)`：有效=True，行=1-103，列数=14
  - Sheet `价值创造`：有效=True，行=1-86，列数=13
- Pipeline：`02：附表4、5：估算、概算、快速预算与概算对比、预算对比划分表-星谷202604020.xlsx`；status=`parsed`；SourceBlock=1；Chunk=17
  - Sheet `估算（概算划分）`：有效=True，行=1-94，列数=31
- Pipeline：`方案比选与价值创造清单方案比选及价值创造.xlsx`；status=`parsed`；SourceBlock=3；Chunk=48
  - Sheet `方案比选`：有效=True，行=1-103，列数=16
  - Sheet `价值创造`：有效=True，行=1-94，列数=14
  - Sheet `方案比选 (2)`：有效=True，行=1-103，列数=14
- Pipeline：`设计策划评审意见表(1).xlsx`；status=`parsed`；SourceBlock=1；Chunk=3
  - Sheet `Sheet1`：有效=True，行=1-37，列数=8
  - Sheet `Sheet2`：有效=False，行=None-None，列数=None
  - Sheet `Sheet3`：有效=False，行=None-None，列数=None
- Pipeline：`设计管理策划书-星谷科创中心项目.docx`；status=`parsed`；SourceBlock=30；Chunk=40

## 8. 异常与未导入项

- 跳过项总数：6。原因分布：`{"unsupported_extension": 6}`。
- Pipeline 错误：无。
- Embedding 错误：无。
- `.docm`、`.wps`、`.7z` 等不在本任务 Loader 支持范围内的文件只登记为跳过项，不自动转换、不自动导入。
- 未审核草稿、个人资料、临时文件、微信文件和缓存目录不进入 Shadow。

## 9. 结论

本次已按 Root-002 选择性批准范围完成只读快照、SourceRecord、Document Pipeline、Metadata staging、BGE-M3 Embedding 和独立 Shadow Qdrant 验证。该结果仅证明候选资料可被技术链路处理，不代表已进入正式知识库，也不代表业务内容已经审核通过。
