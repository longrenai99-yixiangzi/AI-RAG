import { Link, useParams } from 'react-router-dom'
import { getAncestors, getNode } from '../data/mock/knowledgeTree'
import { sources } from '../data/mock/sources'

export function KnowledgeNode() {
  const { id = '' } = useParams(); const node = getNode(id)
  if (!node) return <div className="empty-page"><h1>未找到知识节点</h1><Link to="/framework">返回知识框架</Link></div>
  const ancestors = getAncestors(node.id)
  const sections = ['知识概述', '核心管理要点', '规范依据', '典型问题', '项目案例', '相关知识']
  return <section className="node-page"><div className="breadcrumbs page-breadcrumbs">{ancestors.map((item) => <Link key={item.id} to={`/knowledge/${item.id}`}>{item.name}</Link>)}</div><header className="node-hero"><span className="eyebrow">KNOWLEDGE NODE</span><h1>{node.name}</h1><p>{node.description}</p><div className="tag-row">{node.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></header><div className="node-content">{sections.map((title, index) => <article className="node-section" key={title}><h2>{title}</h2><p>{index === 0 ? `此处用于呈现“${node.name}”的结构化知识内容。V0.1 使用 Mock 数据，后续由知识卡片和经审核来源填充。` : '知识内容将在后续阶段以结构化卡片呈现，原始文件仅作为可核查来源置于页面后半部分。'}</p></article>)}</div><article className="source-preview"><div className="section-heading"><div><span className="eyebrow">SOURCES</span><h2>知识来源</h2></div><span className="panel-note">V0.1 Mock</span></div>{sources.slice(0, 4).map((source) => <button key={source.id}><b>{source.name}</b><span>{source.type} · {source.source} · {source.updatedAt}</span></button>)}</article></section>
}
