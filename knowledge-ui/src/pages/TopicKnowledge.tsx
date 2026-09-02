import { Link, useParams } from 'react-router-dom'
import { topics } from '../data/mock/topics'
import { knowledgeNodes } from '../data/mock/knowledgeTree'

export function TopicKnowledge() {
  const { id } = useParams(); const topic = topics.find((item) => item.id === id)
  if (!topic) return <div className="empty-page"><h1>未找到专题</h1><Link to="/topics">返回专题知识</Link></div>
  const nodes = knowledgeNodes.filter((node) => topic.relatedKnowledgeIds.includes(node.id))
  return <section><header className={`topic-hero ${topic.color}`}><span className="eyebrow">CROSS-DOMAIN TOPIC</span><h1>{topic.name}</h1><p>{topic.description}</p></header><div className="subtopic-grid">{topic.children.map((child) => <article key={child}><span>子专题</span><h3>{child}</h3><p>关联三大业务板块中的知识节点，不复制原始内容。</p></article>)}</div><article className="panel related-panel"><div className="section-heading"><div><span className="eyebrow">RELATED KNOWLEDGE</span><h2>关联知识</h2></div></div><div className="related-nodes">{nodes.map((node) => <Link key={node.id} to={`/knowledge/${node.id}`}>{node.name}<small>{node.description}</small></Link>)}</div></article></section>
}
