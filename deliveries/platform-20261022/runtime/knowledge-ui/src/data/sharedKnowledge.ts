import snapshot from './knowledge-contract.generated.json'
import type { KnowledgeNode } from '../types/knowledge'

export type MaterialRecord = { id:string; path:string; absolute_path:string; title:string; extension:string; primary:string|null; related:string[]; subtopics:string[]; domain:string; product_line_candidates:string[]; classification_review:string; layer:string; answer_eligible:boolean; eligibility_reason:string }
const records: MaterialRecord[] = snapshot.records
export const sharedKnowledge = { ...snapshot, records }
export const isSharedNode = (id: string) => id === 'domain-design' || id === 'domain-technical' || id === 'domain-science' || id.startsWith('design-code-')
export const codeForNode = (id: string) => id.startsWith('design-code-') ? id.slice('design-code-'.length) : ''
const date = snapshot.architecture.defined_on
const makeNode = (id: string, name: string, parentId?: string, code = ''): KnowledgeNode => {
  const rows = snapshot.records.filter(r => r.domain === 'design' && r.layer !== '候选待审核' && (!code || r.primary === code || r.primary?.startsWith(code + '.')))
  return { id, name, parentId, type: parentId ? (code.includes('.') ? 'knowledge' : 'category') : 'domain', description: '现有资料浏览；分类线索待抽检，资料数量不代表已审核知识或问答覆盖率。', childrenCount: 0, knowledgeCount: 0, sourceCount: rows.length, coverage: 0, tags: ['设计管理'], relatedTopics: [], updatedAt: date }
}
export const sharedNodes: KnowledgeNode[] = [makeNode('domain-design', '设计管理'), ...snapshot.taxonomy.flatMap(section => [makeNode('design-code-' + section.id, section.id + ' ' + section.name, 'domain-design', section.id), ...section.children.map(([code, name]) => makeNode('design-code-' + code, code + ' ' + name, 'design-code-' + section.id, code))]), ...snapshot.architecture.management_domains.filter(d => d.id !== 'design').map(d => ({ ...makeNode('domain-' + d.id, d.name + '（后续补充）'), sourceCount: snapshot.records.filter(r => r.domain === d.id).length, description: '预留管理域；现有资料待整理，不计为已建成知识。', tags:[d.name] }))]
for (const node of sharedNodes) node.childrenCount = sharedNodes.filter(child => child.parentId === node.id).length
