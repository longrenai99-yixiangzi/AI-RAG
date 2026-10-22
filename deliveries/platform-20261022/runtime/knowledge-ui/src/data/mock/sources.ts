import type { KnowledgeSource } from '../../types/knowledge'

const sourceTypes: KnowledgeSource['type'][] = ['制度', '规范', '标准', '项目案例', '模板', 'Word', 'PDF', 'Excel', 'PPT', '其他资料']

export const sources: KnowledgeSource[] = Array.from({ length: 20 }, (_, index) => ({
  id: `source-${index + 1}`,
  name: ['EPC项目设计管理指南', '设计任务书模板', '项目设计管理手册', '设计方案比选清单', '深化设计管理细则'][index % 5] + ` · V${(index % 3) + 1}`,
  type: sourceTypes[index % sourceTypes.length],
  source: index % 4 === 0 ? 'Root-002 Shadow资料 · 待审批' : 'Root-001 正式知识基线',
  knowledge: ['设计审查', '项目策划', '价值创造', '深化设计', '科技成果'][index % 5],
  version: `202${4 + (index % 3)}.${String((index % 9) + 1).padStart(2, '0')}`,
  updatedAt: `2026-08-${String(27 - (index % 12)).padStart(2, '0')}`,
  authority: index % 4 === 0 ? '待审' : index % 5 === 0 ? '参考' : '正式',
}))
