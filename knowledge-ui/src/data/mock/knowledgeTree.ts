import type { DomainId, KnowledgeNode } from '../../types/knowledge'
import { getKnowledgeNodeSample } from './sampleContent'
import { designManagementCategorySeeds, designManagementGraphNodes } from './designManagementSample'
import { technicalConstructionGraph } from './technicalConstructionSample'

type DomainSeed = {
  id: DomainId
  name: string
  description: string
  categories: Array<[string, string, string[]]>
}

const seeds: DomainSeed[] = [
  {
    id: 'design',
    name: '设计管理',
    description: '覆盖制度、投标前期、设计策划、过程、成果、资源与资料的完整设计管理知识体系。',
    categories: designManagementCategorySeeds,
  },
  {
    id: 'technical',
    name: '技术管理',
    description: '围绕深化设计、施工组织、专项方案和专业技术协同形成的技术管理体系。',
    categories: [
      ['system', '技术管理体系', ['技术组织', '技术制度', '技术检查']],
      ['construction', '施工组织设计', ['总体施组', '工序组织', '资源配置']],
      ['special', '专项施工方案', ['危大工程', '专项论证', '方案交底']],
      ['detail', '深化设计', ['深化计划管理', '专业深化设计', '深化成果交付']],
      ['disclosure', '技术交底', ['交底体系', '交底记录', '交底案例']],
      ['case', '项目案例', ['技术复盘', '质量问题案例', '工法应用案例']],
    ],
  },
  {
    id: 'science',
    name: '科技管理',
    description: '围绕研发、成果转化、数字化和科技支撑形成的科技管理体系。',
    categories: [
      ['system', '科技管理体系', ['科技制度', '科技计划', '科技评价']],
      ['research', '科技研发', ['课题立项', '研发过程', '成果验收']],
      ['outcome', '科技成果', ['成果转化', '成果推广', '成果奖励']],
      ['ip', '工法 / 专利 / 论文', ['工法', '专利', '论文']],
      ['digital', '数字化', ['BIM', '数据平台', '智能建造']],
      ['case', '项目案例', ['科技示范项目', '数字化案例', '成果应用案例']],
    ],
  },
]

function makeNodes(seed: DomainSeed): KnowledgeNode[] {
  const domainId = `domain-${seed.id}`
  const nodes: KnowledgeNode[] = [
    {
      id: domainId,
      name: seed.name,
      type: 'domain',
      description: seed.description,
      childrenCount: seed.categories.length,
      knowledgeCount: seed.categories.length * 12 + 34,
      sourceCount: seed.categories.length * 19 + 41,
      coverage: seed.id === 'design' ? 87 : seed.id === 'technical' ? 76 : 64,
      tags: [seed.name, '一级板块'],
      relatedTopics: seed.id === 'science' ? ['ai', 'epc'] : seed.id === 'design' ? ['epc', 'value'] : ['epc'],
      updatedAt: '2026-08-27',
    },
  ]

  seed.categories.forEach(([id, name, leaves], index) => {
    const categoryId = `${seed.id}-${id}`
    nodes.push({
      id: categoryId,
      parentId: domainId,
      name,
      type: 'category',
      description: `${name}相关的管理规则、知识要点、案例与知识来源。`,
      childrenCount: leaves.length,
      knowledgeCount: 8 + index * 4,
      sourceCount: 15 + index * 7,
      coverage: Math.max(54, Math.min(94, seed.id === 'design' ? 92 - index * 4 : 83 - index * 5)),
      tags: [seed.name, name],
      relatedTopics: id === 'value' ? ['value', 'epc'] : id === 'digital' ? ['ai'] : ['epc'],
      updatedAt: '2026-08-21',
    })
    leaves.forEach((leaf, leafIndex) => {
      const leafId = `${categoryId}-${leafIndex + 1}`
      const sample = getKnowledgeNodeSample(leafId)
      nodes.push({
        id: leafId,
        parentId: categoryId,
        name: leaf,
        type: 'knowledge',
        description: sample?.space.overview || `${leaf}的结构化知识、核心要点与可核查来源。`,
        childrenCount: 0,
        knowledgeCount: sample?.cards.length ?? 3 + ((index + leafIndex) % 7),
        sourceCount: sample?.sources.length ?? 5 + ((index * 3 + leafIndex) % 12),
        coverage: Math.max(42, Math.min(93, 88 - index * 5 - leafIndex * 3)),
        tags: [seed.name, name, leaf],
        relatedTopics: id === 'value' ? ['value'] : id === 'digital' ? ['ai'] : ['epc'],
        updatedAt: '2026-08-18',
      })
    })
  })
  return nodes
}

const objectifiedSampleNodes = [
  technicalConstructionGraph.domain, technicalConstructionGraph.category, technicalConstructionGraph.node,
  ...designManagementGraphNodes,
]
export const knowledgeNodes = seeds.flatMap(makeNodes).map((node) => objectifiedSampleNodes.find((sample) => sample.id === node.id) || node)
export const domains = knowledgeNodes.filter((node) => node.type === 'domain')

export const getNode = (id: string) => knowledgeNodes.find((node) => node.id === id)
export const getChildren = (parentId: string) => knowledgeNodes.filter((node) => node.parentId === parentId)
export const getAncestors = (id: string) => {
  const chain: KnowledgeNode[] = []
  let current = getNode(id)
  while (current) {
    chain.unshift(current)
    current = current.parentId ? getNode(current.parentId) : undefined
  }
  return chain
}
