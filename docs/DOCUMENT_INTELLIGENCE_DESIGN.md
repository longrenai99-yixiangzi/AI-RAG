# AI 设计管理知识库 V1.0 Document Intelligence Layer 设计

> 任务：TASK-014D Document Intelligence Layer 设计  
> 正式目录：D:\AI智能体\AI设计管理RAG-V1  
> 知识源：D:\设计管理（只读）  
> 状态：仅完成设计，不执行全量文档摘要，不修改正式 Retriever、8000 服务或 Qdrant

## 1. 目标与问题定义

TASK-014C 已经验证了文件级聚合、角色排序和 Evidence Diversity 的价值，但仍存在一个关键问题：

- 文档角色匹配有所提升；
- Expected File Hit Rate 仍然偏低；
- 同一角色下存在多个相似文件，检索结果缺少“这个文件具体解决什么问题”的理解；
- 仅依赖文件名、路径和 Chunk 分数，无法稳定区分适用范围、禁止用途和关联文件。

Document Intelligence Layer 的职责是建立“文档级理解层”，为每个文件形成结构化 Document Profile，再将 Profile 用于文件级召回、排序、Evidence Selection 和回答边界控制。

它不替代 Chunk Retrieval，也不直接生成最终答案。

    Document / Chunk / Metadata
            ↓
    Document Profile
            ↓
    Document-level Retrieval Enhancement
            ↓
    Evidence Ranking
            ↓
    Answer Engine

## 2. 设计边界

本阶段：

- 不修改 app/retriever.py；
- 不修改 app/answer.py；
- 不修改 /api/chat；
- 不修改正式 data\qdrant；
- 不执行全量 Document Summary 生成；
- 不调用 LLM 生成生产知识；
- 不把推断出的 Profile 直接视为正式制度事实。

Document Profile 初期可以在 Shadow 环境中派生和评估，成熟后再进入 Staging，经过审核才能发布到正式索引。

## 3. Document Profile Schema

### 3.1 核心字段

每个 Document 生成一个 Profile，粒度是 document_id，不是 Chunk。

    {
      "document_id": "uuid",
      "document_name": "中建三局EPC项目设计管理指南2023.06.md",
      "source_path": "D:\\设计管理\\...",
      "file_type": ".md",
      "sha256": "sha256",
      "profile_version": "document-profile.v1",
      "document_role": "管理指南",
      "authority_level": "L2",
      "scope": [],
      "contains_topics": [],
      "not_for": [],
      "related_documents": [],
      "profile_source": "rule|extractive|llm_draft|manual",
      "profile_confidence": 0.0,
      "profile_review_status": "NEEDS_REVIEW"
    }

### 3.2 document_name

文档显示名称，默认使用 file_name，不使用 Chunk 标题替代。

规则：

- 保留原始扩展名；
- 不删除版本号、日期和项目名称；
- 文件名相同但路径不同的文档必须通过 document_id 和 source_path 区分；
- 不把自动清洗后的标题写回源文件。

### 3.3 document_role

建议枚举：

| 角色 | 含义 | 典型材料 |
|---|---|---|
| 正式制度 | 具有正式约束或发布属性的制度性文件 | 制度、规定、管理办法、规则 |
| 管理指南 | 指导管理动作、流程、标准或方法的文件 | 指南、流程、手册、规范、标准 |
| 标准模板 | 用于填写、交付或检查的结构化模板 | 模板、任务书、表单、清单、登记 |
| 项目案例 | 描述具体项目实践、复盘、经验或成果的文件 | 项目案例、复盘、经验总结 |
| 培训材料 | 用于培训、授课、学习或考试的材料 | 课件、讲义、培训材料 |
| 汇报材料 | 用于述职、汇报、会议交流或通报的材料 | 述职、汇报、会议纪要、通报 |
| 其他 | 无法可靠归类 | 暂不强行归类 |

角色不是知识类型的简单别名。一个“模板”可能属于标准模板，也可能只是案例中的表格；必须结合路径、标题、正文和文档上下文判断。

### 3.4 authority_level

建议使用稳定的等级编码：

| 等级 | 含义 | 默认角色 |
|---|---|---|
| L1 | 正式制度或正式发布要求 | 正式制度 |
| L2 | 管理指南、流程、标准或规范性指导 | 管理指南 |
| L3 | 经认可的标准模板或交付模板 | 标准模板 |
| L4 | 项目实践、案例或复盘材料 | 项目案例 |
| L5 | 培训和学习参考材料 | 培训材料 |
| L6 | 汇报、述职、会议交流参考材料 | 汇报材料 |
| UNKNOWN | 证据不足 | 其他 |

authority_level 表示“作为回答依据的权威等级”，不是对文件内容真伪的法律或管理裁决。

### 3.5 scope

描述文档适用范围，使用结构化对象而不是一段不可检索的长摘要：

    {
      "board": ["设计管理"],
      "discipline": ["建筑", "结构"],
      "building_type": ["医院"],
      "project_stage": ["方案设计", "施工图设计"],
      "project_name": ["河北科技师范学院项目"],
      "organization": ["设计管理部"]
    }

来源优先级：

1. Front Matter 或人工确认；
2. 路径和文件名；
3. 标题、表头、章节；
4. 正文中的明确范围声明；
5. 规则推断。

无法确认的范围字段保持为空，不用“全公司”“全部项目”等宽泛词替代。

### 3.6 contains_topics

表示文档实际包含的主题，用于文件级召回和解释：

    [
      "设计评审",
      "设计变更",
      "专业接口",
      "EPC设计管理"
    ]

主题来源：

- 标题和 Heading Path；
- 表头、Sheet 名、幻灯片标题；
- 高频且有结构位置的关键词；
- 已确认的 Metadata；
- 后续才考虑 LLM 摘要补充。

contains_topics 不是把所有正文关键词全部塞入数组。应保留少量可解释主题，并记录主题来源和置信度。

### 3.7 not_for

明确文档不适用的场景，用于防止错误召回和错误回答：

    [
      "不作为正式制度条款",
      "不适用于非EPC项目",
      "不替代当前版本模板",
      "仅用于培训参考"
    ]

not_for 只能来自：

- 文档中的明确限制语句；
- 文档角色和权威等级的确定性约束；
- 人工治理规则。

不能因为模型或规则“不喜欢”某个文件，就自动生成负面限制。

### 3.8 related_documents

表示有依据的关联文档，建议结构如下：

    [
      {
        "document_id": "uuid",
        "relation": "template_for|guide_for|case_of|supersedes|related_to",
        "confidence": 0.82,
        "evidence": "来源文件中明确提及"
      }
    ]

关联关系必须区分：

- template_for：模板服务于某个流程或指南；
- guide_for：指南指导某类模板或项目工作；
- case_of：案例属于某项目、专业或方法；
- supersedes：有明确版本替代关系；
- related_to：仅有主题关联，不能推断强依赖。

没有证据时不自动建立 supersedes，避免把日期较新的文件误判为正式替代版本。

## 4. Document Summary 生成策略

### 4.1 阶段一：规则和抽取，不调用 LLM

第一阶段以可解释、可复核为原则，使用：

1. 文件夹路径；
2. 文件名；
3. Markdown/DOCX 标题；
4. PPTX 幻灯片标题；
5. XLSX Workbook、Sheet 和表头；
6. PDF 页标题和首段；
7. 正文中的范围、适用对象、限制语句；
8. 现有 Metadata 和 Governance Metadata。

输出：

- document_role；
- authority_level；
- scope；
- contains_topics；
- not_for；
- related_documents 的确定性关系。

规则结果必须带：

    profile_source
    profile_rule
    profile_confidence
    profile_review_status

### 4.2 文档结构摘要

不生成自由文本摘要，而先生成结构化摘要：

    {
      "title": "...",
      "heading_paths": ["...", "..."],
      "section_count": 12,
      "topic_candidates": ["..."],
      "location_map": [
        {
          "topic": "设计评审",
          "locations": [{"page": 3}, {"line_start": 42, "line_end": 60}]
        }
      ],
      "limitations": ["..."]
    }

结构化摘要的优点：

- 可以直接回链到 Citation；
- 可以比较文档之间的主题重叠；
- 可以发现文件名相似但内容范围不同的资料；
- 不会产生一段无法验证的“漂亮摘要”。

### 4.3 阶段二：人工审核草稿

当规则产生以下情况时进入 NEEDS_REVIEW：

- document_role 在其他或多个角色冲突；
- authority_level 无法确定；
- 文件同时包含制度、案例和培训内容；
- scope 出现多个项目或多个专业；
- not_for 由弱证据推断；
- 关联文档疑似版本替代但没有明确文本。

审核界面应支持：

- 接受；
- 修改；
- 清空；
- 标记冲突；
- 查看支持 Profile 的原始位置。

### 4.4 阶段三：未来 LLM 摘要草稿

LLM 只生成草稿，不直接发布：

    LLM Draft
      → Schema Validation
      → Evidence Span Validation
      → Conflict Detection
      → Human Review
      → Staging

LLM 生成内容必须引用原文位置；无法提供位置的字段不得进入正式 Profile。

## 5. Document 级检索增强方案

### 5.1 两阶段检索

当前主要以 Chunk 为候选单位。Document Intelligence Layer 增加文档级召回：

    Query
      ↓
    Document Profile Retrieval
      ↓
    Candidate Documents
      ↓
    Chunk Retrieval within documents
      ↓
    RRF / Reranker
      ↓
    Evidence Selection

文档级召回不是用文档摘要替换 Chunk，而是先缩小文件级候选范围，再在文件内部寻找可引用 Chunk。

### 5.2 Document Profile 检索字段

文档级索引可以使用：

- document_name；
- document_role；
- authority_level；
- scope；
- contains_topics；
- not_for；
- related_documents；
- 文档标题和章节路径。

每个字段应保留来源和置信度，支持解释：

    命中该文档的原因：
    document_role = 管理指南
    contains_topics 命中 = 设计评审
    scope 命中 = EPC
    authority_level = L2

### 5.3 文件级得分

建议的文件级得分：

    document_score =
        profile_topic_score
      + scope_match_score
      + document_role_score
      + authority_score
      + name_title_score
      + related_document_score
      - not_for_penalty
      - version_conflict_penalty

约束：

- not_for 只能在证据明确时产生软降权；
- 不因一个低置信度 not_for 直接删除文件；
- 文件级候选为空时必须回退全库 Chunk 检索；
- 文件级排序不能抹掉高相关 Chunk 的直接证据。

### 5.4 解决“角色正确但文件不对”

仅有 document_role=管理指南 仍可能命中很多文件。需要增加：

1. contains_topics 与问题主题的匹配；
2. scope 与项目、专业、阶段、业态的匹配；
3. 文件名和标题中的关键实体匹配；
4. 同文档多个 Chunk 的主题一致性；
5. Gold Question 的 expected_files 对文件级排序进行评估；
6. 版本和关联文档关系的消歧。

目标不是让文件 Profile 代替语义检索，而是让多个同角色文件能够按“是否解决当前问题”排序。

## 6. 与 Evidence Ranking 结合方式

### 6.1 输入输出关系

    Retriever Top-K Chunks
      + Document Profile
            ↓
    File-level Aggregation
            ↓
    Document Priority / Authority Ranking
            ↓
    Evidence Diversity
            ↓
    Evidence Bundle

Evidence Item 增加：

- document_score；
- document_name；
- document_role；
- authority_level；
- scope_match；
- topic_match；
- not_for_warning。

### 6.2 推荐融合顺序

    1. 按 document_id 聚合 Chunk
    2. 计算 document_score
    3. 应用 Intent 对应的角色和权威等级偏好
    4. 检查 scope、contains_topics 和 not_for
    5. 选择有限数量的文档
    6. 在文档内选择最能支持问题的 Chunk
    7. 执行 Evidence Diversity
    8. 分配 S1、S2… Citation

不建议先把所有 Chunk 混在一起排序，再事后猜测文档角色；这样会导致一个高频文档占满 Evidence。

### 6.3 按 Intent 的文件级偏好

| Intent | 首选文档角色 | 主要文件级字段 | 降权但不硬过滤 |
|---|---|---|---|
| POLICY_QUERY | 正式制度、管理指南 | authority_level、scope、contains_topics | 项目案例、培训、汇报 |
| CASE_QUERY | 项目案例 | project_name、building_type、scope、contains_topics | 无关制度、培训 |
| METHOD_QUERY | 管理指南、标准模板 | contains_topics、usage_scene、scope | 仅有经验描述的案例 |
| TEMPLATE_QUERY | 标准模板 | document_name、字段主题、related_documents | 案例表格、培训课件 |
| DISCIPLINE_QUERY | 专业指南、项目案例 | discipline、project_stage、contains_topics | 不相关专业材料 |

### 6.4 文件级和 Chunk 级冲突

如果文件级得分高但 Chunk 与问题无关：

- 不应直接把该文件作为 Evidence；
- 在文件内部继续进行 Chunk 相关性筛选；
- 如果没有直接支持问题的 Chunk，只保留为 CONTEXT_ONLY；
- 答案中不得把文件 Profile 当作事实依据。

如果 Chunk 相关性高但文件权威等级较低：

- 可以保留为 SUPPORTING；
- 对制度问题标注“参考材料，不等同于正式制度”；
- 不得因低权威材料的相关性高而自动升级其 authority_level。

## 7. 制度、模板、案例识别规则

### 7.1 制度文件

强信号：

- 制度、规定、规章、管理办法、管理规则、政策；
- 正式发布、适用范围、职责、审批、监督、责任、版本；
- 明确发布组织、发布日期或适用范围。

弱信号：

- 文中出现“制度”“要求”“管理”等词；
- 项目总结中讨论制度执行。

弱信号不能单独把文件识别为正式制度。

### 7.2 管理指南和流程文件

强信号：

- 指南、流程、手册、工作手册、标准、规范、方法与实务；
- 有步骤、输入、输出、职责、检查点或流程图；
- 内容面向一类项目、专业或管理场景。

注意：

- 指南不等同于正式制度；
- 流程文件的 authority_level 默认不高于 L2，除非有正式发布证据。

### 7.3 标准模板

强信号：

- 模板、范本、示范文本、任务书、表单、清单、登记；
- 明确字段、填写说明、提交要求或行列结构；
- XLSX 表头、DOCX 表格、Markdown 字段列表和固定格式。

注意：

- 案例中出现的表格不能自动标记为标准模板；
- 模板如果包含大量项目事实，应同时保留 scope 和 not_for；
- 模板版本必须单独识别，不能默认当前有效。

### 7.4 项目案例

强信号：

- 项目名称、项目所在地、项目阶段、客户或业态；
- 案例、复盘、经验、项目实践、创效、项目总结；
- 背景—措施—效果—经验等叙事结构。

注意：

- 项目文件可以包含方法和制度引用，但主角色仍按文档用途判断；
- 项目案例的做法不能直接写成企业统一要求；
- project_name 是案例文件级检索的关键字段。

### 7.5 培训和汇报材料

培训材料信号：

- 培训、课件、讲义、课程、题库、考试；
- 教学目标、课程目录、练习题、授课对象。

汇报材料信号：

- 述职、汇报、通报、会议纪要、交流会、年度总结、半年总结；
- 会议时间、汇报对象、工作回顾、阶段性成果。

这两类材料可以提供背景和经验，但默认不作为制度问题的最高权威依据。

## 8. 未来 LLM 生成接口设计

### 8.1 Profile 生成接口

未来可增加独立的 Profile Generator：

    DocumentProfileGenerator.generate(
        document_identity,
        structured_extract,
        existing_metadata,
        evidence_spans,
    ) -> DocumentProfileDraft

LLM 输入必须包括：

- 文档名称和路径；
- 结构化章节/页/Sheet 信息；
- 已有 Metadata；
- 关键原文片段及位置；
- 允许的枚举值和字段 Schema。

LLM 不接收“请自由总结”式开放任务，而应返回受约束的 JSON。

### 8.2 JSON Schema 约束

返回字段至少校验：

- 枚举值合法；
- 数组元素为字符串或规定对象；
- 每个 contains_topics 有对应证据位置；
- 每个 not_for 有明确限制语句；
- related_documents 关系类型合法；
- profile_confidence 在 0 到 1；
- profile_review_status 为 NEEDS_REVIEW、AUTO 或 MANUAL。

### 8.3 发布边界

    LLM Profile Draft
      → Schema Validation
      → Evidence Span Validation
      → Conflict Detection
      → Human Review
      → Staging Profile
      → Shadow Evaluation
      → Approved Index Payload

LLM 生成的 Profile 在人工审核前：

- 不能改变原文；
- 不能改变原始 Metadata；
- 不能提升 authority_level；
- 不能创建 supersedes 关系；
- 不能作为制度答案的唯一依据。

## 9. 实施阶段建议

### 阶段 A：结构化 Profile 抽取

- 为 498 个文档生成规则 Profile；
- 只读使用现有 Chunk、Metadata 和 Governance Metadata；
- 输出 Staging Profile JSON；
- 统计角色、权威等级、主题和范围覆盖率。

### 阶段 B：文件级 Gold

- 将 expected_files 与 Document Profile 对账；
- 为相似文件补充 scope、contains_topics 和 not_for；
- 增加“同角色不同文件”的专项问题；
- 重新评估 Document-level Recall 和 Expected File Hit Rate。

### 阶段 C：Shadow Document Retrieval

- 文档级候选召回；
- 文件内 Chunk 精排；
- 与现有 Chunk-only 检索对比；
- 保留无 Document Profile 的回退路径。

### 阶段 D：LLM Profile 草稿

- 只对高价值、低置信度或高混淆文件生成草稿；
- 先生成少量样本，人工审核后再扩大范围；
- 不执行全库自动发布。

## 10. 评估指标

Document Intelligence Layer 的第一阶段指标：

- Document Profile 完整率；
- document_role 识别覆盖率；
- authority_level 识别覆盖率；
- contains_topics 与 Gold Topic 的匹配率；
- scope 命中率；
- not_for 误用率；
- related_documents 关系准确率；
- Document-level Recall@1/@5；
- Expected File Hit Rate；
- Role Match Top-1/Top-5；
- 制度、模板、案例混淆率；
- Profile 引入后的 Evidence Citation 完整率；
- Profile 规则导致的零召回回退率。

任何 Profile 优化都必须同时观察 Expected File Hit Rate 和 Citation 质量，不能只看角色匹配率。

## 11. TASK-014D 边界确认

| 验收项 | 结果 |
|---|---|
| Document Profile Schema | 已设计 |
| Document Summary 生成策略 | 已设计 |
| Document 级检索增强方案 | 已设计 |
| 与 Evidence Ranking 结合方式 | 已设计 |
| 制度/模板/案例识别规则 | 已设计 |
| 未来 LLM 生成接口 | 已设计 |
| 执行全量生成 | 否 |
| 修改正式 Retriever | 否 |
| 修改 8000 服务 | 否 |
| 修改正式 Qdrant | 否 |

**TASK-014D：Document Intelligence Layer 设计完成。**
