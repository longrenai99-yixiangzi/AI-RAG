import type { KnowledgeGap } from '../../types/knowledge'

export const knowledgeGaps: KnowledgeGap[] = [
  { id: 'gap1', nodeId: 'design-deliverables-1', title: '医疗建筑审查', reason: '缺少典型项目案例', level: 'high' },
  { id: 'gap2', nodeId: 'design-deliverables-2', title: '幕墙专项设计', reason: '缺少审查规则', level: 'high' },
  { id: 'gap3', nodeId: 'science-digital-1', title: 'AI Agent', reason: '缺少企业内部应用案例', level: 'medium' },
  { id: 'gap4', nodeId: 'technical-detail-2', title: '深化设计交付', reason: '成果验收清单不完整', level: 'medium' },
  { id: 'gap5', nodeId: 'design-case-1', title: '医院项目案例', reason: '案例覆盖不足', level: 'medium' },
  { id: 'gap6', nodeId: 'science-outcome-1', title: '成果转化', reason: '复用路径待补充', level: 'low' },
]
