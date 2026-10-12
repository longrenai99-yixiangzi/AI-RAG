import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getAncestors, getNode } from '../data/mock/knowledgeTree'

type Knowledge = { knowledge_id: string; node_id: string; title: string; content: string; applicability?: string; source_id: string; source_version?: string; evidence_id?: string; version: number; edit_origin?: string; original_title?: string; original_node_id?: string; context_question?: string; context_text?: string; context_status?: string; context_source?: { source_path: string; sha256: string; location: string }; primary_sources?: {source_path: string; sha256: string; location?: string}[] }

export function KnowledgeNode() {
  const { id = '' } = useParams()
  const node = getNode(id)
  const [knowledge, setKnowledge] = useState<Knowledge[]>([])
  const [loadError, setLoadError] = useState(false)
  const [resources,setResources]=useState<Array<{project_id:string;project_name:string;subject:{id:string;name:string;coverage:string}}>>([])
  const [resourceError,setResourceError]=useState(false)
  useEffect(()=>{const c=new AbortController();setResources([]);setResourceError(false);fetch('/api/v2/knowledge/nodes/'+encodeURIComponent(id)+'/project-resources',{signal:c.signal,cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(p=>setResources(p.items)).catch(()=>{if(!c.signal.aborted)setResourceError(true)});return()=>c.abort()},[id])
  useEffect(() => {
    const controller = new AbortController()
    setKnowledge([]); setLoadError(false)
    fetch('/api/v2/knowledge/items', { cache: 'no-store', signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json() })
      .then((payload) => { if (!Array.isArray(payload.items)) throw new Error(); if (!controller.signal.aborted) setKnowledge(payload.items.filter((item: Knowledge) => item.node_id === id)) })
      .catch(() => { if (!controller.signal.aborted) setLoadError(true) })
    return () => controller.abort()
  }, [id])
  if (!node) return <div className="empty-page"><h1>未找到知识节点</h1><Link to="/framework">返回知识框架</Link></div>
  const ancestors = getAncestors(node.id)
  return <section className="node-page"><div className="breadcrumbs page-breadcrumbs">{ancestors.map((item) => <Link key={item.id} to={`/knowledge/${item.id}`}>{item.name}</Link>)}</div><header className="node-hero"><span className="eyebrow">KNOWLEDGE NODE</span><h1>{node.name}</h1><p>{node.description}</p><div className="tag-row">{node.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></header>
    <article className="panel"><h2>按背景查资料</h2><p>通用方法可以查全库；项目事实先进入项目。没有摘录卡片不代表没有资料。</p><Link to={'/search?'+new URLSearchParams({mode:'content',q:node.name.replace(/^\d+\.\d+\s*/, '')})}>搜索这一事项的相关资料</Link>{id==='design-system-7'&&<p><Link className="primary-link" to="/periods">按部门、年份和期间浏览整份总结</Link> 下方少量摘录不代表指标全集。</p>}{resourceError?<p className="runtime-error">项目资料关联暂时无法读取。</p>:<div className="domain-grid">{resources.map(r=><Link className="space-card" key={r.project_id+r.subject.id} to={'/projects/'+r.project_id+'?subject='+r.subject.id}><h3>{r.project_name}</h3><b>{r.subject.name}</b><p>{r.subject.coverage}</p><span>查看项目内相关原文</span></Link>)}</div>}</article>
    <article className="sample-space-section"><div className="section-heading"><div><h2>已逐条确认的摘录（{knowledge.length}）</h2></div><Link to={`/ai?node=${node.id}`}>查询此事项的通用问题</Link></div>{loadError ? <p className="runtime-error">真实知识暂时无法读取。</p> : knowledge.length ? <div className="sample-card-grid">{knowledge.map((item) => <article key={item.knowledge_id}><span>{item.context_status === 'REVIEW_REQUIRED' ? '原记录保留 · 范围待复核' : '已审核记录'} · 版本 {item.version}</span><h3>{item.title}</h3>{item.context_question && <p><b>对应问题：</b>{item.context_question}</p>}<p style={{ whiteSpace: 'pre-line' }}>{item.content}</p>{item.context_text && <p className={item.context_status === 'REVIEW_REQUIRED' ? 'runtime-error' : ''}><b>同版资料上下文：</b>{item.context_text}</p>}{item.applicability && <small>适用范围：{item.applicability}</small>}{item.context_source && <small>上下文定位：{item.context_source.source_path.split(/[\\/]/).pop()} · {item.context_source.location}</small>}<small>来源版本：{(item.source_version || '待核实').slice(0, 12)}</small>{item.evidence_id && <Link style={{display: 'block', marginTop: '6px'}} to={`/sources?source_id=${encodeURIComponent(item.source_id)}&evidence_id=${encodeURIComponent(item.evidence_id)}&source_version=${encodeURIComponent(item.source_version || '')}`}>查看本条知识的来源证据</Link>}{item.primary_sources?.map(source => <Link style={{display: 'block', marginTop: '6px'}} key={source.sha256+source.source_path} to={'/api/v2/knowledge/primary-sources/'+source.sha256} reloadDocument>打开原始资料版本 · {source.source_path.split(/[\\/]/).pop()}</Link>)}{item.original_title && <details><summary>查看原卡标题与归类</summary><small>{item.original_title} · {item.original_node_id} · {item.knowledge_id}</small></details>}</article>)}</div> : <p className="sample-empty">本节点尚未形成逐条确认的摘录；可通过上方项目资料或全库搜索查原文。</p>}</article>
    <p>当前摘录只覆盖已经逐条确认的内容；原始资料按上方项目或全库搜索查阅。</p>
  </section>
}
