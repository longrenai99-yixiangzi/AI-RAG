import { Link } from 'react-router-dom'
import type { KnowledgeNode } from '../../types/knowledge'
import { getKnowledgeNodeSample } from '../../data/mock/sampleContent'

type Props = { node: KnowledgeNode; children: KnowledgeNode[]; onSelect: (node: KnowledgeNode) => void }

export function KnowledgeMap({ node, children, onSelect }: Props) {
  const sample = getKnowledgeNodeSample(node.id)
  return <div className="knowledge-map">
    <div className="map-root"><span>当前节点</span><b>{node.name}</b><small>{node.description}</small></div>
    <div className="map-line" />
    <div className="map-children">
      {sample && <div className="sample-node-preview"><span className="map-node-type">KNOWLEDGE NODE PREVIEW</span><b>{node.name} · 已接通真实内容样板</b><p>{sample.cards.length} 张知识卡片 · {sample.sources.length} 条资料来源 · {sample.cases.length} 个项目案例</p><div>{sample.cards.map((card) => <span key={card.id}>{card.title}</span>)}</div><Link to={`/knowledge/${node.id}`}>进入完整知识空间</Link></div>}
      {children.length ? children.map((child) => <button key={child.id} onClick={() => onSelect(child)}><span className="map-node-type">{child.type === 'knowledge' ? '知识点' : '知识分类'}</span><b>{child.name}</b><small>{child.knowledgeCount} 个知识 · 覆盖 {child.coverage}%</small></button>) : !sample && <p className="map-empty">当前节点已是知识叶子，可进入知识节点查看结构化内容。</p>}
    </div>
  </div>
}
