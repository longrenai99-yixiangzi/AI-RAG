import { useEffect, useState } from 'react'

type Funnel = { stage: string; rate: number | null; status: string }
type Failure = { code: string; count: number }
type Question = { query_run_id: string; timestamp: string; question: string; answer_status: string; failure: { failure_stage?: string; failure_code?: string; failure_reason?: string }; counts?: Record<string, number>; latency?: { total_ms?: number } }
type Overview = { question_runs: number; answer_success_rate: number | null; quality_funnel: Funnel[]; failure_distribution: Failure[]; benchmark: Record<string, unknown>; audit_files: Record<string, boolean> }

export function Diagnostics() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([
      fetch('/api/v2/knowledge/diagnostics/overview', { cache: 'no-store' }).then((response) => response.ok ? response.json() : Promise.reject()),
      fetch('/api/v2/knowledge/diagnostics/questions?limit=50', { cache: 'no-store' }).then((response) => response.ok ? response.json() : Promise.reject()),
    ]).then(([summary, list]) => { setOverview(summary); setQuestions(list.items || []) }).catch(() => setError('诊断数据暂时不可用，请检查8010服务。'))
  }, [])
  async function inspect(id: string) {
    setError('')
    try {
      const response = await fetch(`/api/v2/knowledge/diagnostics/questions/${encodeURIComponent(id)}`, { cache: 'no-store' })
      if (!response.ok) throw new Error()
      setTrace((await response.json()).trace)
    } catch { setError('该次问答的完整Trace不存在。') }
  }
  if (error && !overview) return <p className="runtime-error">{error}</p>
  return <section className="diagnostics-page">
    <header className="page-hero compact"><div><span className="eyebrow">QUALITY TRACE</span><h1>问答诊断</h1><p>从来源、解析、检索、核验到回答，定位每次成功或失败发生在哪一层。</p></div></header>
    {error && <p className="runtime-error">{error}</p>}
    {overview && <>
      <div className="runtime-metrics"><article><b>{overview.question_runs}</b><span>已记录问答</span></article><article><b>{overview.answer_success_rate == null ? '待测' : `${(overview.answer_success_rate * 100).toFixed(1)}%`}</b><span>当前Trace回答率</span></article><article><b>{String(overview.benchmark.total_questions ?? '待建')}</b><span>Benchmark问题</span></article><article><b>{Object.values(overview.audit_files).filter(Boolean).length}/{Object.keys(overview.audit_files).length}</b><span>审计模块已有结果</span></article></div>
      <div className="diagnostic-grid"><article className="panel diagnostic-card"><h2>质量漏斗</h2>{overview.quality_funnel.map((item) => <div className="funnel-row" key={item.stage}><span>{item.stage}</span><b>{item.rate == null ? '待测' : `${(item.rate * 100).toFixed(1)}%`}</b><small>{item.status}</small></div>)}</article><article className="panel diagnostic-card"><h2>失败分布</h2>{overview.failure_distribution.length ? overview.failure_distribution.map((item) => <div className="funnel-row" key={item.code}><span>{item.code}</span><b>{item.count}</b></div>) : <p className="empty-runtime">暂无失败Trace。</p>}</article></div>
    </>}
    <article className="panel diagnostic-card"><h2>最近问答</h2><div className="diagnostic-questions">{questions.map((item) => <button key={item.query_run_id} onClick={() => void inspect(item.query_run_id)}><span>{item.question}</span><small>{item.failure?.failure_code || 'NO_FAILURE'} · {item.answer_status} · {item.latency?.total_ms?.toFixed?.(0) || '?'} ms</small></button>)}</div></article>
    {trace && <article className="panel diagnostic-card trace-detail"><header><h2>单题全链路</h2><button onClick={() => setTrace(null)}>关闭</button></header><pre>{JSON.stringify(trace, null, 2)}</pre></article>}
  </section>
}
