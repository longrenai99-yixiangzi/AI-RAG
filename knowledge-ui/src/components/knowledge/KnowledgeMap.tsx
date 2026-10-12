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
      {sample && <div className="sample-node-preview"><span className="map-node-type">待接入样例</span><b>{node.name}</b><p>本节点有人工整理样例；真实条目和来源数量以运行数据为准。</p><div>{sample.cards.map((card) => <span key={card.id}>{card.title}</span>)}</div><Link to={`/knowledge/${node.id}`}>进入知识空间</Link></div>}
      {children.length ? children.map((child) => <button key={child.id} onClick={() => onSelect(child)}><span className="map-node-type">{child.type === 'knowledge' ? '知识点' : '知识分类'}</span><b>{child.name}</b><small>分类入口 · 资料关联范围以内容页为准</small></button>) : !sample && <div className="map-empty"><p>分类名称不代表资料已全部整理。进入后可查相关项目资料和已确认摘录。</p><Link className="primary-link" to={`/node/${node.id}`}>查看此事项的资料与摘录</Link></div>}
    </div>
  </div>
}
