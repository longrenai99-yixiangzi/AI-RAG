export type KnowledgeNodeType = 'domain' | 'category' | 'topic' | 'knowledge' | 'source'

export type DomainId = 'design' | 'technical' | 'science'

export interface KnowledgeNode {
  id: string
  name: string
  parentId?: string
  type: KnowledgeNodeType
  description: string
  childrenCount: number
  knowledgeCount: number
  sourceCount: number
  coverage: number
  tags: string[]
  relatedTopics: string[]
  updatedAt: string
}

export interface Topic {
  id: string
  name: string
  color: 'epc' | 'value' | 'ai'
  description: string
  relatedKnowledgeIds: string[]
  children: string[]
}

export interface KnowledgeGap {
  id: string
  nodeId: string
  title: string
  reason: string
  level: 'low' | 'medium' | 'high'
}

export interface KnowledgeGrowthItem {
  id: string
  title: string
  action: 'create' | 'update' | 'link'
  path: string[]
  date: string
}

export interface KnowledgeSource {
  id: string
  name: string
  type: '制度' | '规范' | '标准' | '项目案例' | '模板' | 'Word' | 'PDF' | 'Excel' | 'PPT' | '其他资料'
  source: string
  knowledge: string
  version: string
  updatedAt: string
  authority: '正式' | '待审' | '参考'
}
