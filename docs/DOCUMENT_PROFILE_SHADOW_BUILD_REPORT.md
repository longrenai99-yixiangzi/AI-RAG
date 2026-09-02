# Document Profile Shadow Build Report

> 本报告基于 Shadow Qdrant 的 Chunk、Metadata、Governance Metadata 和文档结构生成 Document Profile。
> 不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. 构建范围

- Shadow Collection 点数：4747。
- Profile 生成数量：498。
- Profile 输出：D:\AI智能体\AI设计管理RAG-V1\data\shadow\full_corpus_qdrant\document_profiles.jsonl。
- 生成来源：文件名、路径、标题/章节、已有 Metadata、Governance Metadata 和规则化关键词。

## 2. Profile 字段

每个 Profile 包含：document_id、document_name、document_role、authority_level、scope、contains_topics、not_for、related_documents、profile_source、profile_confidence、profile_review_status。

## 3. 统计结果

| 指标 | 结果 |
|---|---:|
| Profile 数量 | 498 |
| NEEDS_REVIEW 数量 | 103 |
| 低置信度文件（<0.8） | 103 |
| 包含 scope 的文件 | 498 |
| 包含 contains_topics 的文件 | 498 |
| related_documents 关系数 | 738 |

- document_role 分布：{"正式制度": 40, "其他": 53, "标准模板": 71, "项目案例": 240, "管理指南": 55, "汇报材料": 16, "培训材料": 23}。
- authority_level 分布：{"L1": 40, "UNKNOWN": 53, "L3": 71, "L4": 240, "L2": 55, "L6": 16, "L5": 23}。
- scope.project_stage 分布：{"未识别": 329, "设计策划": 76, "施工图设计": 22, "方案设计": 20, "投标": 32, "初步设计": 16, "深化设计": 3}。

## 4. 100题 Gold expected_files 对账

| 指标 | 数量 | 比例 |
|---|---:|---:|
| Gold Questions | 100 | 100.00% |
| expected_files 可找到 Profile | 100 | 100.00% |
| expected_document_role 匹配 | 56 | 56.00% |
| expected_authority_level 匹配 | 56 | 56.00% |
| expected_usage_scene 匹配 | 56 | 56.00% |

该对账只验证 Profile 是否覆盖 Gold 指向的文件和治理字段，不代表文件内容已经被人工确认。

## 5. 低置信度文件

| 文件 | 角色 | 权威等级 | 置信度 | 状态 |
|---|---|---|---:|---|
| 中建三局体系建设及执行评价.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理评价.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 中建三局报批报建指标库.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 知识变更日志.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计招采.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 施工图审核要点.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 之寓 人才公寓-设计管理策划.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 附件3：关于设计与技术支持中心建设的改进建议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| purpose.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 二公司报批报建指标库.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理标签词典.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 二公司体系建设及执行自评.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理成果总结.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 产品线设计指标库（厂房）.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 二公司设计与技术支持中心工作报告0227.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 司属单位设计与技术中心建设督导报告.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 2026年4月.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理评审.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 二公司设计管理部.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 太原716涉密策划及概预算评审纪要.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 无锡山姆设计方案比选.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 分支机构设计与技术支持中心组织建设情况一览表.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 中建三局第二建设公司设计与技术支持中心建设方案.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 管理工具书.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 设计价值创造.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 设计院台账.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 常熟药机场设计方案比选.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 2025年设计与技术支持中心建设情况一览表.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 产品线价值创造.md | 标准模板 | L3 | 0.760 | NEEDS_REVIEW |
| 设计与技术支持中心建设意见的报告.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 产品线设计指标库（学校）.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 公司层面的设计资源维护 汇总表.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 附件4：关于设计与技术支持中心建设意见的报告.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 与公司合作设计院情况统计表1.21.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 华南公司.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 附件2：司属单位督导反馈存在问题.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理知识体系.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 相关方沟通机制.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| log.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计与技术支持中心.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| EPC工程报批报建工作指引.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计与技术支持中心优化后的组织建设情况.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计指标库.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 光谷实验中学-设计管理策划.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 平鲁风电方案比选分析.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 设计质量.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 设计评估报告范文本20240514.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 2020苏州战略合作框架协议 吴中区.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 修文独立储能电站-设计管理策划.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 设计策划评审.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 设计支持.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 2026-08-15_知识库接入基线.md | 标准模板 | L3 | 0.760 | NEEDS_REVIEW |
| 苏州吴中区政府战略协议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 江苏纬信工程咨询战略协议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 2026-08-15_外部资料导入报告.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 设计院分类统计及对接分工.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 华设设计集团战略协议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 2026-08-15_外部资料导入待审核.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 设计管理体系.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 悉地国际设计顾问（深圳）有限公司战略协议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计策划.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| index.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 战略合作协议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 产品线设计指标库（医疗）.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理服务台账.md | 标准模板 | L3 | 0.760 | NEEDS_REVIEW |
| 限额设计.md | 标准模板 | L3 | 0.760 | NEEDS_REVIEW |
| entity.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 报批报建.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 控概与概算.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 方案比选库.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 设计管理体系文件汇编.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 葛店经开区富家山生态陵园策划及概预算评审纪要.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| overview.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 光谷网球中心策划及概预算评审纪要.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 附件1：司属单位设计与技术支持中心组织建设情况一览表.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 方案比选.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 报批报建指标库.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 四大中心建设情况报告框架.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 孝感奥体文旅、光谷实验中学、武汉轻工大学公寓策划及概预算评审纪要.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 中建三局.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 公司合作设计院情况报告1.21.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 公司投资业务合作资源储备库.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 产品线设计指标库（住宅）.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 光谷能源站方案比选.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 公司设计服务管理台帐2026.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计管理结果应用.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 中建三局第二建设公司设计支持管理细则.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 复杂专项与地标.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 审计巡查与合规.md | 正式制度 | L1 | 0.760 | NEEDS_REVIEW |
| 关于督导华中公司设计与技术支持中心建设情况小结.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 设计风险.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 中建三局二公司设计与技术中心建设督导报告20251113.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 支持中心建设的改进建议.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 产品线设计指标库（场馆）.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 预警提示单.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 应城市东马坊园区、武汉星谷科创中心、修文工业园储能电站策划及概预算评审纪要.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 设计评估.md | 其他 | UNKNOWN | 0.080 | NEEDS_REVIEW |
| 新洲星谷科创中心-设计管理策划.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |
| 设计阶段报批报建.md | 管理指南 | L2 | 0.760 | NEEDS_REVIEW |
| 平鲁风电报批报建.md | 项目案例 | L4 | 0.760 | NEEDS_REVIEW |

## 6. 质量边界与后续

1. 当前 Profile 为规则化 Shadow Profile，不调用 LLM，不自动写入正式索引。
2. contains_topics 是可解释关键词候选，不是经过语义模型确认的完整主题摘要。
3. not_for 仅来自明确限制语句或确定性角色边界；低置信度限制不应直接作为硬过滤条件。
4. related_documents 当前只建立有共同项目范围证据的 related_to 关系，不自动推断 supersedes。
5. 下一步应使用 Profile 做 Document-level Retrieval，并与 Chunk-only Retrieval 对比 Expected File Hit Rate。

## 7. TASK-014E 边界确认

| 验收项 | 结果 |
|---|---|
| 真实知识库 Shadow Document Profile | 已生成 |
| Profile 字段完整 | 已生成 |
| 角色和 authority 分布统计 | 已完成 |
| NEEDS_REVIEW 和低置信度统计 | 已完成 |
| 100题 expected_files 对账 | 已完成 |
| 调用 LLM | 否 |
| 修改正式 Retriever | 否 |
| 修改 8000 服务 | 否 |
| 修改正式 Qdrant | 否 |

**TASK-014E：Document Profile Shadow Build 完成。**
