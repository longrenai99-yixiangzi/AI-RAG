import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

type SearchItem = {
  type: 'SOURCE' | 'KNOWLEDGE' | 'EVIDENCE'
  score: number
  source?: { source_id: string; file_name: string; source_path: string; index_status?: string }
  knowledge?: { knowledge_id: string; title: string; content: string; source_id: string; version: number }
  evidence?: { evidence_id: string; source_id: string; file_name: string; heading_path?: string; excerpt: string }
}

export function SearchResults() {
  const [params] = useSearchParams()
  const query = params.get('q') || ''
  const [items, setItems] = useState<SearchItem[]>([])
  const [message, setMessage] = useState('正在搜索真实知识和来源…')
  useEffect(() => {
    if (!query.trim()) { setItems([]); setMessage('请输入关键词后再搜索。'); return }
    setMessage('正在搜索真实知识和来源…')
    fetch(`/api/v2/knowledge/search?q=${encodeURIComponent(query)}`, { cache: 'no-store' })
      .then(async (response) => { if (!response.ok) throw new Error(String(response.status)); return response.json() })
      .then((payload) => { setItems(payload.items || []); setMessage((payload.items || []).length ? '' : '没有找到匹配的真实知识、来源或正文。') })
      .catch(() => { setItems([]); setMessage('搜索服务暂时不可用，请检查 8010 服务。') })
  }, [query])
  return <section><header className="page-hero compact"><div><span className="eyebrow">SEARCH</span><h1>全局搜索</h1><p>关键词：{query || '未输入'}</p></div></header>{message && <p className="empty-runtime">{message}</p>}<div className="search-results">{items.map((item, index) => <article className="panel" key={`${item.type}-${item.source?.source_id || item.knowledge?.knowledge_id || item.evidence?.evidence_id}-${index}`}><span>{item.type === 'SOURCE' ? '来源' : item.type === 'KNOWLEDGE' ? '已审核知识' : '正文证据'}</span>{item.source && <><h2>{item.source.file_name}</h2><p>{item.source.source_path}</p><Link to="/sources">在知识资产中查看</Link></>}{item.knowledge && <><h2>{item.knowledge.title}</h2><p>{item.knowledge.content}</p><small>版本 {item.knowledge.version} · {item.knowledge.knowledge_id}</small></>}{item.evidence && <><h2>{item.evidence.file_name}</h2><p>{item.evidence.excerpt}</p><small>{item.evidence.heading_path || '未识别章节'} · {item.evidence.evidence_id}</small></>}</article>)}</div></section>
}
