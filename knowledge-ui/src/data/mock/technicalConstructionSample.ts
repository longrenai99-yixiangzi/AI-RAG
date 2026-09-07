/**
 * 试验用的完整数据链：技术管理 → 施工组织设计 → 总体施组。
 * 其余节点仍是框架占位，不得将本文件的 Mock 内容视为已入库企业资料。
 */
import type { KnowledgeNode } from '../../types/knowledge'
import type { KnowledgeCardRecord, KnowledgeCaseRecord, KnowledgeNodeSample, KnowledgeSourceRecord } from './knowledgeContent'
export const technicalConstructionNodeId = 'technical-construction-1'

export const technicalConstructionSources: KnowledgeSourceRecord[] = [
  { id: 'tos-01', name: '施工组织设计编制管理指引（Mock）', type: '制度', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/制度', location: '第 2 章 / 第 4—8 条', excerpt: '总体施工组织设计应在项目实施策划阶段完成编制、评审与动态更新。' },
  { id: 'tos-02', name: '总体施工组织设计编制模板（Mock）', type: '模板', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/模板', location: '目录 / 表单 1—9', excerpt: '模板包括工程概况、施工部署、进度计划、资源配置、总平面布置与风险控制。' },
  { id: 'tos-03', name: '总体施工组织设计审查要点清单（Mock）', type: '清单', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/清单', location: '审查项 01—24', excerpt: '审查施工部署与合同工期、资源能力、现场条件和重大风险是否匹配。' },
  { id: 'tos-04', name: '施工总进度计划编制要点（Mock）', type: '指南', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/进度指南', location: '第 3 节 / 关键线路', excerpt: '进度计划应明确里程碑、关键线路、资源约束及纠偏机制。' },
  { id: 'tos-05', name: '项目施工部署与现场总平面布置指引（Mock）', type: '指南', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/总平面', location: '第 2 节 / 场地组织', excerpt: '现场总平面应统筹运输组织、临建设施、材料堆场、机械布置与消防通道。' },
  { id: 'tos-06', name: '项目资源配置计划表（Mock）', type: '模板', authority: '正式原文', sourcePath: 'Mock/技术管理/施工组织设计/资源模板', location: '人工 / 材料 / 机械表', excerpt: '资源计划应按阶段匹配劳动力、主要材料、周转料具和机械设备需求。' },
  { id: 'tos-07', name: '产业园项目总体施组编制案例（Mock）', type: '案例', authority: '参考', sourcePath: 'Mock/技术管理/施工组织设计/案例', location: '第 3 章 / 施工部署', excerpt: '案例采用分区、分段、穿插施工组织，并以关键线路控制工期风险。' },
  { id: 'tos-08', name: '总体施组风险与动态纠偏记录（Mock）', type: '计划', authority: '参考', sourcePath: 'Mock/技术管理/施工组织设计/风险台账', location: '风险台账 / R-01—R-12', excerpt: '对资源供应、雨季施工、交叉作业和场地转换设置预警及纠偏责任人。' },
]

export const technicalConstructionCards: KnowledgeCardRecord[] = [
  { id: 'toc-01', title: '总体施组的编制边界', summary: '明确总体施组要解决的项目级组织问题，以及与专项方案、进度计划的衔接关系。', keyPoints: ['以合同、图纸、现场条件为输入', '覆盖部署、进度、资源、总平面和风险', '专项方案不得替代总体施组'], sourceIds: ['tos-01', 'tos-02'] },
  { id: 'toc-02', title: '施工部署与组织原则', summary: '用分区、分段、流水、穿插等方式把工期目标转化为可执行的施工组织。', keyPoints: ['确定施工区段和施工顺序', '识别关键线路与控制节点', '明确总包与专业分包界面'], sourceIds: ['tos-01', 'tos-04', 'tos-07'] },
  { id: 'toc-03', title: '资源与总平面统筹', summary: '将人、材、机、临建和运输组织放在同一张项目级资源配置图中校核。', keyPoints: ['资源计划按阶段配置', '总平面满足安全与消防要求', '场地转换应有时序安排'], sourceIds: ['tos-05', 'tos-06'] },
  { id: 'toc-04', title: '评审、实施与动态纠偏', summary: '总体施组经评审后作为组织实施基线，并在条件变化时保留动态调整依据。', keyPoints: ['按审查清单逐项校核', '里程碑偏差触发纠偏', '风险台账明确责任人与时限'], sourceIds: ['tos-03', 'tos-08'] },
]

export const technicalConstructionCases: KnowledgeCaseRecord[] = [
  { id: 'toc-case-01', name: '产业园多单体分区穿插案例（Mock）', scenario: '多单体同步开工、场地狭窄，需统筹塔吊、运输与材料堆场。', outcome: '以分区流水和总平面分期转换组织施工，减少交叉干扰。', sourceIds: ['tos-07', 'tos-05'] },
  { id: 'toc-case-02', name: '公共建筑工期压缩案例（Mock）', scenario: '合同工期紧，机电、装饰与土建需要穿插施工。', outcome: '通过关键线路复核和资源峰值平衡形成纠偏方案。', sourceIds: ['tos-04', 'tos-08'] },
  { id: 'toc-case-03', name: '复杂场地临建转换案例（Mock）', scenario: '施工阶段变化导致临建、道路和堆场需多次调整。', outcome: '在总体施组中设置场地转换节点和责任清单。', sourceIds: ['tos-05', 'tos-03'] },
]

export const technicalConstructionSpace = {
  nodeId: technicalConstructionNodeId,
  overview: '总体施组是项目级施工组织基线，用于把工期、资源、场地与风险控制要求组织成可执行方案。以下内容均为真实对象关系的 Mock 样板，待后续替换为经审核的企业知识数据。',
  managementPoints: ['编制前核实合同边界、现场条件、图纸成熟度与资源约束。', '评审重点是施工部署、关键线路、资源峰值、总平面和重大风险的一致性。', '实施期间发生工期、场地、资源或重大方案变化时，应形成动态调整记录。'],
}

/** 主系统使用的唯一对象图；卡片、来源、案例和路由均从此处关联。 */
export const technicalConstructionGraph: { domain: KnowledgeNode; category: KnowledgeNode; node: KnowledgeNode } = {
  domain: {
    id: 'domain-technical', name: '技术管理', type: 'domain',
    description: '围绕深化设计、施工组织、专项方案和专业技术协同形成的技术管理体系。',
    childrenCount: 6, knowledgeCount: technicalConstructionCards.length, sourceCount: technicalConstructionSources.length, coverage: 76,
    tags: ['技术管理', '一级板块'], relatedTopics: ['epc'], updatedAt: '2026-08-27',
  },
  category: {
    id: 'technical-construction', parentId: 'domain-technical', name: '施工组织设计', type: 'category',
    description: '覆盖总体施组、工序组织和资源配置；当前仅“总体施组”完成数据对象化。',
    childrenCount: 3, knowledgeCount: technicalConstructionCards.length, sourceCount: technicalConstructionSources.length, coverage: 83,
    tags: ['技术管理', '施工组织设计'], relatedTopics: ['epc'], updatedAt: '2026-08-27',
  },
  node: {
    id: technicalConstructionNodeId, parentId: 'technical-construction', name: '总体施组', type: 'knowledge',
    description: technicalConstructionSpace.overview,
    childrenCount: 0, knowledgeCount: technicalConstructionCards.length, sourceCount: technicalConstructionSources.length, coverage: 100,
    tags: ['技术管理', '施工组织设计', '总体施组'], relatedTopics: ['epc'], updatedAt: '2026-08-27',
  },
}
