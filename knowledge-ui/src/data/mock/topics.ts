import type { Topic } from '../../types/knowledge'

export const topics: Topic[] = [
  {
    id: 'epc',
    name: 'EPC',
    color: 'epc',
    description: '聚合设计、技术、科技管理中与工程总承包履约相关的知识节点。',
    relatedKnowledgeIds: ['design-bid', 'design-planning', 'design-process', 'technical-detail', 'technical-construction'],
    children: ['项目策划', '设计协同', '深化设计', '履约案例'],
  },
  {
    id: 'value',
    name: '价值创造',
    color: 'value',
    description: '聚合设计创效、方案比选、效益测算与项目复盘的跨板块专题。',
    relatedKnowledgeIds: ['design-planning', 'design-result-library', 'technical-detail'],
    children: ['创效策划', '方案比选', '效益测算', '案例复盘'],
  },
  {
    id: 'ai',
    name: 'AI',
    color: 'ai',
    description: '覆盖模型、工具、RAG、智能体、内容生成、部署与企业业务应用。',
    relatedKnowledgeIds: ['science-digital', 'science-research', 'design-process'],
    children: ['AI基础与模型', 'AI工具', 'AI知识库与智能体', 'AI内容生成', 'AI开发与部署', 'AI业务应用'],
  },
]
