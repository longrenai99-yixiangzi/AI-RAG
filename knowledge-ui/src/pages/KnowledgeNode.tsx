import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getAncestors, getNode } from '../data/mock/knowledgeTree'

type Knowledge = { knowledge_id: string; node_id: string; title: string; content: string; applicability?: string; source_id: string; source_version?: string; version: number; edit_origin?: string }

export function KnowledgeNode() {
  const { id = '' } = useParams()
  const node = getNode(id)
  const [knowledge, setKnowledge] = useState<Knowledge[]>([])
  const [loadError, setLoadError] = useState(false)
  useEffect(() => {
    fetch('/api/v2/knowledge/items', { cache: 'no-store' })
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json() })
      .then((payload) => setKnowledge((payload.items || []).filter((item: Knowledge) => item.node_id === id)))
      .catch(() => setLoadError(true))
  }, [id])
  if (!node) return <div className="empty-page"><h1>未找到知识节点</h1><Link to="/framework">返回知识框架</Link></div>
  const ancestors = getAncestors(node.id)
  return <section className="node-page"><div className="breadcrumbs page-breadcrumbs">{ancestors.map((item) => <Link key={item.id} to={`/knowledge/${item.id}`}>{item.name}</Link>)}</div><header className="node-hero"><span className="eyebrow">KNOWLEDGE NODE</span><h1>{node.name}</h1><p>{node.description}</p><div className="tag-row">{node.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></header>
    <article className="sample-space-section"><div className="section-heading"><div><span className="eyebrow">REVIEWED KNOWLEDGE</span><h2>已生效知识</h2></div><Link to={`/ai?node=${node.id}`}>基于此节点提问</Link></div>{loadError ? <p className="runtime-error">真实知识暂时无法读取。</p> : knowledge.length ? <div className="sample-card-grid">{knowledge.map((item) => <article key={item.knowledge_id}><span>已审核 · 版本 {item.version}</span><h3>{item.title}</h3><p>{item.content}</p>{item.applicability && <small>适用范围：{item.applicability}</small>}<small>来源：{item.source_id} · {(item.source_version || '待核实').slice(0, 12)}</small></article>)}</div> : <p className="sample-empty">当前节点还没有已审核并生效的知识；下方结构只是待接入模板。</p>}</article>
    <div className="node-content">{['知识概述', '核心管理要点', '规范依据', '典型问题', '项目案例', '相关知识'].map((title) => <article className="node-section" key={title}><h2>{title}</h2><p>待从已审核知识和有效来源中接入，不使用示例内容作为业务事实。</p></article>)}</div>
  </section>
}
