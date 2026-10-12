import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { KnowledgeMap } from '../components/knowledge/KnowledgeMap'
import { KnowledgeTree } from '../components/knowledge/KnowledgeTree'
import { domains, getAncestors, getChildren, getNode } from '../data/mock/knowledgeTree'
import type { KnowledgeNode } from '../types/knowledge'

export function KnowledgeFramework() {
  const [params] = useSearchParams()
  const requestedNode = params.get('node')
  const initial = getNode(requestedNode || '') || domains[0]
  const [selected, setSelected] = useState<KnowledgeNode>(initial)
  const [cards, setCards] = useState<Array<{node_id: string; source_id: string; source_version: string}> | null>(null)
  useEffect(() => { fetch('/api/v2/knowledge/items', {cache: 'no-store'}).then(r => {if(!r.ok) throw new Error();return r.json()}).then(p => {if(!Array.isArray(p.items)) throw new Error();setCards(p.items)}).catch(() => setCards(null)) }, [])
  useEffect(() => setSelected(getNode(requestedNode || '') || domains[0]), [requestedNode])
  const children = useMemo(() => getChildren(selected.id), [selected])
  const ancestors = getAncestors(selected.id)
  const branchCards = cards?.filter(card => getAncestors(card.node_id).some(parent => parent.id === selected.id))
  const evidenceVersions = branchCards ? new Set(branchCards.map(card => card.source_id+'|'+card.source_version)).size : '待统计'
  return <>
    <section className="page-hero compact"><div><span className="eyebrow">KNOWLEDGE FRAMEWORK</span><h1>知识框架</h1><p>逐级查看企业知识体系、知识关系和节点属性。</p></div></section>
    <section className="framework-layout">
      <article className="panel tree-panel"><div className="panel-title"><h2>知识体系</h2><span>3大板块</span></div><KnowledgeTree selectedId={selected.id} onSelect={setSelected} /></article>
      <article className="panel map-panel"><div className="panel-title"><h2>知识地图</h2><span>按需展开</span></div><div className="breadcrumbs">{ancestors.map((node) => <button key={node.id} onClick={() => setSelected(node)}>{node.name}</button>)}</div><KnowledgeMap node={selected} children={children} onSelect={setSelected} /></article>
      <article className="panel detail-panel"><div className="panel-title"><h2>节点信息</h2><span>{selected.type}</span></div><span className="detail-domain">{ancestors[0]?.name}</span><h3>{selected.name}</h3><p>{selected.description}</p><div className="detail-metrics"><div><b>{selected.childrenCount}</b><span>配置子节点</span></div><div><b>{branchCards?.length ?? '待统计'}</b><span>当前知识记录</span></div><div><b>{evidenceVersions}</b><span>卡片证据版本</span></div></div><p>统计只覆盖当前知识卡；不等于全资料覆盖率。</p><div className="tag-row">{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div><div className="related-list"><b>关联专题</b>{selected.relatedTopics.map((topic) => <span key={topic}>#{topic.toUpperCase()}</span>)}</div><Link className="primary-link" to={`/knowledge/${selected.id}`}>进入完整知识空间</Link></article>
    </section>
  </>
}
