import { useEffect, useState } from 'react'

type RecordItem = { feedback_id: string; question: string; comment?: string; traffic_kind: string; processing_status: string; original_status?: string; published_package_sha256?: string }
const kindLabel: Record<string, string> = { REAL: '业务反馈', TECHNICAL: '技术记录', UNCLASSIFIED: '未分类' }
const statusLabel: Record<string, string> = { PUBLISHED_PENDING_BUSINESS_REVIEW: '修复已发布，待业务复核', TECHNICAL_RECORD: '技术检查记录', PENDING_REVIEW: '待核对处理', CLOSED: '已处理', REJECTED: '已驳回', DEFERRED: '已暂缓', WITHDRAWN: '已撤回' }

export function FeedbackRecords() {
  const [rows, setRows] = useState<RecordItem[]>([])
  const [summary, setSummary] = useState<Record<string, number> | null>(null)
  const [filter, setFilter] = useState('BUSINESS')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    fetch('/api/v2/feedback-workflow', { cache: 'no-store' })
      .then(async response => { if (!response.ok) throw new Error(); return response.json() })
      .then(payload => { if (!Array.isArray(payload.items)) throw new Error(); setRows(payload.items); setSummary(payload.summary || null) })
      .catch(() => setError('反馈记录读取失败，请检查服务；这不表示没有反馈。'))
      .finally(() => setLoading(false))
  }, [])
  const shown = rows.filter(row => filter === 'ALL' || (filter === 'BUSINESS' ? row.traffic_kind !== 'TECHNICAL' : row.traffic_kind === filter))
  return <section><header className="page-hero compact"><div><h1>反馈记录</h1><p>保留历史意见，分别显示业务待办和技术检查；已发布修复仍需业务复核。</p></div></header>
    {summary && <div className="runtime-metrics"><article><b>{summary.pending}</b><span>待核对或业务复核</span></article><article><b>{summary.pending_business_review}</b><span>已修复待业务复核</span></article><article><b>{summary.technical}</b><span>技术记录</span></article><article><b>{summary.unclassified}</b><span>未分类记录</span></article></div>}
    <div className="source-filter">{[['BUSINESS', '业务待办'], ['TECHNICAL', '技术记录'], ['UNCLASSIFIED', '未分类'], ['ALL', '全部历史']].map(([value, label]) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div>
    {error && <p className="runtime-error">{error}</p>}{loading && <p>正在读取记录…</p>}
    {!loading && !error && !shown.length && <p className="empty-runtime">当前筛选范围没有反馈记录。</p>}
    {shown.map(row => <article className="panel diagnostic-card" key={row.feedback_id}><h2>{row.question || '问题待核对'}</h2><p>{kindLabel[row.traffic_kind] || '未分类'} · {statusLabel[row.processing_status] || '待核对处理'}</p>{row.published_package_sha256 && <p>已发布修复版本：{row.published_package_sha256.slice(0, 8)}</p>}<details><summary>查看原反馈与历史状态</summary><p>{row.comment || '无补充说明'}</p><small>原记录状态：{row.original_status || '未记录'} · {row.feedback_id}</small></details></article>)}
  </section>
}
