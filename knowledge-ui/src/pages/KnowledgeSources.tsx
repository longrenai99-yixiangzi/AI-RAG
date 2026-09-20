import { useEffect, useState } from 'react'

type Source = {
  source_id: string
  file_name: string
  source_path: string
  file_type: string
  source_type?: string
  knowledge_root_id?: string
  body_status?: string
  index_status?: string
  current_hash?: string
  version_note?: string
  approval_status?: string
  chunk_count?: number
  error?: string | null
}
type Evidence = { evidence_id: string; source_version?: string; parent_evidence_id?: string; location: Record<string, unknown>; heading_path?: string; raw_text?: string; search_context?: string; excerpt: string }

const formats = ['全部', '.pdf', '.docx', '.xlsx', '.pptx', '.md', '.wps']
const statusText: Record<string, string> = { INDEXED: '正文已入库', PENDING: '等待处理', FAILED: '处理失败', PARSED: '解析完成' }

export function KnowledgeSources() {
  const [sources, setSources] = useState<Source[]>([])
  const [format, setFormat] = useState('全部')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<Source | null>(null)
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [error, setError] = useState('')

  async function loadSources() {
    const params = new URLSearchParams({ offset: String(page * 50), limit: '50' })
    if (query.trim()) params.set('query', query.trim())
    if (format !== '全部') params.set('file_type', format)
    return fetch(`/api/v2/knowledge/sources?${params}`, { cache: 'no-store' })
      .then(async (response) => { if (!response.ok) throw new Error(String(response.status)); return response.json() })
      .then((payload) => { setSources(payload.items || []); setTotal(payload.total || 0) })
      .catch(() => setError('真实来源暂时无法读取，请检查 8010 服务。'))
  }
  useEffect(() => { const timer = window.setTimeout(() => void loadSources(), 200); return () => window.clearTimeout(timer) }, [query, format, page])

  async function inspect(source: Source) {
    setSelected(source)
    setEvidence([])
    const response = await fetch(`/api/v2/knowledge/sources/${source.source_id}/evidence?limit=12`, { cache: 'no-store' })
    const payload = await response.json()
    if (response.ok) setEvidence(payload.items || [])
  }

  async function operate(action: 'refresh' | 'withdraw') {
    if (!selected) return
    setError('')
    const response = await fetch(`/api/v2/knowledge/sources/${selected.source_id}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trial_user: 'reviewer-001' }) })
    const payload = await response.json()
    if (!response.ok) { setError(payload.detail || '来源操作失败。'); return }
    await loadSources()
    if (action === 'withdraw') { setSelected(null); setEvidence([]) } else if (payload.source) { await inspect(payload.source) }
  }

  return <section>
    <header className="page-hero compact"><div><span className="eyebrow">KNOWLEDGE SOURCES</span><h1>知识来源</h1><p>这里显示当前试用问答实际可访问的来源和正文状态。</p></div></header>
    {error && <p className="runtime-error">{error}</p>}
    <div className="source-toolbar"><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} placeholder="按名称或路径筛选" /><div className="source-filter">{formats.map((item) => <button key={item} className={format === item ? 'active' : ''} onClick={() => { setFormat(item); setPage(0) }}>{item === '全部' ? item : item.slice(1).toUpperCase()}</button>)}</div></div>
    <article className="panel source-table real-source-table">
      <div className="table-head"><span>资料名称</span><span>格式</span><span>业务类型</span><span>正文状态</span><span>索引状态</span><span>版本</span></div>
      {sources.map((source) => <button className="table-row source-row-button" key={source.source_id} onClick={() => void inspect(source)}><b>{source.file_name}</b><span>{source.file_type.slice(1).toUpperCase()}</span><span>{source.source_type || '待分类'}</span><span>{statusText[source.body_status || ''] || source.body_status || '待确认'}</span><span className={source.index_status === 'FAILED' ? 'pending-text' : ''}>{statusText[source.index_status || ''] || source.index_status || '待确认'}</span><span>{source.current_hash === 'FROZEN_INDEX' ? '冻结索引' : source.current_hash?.slice(0, 8) || '待核实'}</span></button>)}
      {!sources.length && !error && <p className="empty-runtime">没有符合条件的真实来源。</p>}
    </article>
    <div className="source-pagination"><span>共 {total} 条</span><button disabled={page === 0} onClick={() => setPage((value) => value - 1)}>上一页</button><span>第 {page + 1} 页</span><button disabled={(page + 1) * 50 >= total} onClick={() => setPage((value) => value + 1)}>下一页</button></div>
    {selected && <article className="panel source-inspector"><header><div><span className="eyebrow">SOURCE DETAIL</span><h2>{selected.file_name}</h2></div><button onClick={() => setSelected(null)}>关闭</button></header><p>{selected.source_path}</p><div className="source-meta"><span>{selected.knowledge_root_id}</span><span>{selected.version_note || '[待核实]'}</span><span>{selected.chunk_count ?? evidence.length} 个切片</span></div>{selected.approval_status === 'USER_APPROVED_SHADOW_READ' && <div className="source-actions"><button onClick={() => void operate('refresh')}>重新读取并刷新试用索引</button><button onClick={() => void operate('withdraw')}>撤回试用来源</button></div>}{selected.error && <p className="runtime-error">{selected.error}</p>}<h3>解析正文与切片预览</h3>{evidence.length ? evidence.map((item) => <div className="evidence-preview" key={item.evidence_id}><b>{locationText(item.location)} {item.heading_path || ''}</b><small>证据 {item.evidence_id} · 父块 {item.parent_evidence_id || '无'} · 版本 {(item.source_version || '待核实').slice(0, 12)}</small>{item.search_context && <details><summary>检索上下文（不作为引用事实）</summary><p>{item.search_context}</p></details>}<pre>{item.raw_text || item.excerpt}</pre></div>) : <p className="empty-runtime">当前来源没有可预览正文，或尚未完成索引。</p>}</article>}
  </section>
}

function locationText(location: Record<string, unknown>) {
  if (location.page) return `第${location.page}页`
  if (location.sheet_name) return `${location.sheet_name} 第${location.row_start || location.row || '?'}行`
  if (location.table) return `表${location.table}`
  if (location.paragraph_start) return `第${location.paragraph_start}段`
  if (location.line_start) return `第${location.line_start}行`
  return '位置未定位'
}
