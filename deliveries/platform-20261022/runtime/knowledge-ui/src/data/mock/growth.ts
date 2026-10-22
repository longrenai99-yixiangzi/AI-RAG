import type { KnowledgeGrowthItem } from '../../types/knowledge'

export const growthItems: KnowledgeGrowthItem[] = [
  { id: 'g1', title: '新增《建筑专业图纸审查要点》', action: 'create', path: ['设计管理', '设计审查'], date: '今天' },
  { id: 'g2', title: '补充 EPC 项目设计策划案例', action: 'update', path: ['EPC', '项目策划'], date: '今天' },
  { id: 'g3', title: '关联价值创造与方案比选节点', action: 'link', path: ['价值创造'], date: '昨天' },
  { id: 'g4', title: '新增 AI Agent 工作流案例', action: 'create', path: ['AI', 'AI知识库与智能体'], date: '昨天' },
  { id: 'g5', title: '更新深化设计计划管理清单', action: 'update', path: ['技术管理', '深化设计'], date: '08-25' },
  { id: 'g6', title: '关联 BIM 与智能建造知识', action: 'link', path: ['科技管理', '数字化'], date: '08-24' },
  { id: 'g7', title: '新增设计任务书结构模板', action: 'create', path: ['设计管理', '项目策划'], date: '08-23' },
  { id: 'g8', title: '更新专业接口审查问题库', action: 'update', path: ['设计管理', '设计审查'], date: '08-22' },
  { id: 'g9', title: '新增专项方案交底案例', action: 'create', path: ['技术管理', '技术交底'], date: '08-21' },
  { id: 'g10', title: '关联科技成果转化资料', action: 'link', path: ['科技管理', '科技成果'], date: '08-20' },
]
