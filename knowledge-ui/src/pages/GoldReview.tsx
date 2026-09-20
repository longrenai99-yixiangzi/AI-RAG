import { useEffect, useState } from 'react'

type Candidate = { chunk_id: string; file_name: string; section_path: string; snippet: string }
type GoldItem = { question_id: string; question: string; verification_status: string; acceptable_sources: string[]; acceptable_sections: { section_path?: string; section?: string }[]; review_candidates: Candidate[] }

export function GoldReview() {
  const [items, setItems] = useState<GoldItem[]>([])
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<Record<string, Candidate[]>>({})
  const [sourceInput, setSourceInput] = useState('')
  const [sectionInput, setSectionInput] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => { fetch('/api/v2/gold-review/items?status=PENDING&limit=50', { cache: 'no-store' }).then((r) => r.json()).then((data) => setItems(data.items || [])).catch(() => setNotice('Gold 审核数据暂时不可用。')) }, [])
  const item = items[index]
  useEffect(() => {
    if (!item) return
    setSourceInput(item.acceptable_sources?.[0] || '')
    const section = item.acceptable_sections?.[0]
    setSectionInput(section?.section_path || section?.section || (section ? JSON.stringify(section) : ''))
  }, [item?.question_id])
  function toggle(candidate: Candidate) {
    if (!item) return
    const current = selected[item.question_id] || []
    const exists = current.some((row) => row.chunk_id === candidate.chunk_id)
    setSelected({ ...selected, [item.question_id]: exists ? current.filter((row) => row.chunk_id !== candidate.chunk_id) : [...current, candidate] })
  }
  async function review(status: 'CONFIRMED' | 'PENDING' | 'REJECTED' | 'NO_VALID_EVIDENCE') {
    if (!item) return
    const rows = selected[item.question_id] || []
    const sources = [...new Set([...rows.map((row) => row.file_name), sourceInput.trim()].filter(Boolean))]
    const sections = [...rows.map((row) => ({ section_path: row.section_path, chunk_id: row.chunk_id })), ...(sectionInput.trim() ? [{ section_path: sectionInput.trim() }] : [])]
    const response = await fetch(`/api/v2/gold-review/items/${encodeURIComponent(item.question_id)}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewer: 'reviewer-001', status, acceptable_sources: sources, acceptable_sections: sections, comment: '' }) })
    setNotice(response.ok ? `${item.question_id} 已保存为 ${status}` : '保存失败。')
    if (response.ok && index < items.length - 1) setIndex(index + 1)
  }
  if (!item) return <section className="gold-review-page"><header className="page-hero compact"><div><span className="eyebrow">RETRIEVAL GOLD</span><h1>Gold 审核</h1><p>{notice || '暂无待审核题目。'}</p></div></header></section>
  const picked = selected[item.question_id] || []
  return <section className="gold-review-page"><header className="page-hero compact"><div><span className="eyebrow">RETRIEVAL GOLD · {index + 1}/{items.length}</span><h1>Source / Section 人工确认</h1><p>题目适合评估不等于来源真值；只有人工确认后才进入正式指标。</p></div></header><article className="panel diagnostic-card"><span className="eyebrow">{item.question_id} · {item.verification_status}</span><h2>{item.question}</h2><div className="gold-manual-fields"><label>正确来源文件<input value={sourceInput} onChange={(event) => setSourceInput(event.target.value)} placeholder="文件名或完整来源路径" /></label><label>正确章节 / 页码<input value={sectionInput} onChange={(event) => setSectionInput(event.target.value)} placeholder="章节路径、页码、段落或 Sheet" /></label></div><div className="diagnostic-questions">{item.review_candidates?.length ? item.review_candidates.map((candidate) => { const active = picked.some((row) => row.chunk_id === candidate.chunk_id); return <button className={active ? 'selected' : ''} key={candidate.chunk_id} onClick={() => toggle(candidate)}><span>{candidate.file_name} · {candidate.section_path || '章节待确认'}</span><small>{candidate.snippet || '当前 staging 未找到可展示摘录'}</small></button> }) : <p className="empty-runtime">当前 staging 没有候选摘录；可直接填写正确来源和章节。</p>}</div><div className="action-row"><button onClick={() => void review('CONFIRMED')} disabled={!picked.length && !(sourceInput.trim() && sectionInput.trim())}>✓ 确认正确来源/章节</button><button onClick={() => void review('PENDING')}>△ 暂缓</button><button onClick={() => void review('REJECTED')}>✕ 驳回</button><button onClick={() => void review('NO_VALID_EVIDENCE')}>? 无有效证据</button><button onClick={() => setIndex(Math.min(items.length - 1, index + 1))}>下一题</button></div>{notice && <small>{notice}</small>}</article></section>
}
