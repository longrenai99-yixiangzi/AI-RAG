import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type Candidate = {
  candidate_id: string; question: string; growth_type: string; current_answer_status: string;
  reason: string; recommended_action: string; occurrence_count: number; candidate_hash?: string;
  effective_review_status: string; related_query_ids?: string[];
  evidence_snapshot?: { sources?: { source_id?: string; source_version?: string; file_name?: string; excerpt?: string }[] };
}
const kindLabel: Record<string, string> = { KNOWLEDGE_GROWTH: '来源待核对', RETRIEVAL_GROWTH: '读取与检索待修', QA_GROWTH: '回答与引用待修', EVIDENCE_REVIEW_CANDIDATE: '依据与回答待核', CONFLICT_REVIEW_CANDIDATE: '冲突待裁定' }
const statusLabel: Record<string, string> = { PROPOSED: '待核对', APPROVED: '已审核，待受控处理', REVIEWED: '已复核', REJECTED: '已驳回', DEFERRED: '已暂缓' }

export function GrowthQueue() {
  const [rows, setRows] = useState<Candidate[]>([])
  const [filter, setFilter] = useState('PENDING')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v2/growth-candidates?include_reviewed=true', { cache: 'no-store', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(); return response.json() })
      .then(payload => { if (!Array.isArray(payload.candidates)) throw new Error(); setRows(payload.candidates) })
      .catch(() => { if (!controller.signal.aborted) setError('候选记录读取失败，请检查服务；这不表示没有待办。') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])
  const shown = rows.filter(row => filter === 'ALL' || row.effective_review_status === 'PROPOSED')
  function download() {
    const text = ['# 知识补充与改进清单', '', '以下为待核对线索，不是已发布知识，也不作为答案依据。', ...shown.flatMap((row, index) => ['', `## ${index + 1}. ${row.question}`, '', `类别：${kindLabel[row.growth_type] || '待进一步定位'}`, `状态：${statusLabel[row.effective_review_status] || '待核对'}`, `记录情况：${row.reason}`, `下一步：${row.recommended_action}`, `来源：${(row.evidence_snapshot?.sources || []).map(source => source.file_name || '待核对').join('；') || '待核对'}`, `追溯编号：${row.candidate_id}`])].join('\n')
    const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = '知识补充与改进清单.md'; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section>
    <header className="page-hero compact"><div><h1>知识补充与改进</h1><p>从真实提问和反馈整理待办。这里只记录线索，不会把答案、草稿或计算结果自动变成知识。</p></div></header>
    <p>先分清缺资料、正常拒答和系统没答好。技术检查不进入此清单；已审核也不等于已进入问答。</p>
    <div className="source-filter"><button className={filter === 'PENDING' ? 'active' : ''} onClick={() => setFilter('PENDING')}>待核对</button><button className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>全部候选</button><button onClick={download} disabled={loading || !!error || !shown.length}>下载当前候选清单</button></div>
    {loading && <p>正在读取候选记录…</p>}{error && <p className="runtime-error">{error}</p>}
    {!loading && !error && <p>当前显示 {shown.length} 条。重复提问合并显示，出处和提问记录保留。</p>}
    {!loading && !error && !shown.length && <p className="empty-runtime">当前筛选范围没有候选。已回答并不自动成为经过审核的知识。</p>}
    {shown.map(row => <article className="panel diagnostic-card" key={row.candidate_id}>
      <h2>{row.question}</h2><p>{kindLabel[row.growth_type] || '待进一步定位'} · {statusLabel[row.effective_review_status] || '待核对'} · {row.occurrence_count} 次提问</p>
      <p>{row.reason}</p><p>下一步：{row.recommended_action}</p>
      <details><summary>查看来源与提问记录</summary>
        {(row.evidence_snapshot?.sources || []).map((source, index) => <div key={index}><b>{source.file_name || '来源名称待核'}</b>
          {source.source_id && source.source_version ? <p><Link to={`/read?source=${encodeURIComponent(source.source_id)}&version=${encodeURIComponent(source.source_version)}`}>核对同版来源</Link></p> : <p>本条来源版本尚待核对。</p>}
          <p>{source.excerpt || '历史记录没有保留可直接采用的原文摘录，需打开来源核对。'}</p></div>)}
        <small>候选版本：{row.candidate_hash?.slice(0, 8) || '待核对'} · 关联记录：{row.related_query_ids?.length || 0}</small>
      </details>
      <p>由维护人员核对原因和原件后，准备具体补充或修复。涉及业务事实、冲突或正式采用时，再按实际需要请你决定。</p>
    </article>)}
  </section>
}
