# Metadata 分类规则优化验证报告

> 任务：TASK-006.5 Metadata 分类规则优化验证  
> 项目目录：`D:\AI智能体\AI设计管理RAG-V1`  
> 知识源：`D:\设计管理`（只读）  
> 抽样日期：2026-08-22  
> 状态：规则已优化，未接入正式 indexer

## 1. 执行边界与统计口径

本次只对 Metadata 分类器和 YAML 规则进行旁路验证：

- 未接入正式 `app/indexer.py`；
- 未写入 Qdrant；
- 未改变 Document Loader、Chunker 或正式运行链路；
- 未修改 `D:\设计管理`；
- 未生成 Embedding。

### 1.1 抽样方法

| 项目 | 口径 |
|---|---|
| 候选集 | `D:\设计管理` 经现有只读扫描器筛出的 498 个支持文件 |
| 抽样数 | 50 |
| 随机种子 | 20260822 |
| 抽样方式 | `random.Random(20260822).sample(..., 50)` |

该种子固定后，后续可复用同一批样本进行规则回归。

### 1.2 重要限制

当前没有人工标注的 Gold Metadata，因此本报告中的“自动识别率”定义为字段非空文件数 / 抽样文件数。它是覆盖率指标，不是真实准确率；疑似冲突不能直接判定为错误。

## 2. 优化前基线

优化前使用原有规则，对同一随机样本得到：

| 指标 | 识别数 | 识别率 |
|---|---:|---:|
| `board` | 37/50 | 74% |
| `knowledge_type` | 31/50 | 62% |
| `discipline` | 16/50 | 32% |
| `NEEDS_REVIEW` | 49/50 | 98% |
| `AUTO` | 1/50 | 2% |

优化前的主要问题：

1. 没有 Obsidian Front Matter 证据源；
2. 正文泛关键词可以直接产生企业分类，误分类风险高；
3. `培训通知` 可能优先命中“通知/会议资料”；
4. `工作总结` 等文件名缺少明确知识类型规则；
5. 路径和文件名冲突时缺少字段级优先级。

## 3. 本次规则优化

修改文件：

```text
app/ingestion/metadata/rules.yaml
```

### 3.1 证据优先级

| 字段 | 优先级 |
|---|---|
| `board` | `front_matter` → `path` → `file_name` → `title` → `headers` |
| `knowledge_type` | `front_matter` → `file_name` → `title` → `path` → `headers` |
| `discipline` | `front_matter` → `file_name` → `title` → `path` → `headers` |

调整理由：Front Matter 是用户显式维护的信息；board 更依赖组织/目录归属；knowledge_type 和 discipline 的文件名、标题通常比宽泛父目录更具体；正文泛关键词不再作为企业分类兜底。

### 3.2 路径规则

新增/加强了以下路径语义词：

- board：设计支持、报批报建、方案比选、设计任务书、设计策划、设计价值创造；
- knowledge_type：制度、案例、经验总结、成果总结、工作总结、年度总结、培训、会议、模板；
- discipline：建筑、结构、机电、BIM、EPC 及明确专业词。

路径规则只使用明确目录语义，不把项目业态名称直接当作专业分类。

### 3.3 文件名规则

新增/加强了：

- 工作总结、年度总结 → 案例候选；
- 设计任务书、设计策划、指南、手册 → 方法候选；
- 模板、范本、示范文本 → 模板候选；
- 培训、课件、题库、考试 → 培训资料候选；
- 会议、纪要 → 会议资料候选。

“通知”不再单独归为会议资料，以避免“培训班通知”覆盖培训资料判断。

### 3.4 标题和表头规则

规则配置保留 `title` 和 `headers` 证据来源，并按低于路径/文件名的置信度处理：

```text
title：0.82
headers：0.76
```

标题或表头能够明确分类时可以识别；低于自动通过阈值时仍为 `NEEDS_REVIEW`。

### 3.5 Obsidian Front Matter 支持

`classifier.py` 新增 `front_matter` 输入；Markdown Loader 已提供解析后的 front matter，旁路 Pipeline 会自动传入。

| 目标字段 | 支持键 |
|---|---|
| `board` | `board`、`板块`、`board_name`、`tags` |
| `knowledge_type` | `knowledge_type`、`knowledge-type`、`knowledgeType`、`知识类型`、`tags` |
| `discipline` | `discipline`、`专业`、`discipline_name`、`tags` |

显式 Front Matter 命中时，`metadata_source=front_matter`、`metadata_confidence=1.0`。未知或缺失字段不强行填充。

## 4. 优化后同样本结果

对同一随机种子、同一 50 个文件复测：

| 指标 | 优化前 | 优化后 | 变化 |
|---|---:|---:|---:|
| `board` 自动识别率 | 74% | 76% | +2 个百分点 |
| `knowledge_type` 自动识别率 | 62% | 66% | +4 个百分点 |
| `discipline` 自动识别率 | 32% | 2% | -30 个百分点 |
| `NEEDS_REVIEW` 比例 | 98% | 98% | 不变 |
| `AUTO` 比例 | 2% | 2% | 不变 |

### 4.1 如何解释结果

- board、knowledge_type 有小幅覆盖提升；
- discipline 的非空率明显下降，原因是移除了正文泛关键词匹配，改为只接受 Front Matter、路径、文件名、标题和表头的明确证据；
- 这不是“分类能力退化”的直接证据，而是从高风险覆盖转向保守精度；
- 当前没有 Gold 标签，不能证明 discipline 优化后的真实准确率；
- 98% 的 NEEDS_REVIEW 说明企业分类治理仍需要人工审核或补充标注，不能直接把自动标签作为硬过滤条件。

## 5. 疑似错误分类与待人工核验案例

以下是规则冲突或证据不足案例，均标记为 `[待人工核验]`，不把它们伪装成已确认错误：

| 案例模式 | 当前结果 | 风险 |
|---|---|---|
| `raw\设计管理成果总结\管理工具书\建设标准参考手册\医疗产品线建设标准.md` | `knowledge_type=案例`，来源为 path | “成果总结”目录与“标准/手册”文件语义冲突，应人工确定案例或方法 |
| `raw\设计支持\方案比选\...方案比选.md` | `knowledge_type=案例`，来源为 file_name | 方案比选可能是案例，也可能是方法材料，当前无 Gold 证据 |
| `raw\设计支持\报批报建\...报批报建...md` | board 可识别，knowledge_type/discipline 为空 | 分类证据不足，不应强行补成制度或专业 |
| `raw\设计管理体系\培训与能力建设\...培训班的通知.pdf` | `knowledge_type=培训资料` | 已避免旧规则把“通知”优先归为会议资料，但仍建议人工抽查 |
| `raw\工作总结\2024年年度总结.md` | `knowledge_type=案例` | 规则已从正文弱命中改为文件名强命中，仍需确认年度总结是否纳入案例 |
| 大量项目文件只有项目名/业态名 | `discipline` 为空 | 不能把医院、学校、住宅等 building type 直接当作建筑/结构/机电专业 |

## 6. 验证测试

新增/更新测试覆盖：

- 自动分类；
- 未知分类；
- 低置信度分类；
- Front Matter 优先级；
- Metadata 缺失；
- Schema 校验；
- Staging Pipeline Metadata 快照。

最终测试结果：

```text
完整项目测试集：48 passed
```

## 7. 后续建议

1. 建立人工 Gold Metadata 集，至少覆盖 board、knowledge_type、discipline 各类真实样本。
2. 对“成果总结/手册/标准”“培训通知/会议资料”等冲突模式建立审核标签。
3. 不要为了提高非空率恢复正文泛关键词硬分类。
4. discipline 需要更细的专业目录或人工标注，不能用业态名称替代专业。
5. 规则稳定后，再把分类过滤接入 Retriever，并保留无结果全库回退。

## 8. TASK-006.5 验收结论

| 验收项 | 结果 |
|---|---|
| 随机抽取 50 个真实文件 | 已完成，固定种子 20260822 |
| board 自动识别率统计 | 已完成 |
| knowledge_type 自动识别率统计 | 已完成 |
| discipline 自动识别率统计 | 已完成 |
| NEEDS_REVIEW 比例统计 | 已完成 |
| 疑似错误分类案例 | 已列出并标记待人工核验 |
| 路径规则优化 | 已完成 |
| 文件名规则优化 | 已完成 |
| 标题/表头规则 | 已完成 |
| Obsidian Front Matter 支持 | 已完成 |
| 未接入正式 indexer | 是 |
| 未写入 Qdrant | 是 |
| 未改变 Document Engine Loader | 是 |
| 未修改 `D:\设计管理` | 是 |

**TASK-006.5：完成。**
