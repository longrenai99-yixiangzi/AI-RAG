import { useEffect, useState } from 'react'

type Funnel = { stage: string; rate: number | null; status: string }
type Failure = { code: string; count: number }
type Question = { query_run_id: string; timestamp: string; question: string; answer_status: string; traffic_kind: string; failure: { failure_stage?: string; failure_code?: string; failure_reason?: string }; latency?: { total_ms?: number } }
type Overview = { question_runs: number; answer_success_rate: number | null; traffic_counts: Record<string, number>; quality_funnel: Funnel[]; failure_distribution: Failure[]; benchmark: Record<string, unknown>; audit_files: Record<string, boolean>; historical_evaluation_note?: string }
const trafficLabel: Record<string, string> = { ALL: '全部记录', REAL: '真实业务', TECHNICAL: '技术检查', UNCLASSIFIED: '未分类' }
const stageLabel: Record<string, string> = { 'Source Available': '原始资料可取得', 'Parse Success': '正文读取成功', 'Chunk Integrity': '内容切分完整', 'Metadata Strong Facts': '对象信息完整', 'Recall@20': '检索命中依据', 'Rerank@5': '结果排序有效', 'Evidence Pass': '证据核对通过', 'Answer Correct': '答案正确' }

export function Diagnostics() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('ALL')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setTrace(null)
    const query = `traffic_filter=${filter}`
    Promise.all([
      fetch(`/api/v2/knowledge/diagnostics/overview?${query}`, { cache: 'no-store' }).then(response => response.ok ? response.json() : Promise.reject()),
      fetch(`/api/v2/knowledge/diagnostics/questions?limit=50&${query}`, { cache: 'no-store' }).then(response => response.ok ? response.json() : Promise.reject()),
    ]).then(([summary, list]) => { if (!Array.isArray(list.items)) throw new Error(); if (active) { setOverview(summary); setQuestions(list.items) } })
      .catch(() => { if (active) setError('问答记录读取失败，请检查当前服务；这不表示没有记录。') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [filter])
  async function inspect(id: string) {
    setError(''); setTrace(null)
    try {
      const response = await fetch(`/api/v2/knowledge/diagnostics/questions/${encodeURIComponent(id)}`, { cache: 'no-store' })
      if (!response.ok) throw new Error()
      const payload = await response.json()
      if (!payload.trace) throw new Error()
      setTrace(payload.trace)
    } catch { setError('这条问答的详细记录读取失败，请核对记录位置。') }
  }
  return <section className="diagnostics-page">
    <header className="page-hero compact"><div><h1>问答诊断</h1><p>查看当前系统保存的问答记录，定位问题发生在哪一步。</p></div></header>
    <div className="source-filter">{Object.entries(trafficLabel).map(([value, label]) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}{overview?.traffic_counts && value !== 'ALL' ? `（${overview.traffic_counts[value] || 0}）` : ''}</button>)}</div>
    {error && <p className="runtime-error">{error}</p>}{loading && <p>正在读取问答记录…</p>}
    {!loading && !error && overview && <>
      <div className="runtime-metrics"><article><b>{overview.question_runs}</b><span>当前筛选记录数</span></article><article><b>{overview.answer_success_rate == null ? '暂无数据' : `${(overview.answer_success_rate * 100).toFixed(1)}%`}</b><span>已回答记录比例</span></article><article><b>{String(overview.benchmark.total_questions ?? '未测量')}</b><span>独立评测问题数</span></article><article><b>{Object.values(overview.audit_files).filter(Boolean).length}/{Object.keys(overview.audit_files).length}</b><span>已载入历史评测材料</span></article></div>
      <p>已回答记录比例不代表答案正确率。技术检查不计入真实业务使用；旧记录无法确认来源时保留为未分类。</p>
      <div className="diagnostic-grid"><article className="panel diagnostic-card"><h2>历史质量评测</h2><p>{overview.historical_evaluation_note}</p>{overview.quality_funnel.map(item => <div className="funnel-row" key={item.stage}><span>{stageLabel[item.stage] || item.stage}</span><b>{item.rate == null ? '未测量' : `${(item.rate * 100).toFixed(1)}%`}</b></div>)}</article><article className="panel diagnostic-card"><h2>当前筛选的问题分布</h2>{overview.failure_distribution.length ? overview.failure_distribution.map(item => <div className="funnel-row" key={item.code}><span>{item.code}</span><b>{item.count}</b></div>) : <p className="empty-runtime">当前筛选没有标记为异常的记录。</p>}</article></div>
      <article className="panel diagnostic-card"><h2>最近问答</h2><div className="diagnostic-questions">{questions.map(item => <button key={item.query_run_id} onClick={() => void inspect(item.query_run_id)}><span>{item.question}</span><small>{trafficLabel[item.traffic_kind] || '未分类'} · {item.answer_status} · {item.latency?.total_ms?.toFixed?.(0) || '?'} ms</small></button>)}</div>{!questions.length && <p className="empty-runtime">当前筛选没有问答记录。</p>}</article>
    </>}
    {trace && <article className="panel diagnostic-card trace-detail"><header><h2>这条问答的详细记录</h2><button onClick={() => setTrace(null)}>关闭</button></header><pre>{JSON.stringify(trace, null, 2)}</pre></article>}
  </section>
}
