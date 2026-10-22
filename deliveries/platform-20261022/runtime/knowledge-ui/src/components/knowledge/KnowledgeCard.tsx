import { Link } from 'react-router-dom'
import type { KnowledgeNode } from '../../types/knowledge'
import { CoverageBar } from './CoverageBar'

export function KnowledgeCard({ node }: { node: KnowledgeNode }) {
  const domainClass = node.id.includes('technical') ? 'technical' : node.id.includes('science') ? 'science' : 'design'
  return <Link className={`knowledge-card ${domainClass}`} to={`/knowledge/${node.id}`}>
    <span className="card-kicker">一级知识板块</span>
    <h3>{node.name}</h3><p>{node.description}</p>
    <div className="card-numbers"><span><b>{node.childrenCount}</b>类知识</span><span><b>{node.knowledgeCount}</b>个节点</span></div>
    <CoverageBar value={node.coverage} />
  </Link>
}
