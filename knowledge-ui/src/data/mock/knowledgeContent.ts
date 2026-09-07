import type { KnowledgeNode } from '../../types/knowledge'

export type KnowledgeSourceRecord = {
  id: string
  name: string
  type: string
  authority: '正式原文' | '知识提炼' | '参考'
  sourcePath?: string
  location: string
  excerpt: string
}

export type KnowledgeCardRecord = {
  id: string
  title: string
  summary: string
  keyPoints: string[]
  sourceIds: string[]
  contentStatus?: '已抽取' | '待核原文'
}

export type KnowledgeCaseRecord = {
  id: string
  name: string
  scenario: string
  outcome: string
  sourceIds: string[]
}

export type KnowledgeNodeSample = {
  graph: { domain: KnowledgeNode; category: KnowledgeNode; node: KnowledgeNode }
  cards: KnowledgeCardRecord[]
  sources: KnowledgeSourceRecord[]
  cases: KnowledgeCaseRecord[]
  space: { overview: string; managementPoints: string[] }
}
