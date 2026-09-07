import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'

type Citation = { citation_id: string; file_name?: string; source_path?: string; display_location?: string; excerpt?: string; location?: Record<string, unknown> }
type Claim = { claim_id: string; rendered_claim_text: string; claim_type: string }
type V2Result = { query_id: string; answer: string; answer_status: string; status_label: string; citations: Citation[]; claims: Claim[]; growth_candidate_ids: string[]; latency: { total_ms: number }; debug: unknown }
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string; result?: V2Result }
type FeedbackDraft = { feedback_type: string; comment: string; source_path: string; source_location: string; expected_answer: string; required_terms: string[] }
type FeedbackClosure = { candidate_id: string; question: string; feedback_type?: string; closure_status: string; feedback_event?: Partial<FeedbackDraft>; regression_case?: { ready?: boolean; required_terms?: string[]; regression_ready_reason?: string; source_runtime_status?: string; invalid_required_terms?: string[] }; latest_regression?: { regression_status?: string } }

const EXAMPLES = ['设计任务书需要包含哪些内容？', '设计创效如何计算？', '自动喷淋系统管材有哪些方案可以比选？', '2025年公司设计创效情况如何？', '某项目有哪些设计价值创造点？']
const STORAGE_KEY = 'v2_trial_ai_chat_messages'
const FEEDBACK_DRAFT_KEY = 'v2_trial_feedback_draft_'
const COMPLETED_CLOSURE_STATUSES = new Set(['CLOSED', 'REJECTED', 'DEFERRED'])

function emptyFeedback(): FeedbackDraft {
  return { feedback_type: '回答不完整', comment: '', source_path: '', source_location: '', expected_answer: '', required_terms: [] }
}

function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean))]
}

function feedbackDraftKey(queryId: string): string {
  return `${FEEDBACK_DRAFT_KEY}${queryId}`
}

function loadFeedbackDraft(result?: V2Result): { draft: FeedbackDraft; terms: string } {
  const empty = { draft: emptyFeedback(), terms: '' }
  if (!result?.query_id) return empty
  try {
    const saved = JSON.parse(localStorage.getItem(feedbackDraftKey(result.query_id)) || 'null') as { draft?: Partial<FeedbackDraft>; terms?: string } | null
    if (!saved) return empty
    return { draft: { ...emptyFeedback(), ...(saved.draft || {}), required_terms: [] }, terms: typeof saved.terms === 'string' ? saved.terms : '' }
  } catch { return empty }
}

export function AIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages())
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Citation | null>(null)
  const [feedback, setFeedback] = useState('')
  const [closures, setClosures] = useState<FeedbackClosure[]>([])
  const controller = useRef<AbortController | null>(null)
  const history = useMemo(() => messages.filter((item) => item.role === 'user'), [messages])

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40))) }, [messages])
  useEffect(() => { void refreshClosures() }, [])

  async function refreshClosures() {
    try {
      const response = await fetch('/api/v2/feedback-closures')
      const payload = await response.json() as { closures?: FeedbackClosure[] }
      if (response.ok) setClosures(payload.closures || [])
    } catch { /* 闭环队列加载失败不应影响问答。 */ }
  }

  async function send(value = question) {
    const text = value.trim()
    if (!text || loading) return
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', text }
    setMessages((items) => [...items, userMessage])
    setQuestion('')
    setFeedback('')
    setLoading(true)
    controller.current = new AbortController()
    try {
      const response = await fetch('/api/v2/query', { method: 'POST', signal: controller.current.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, trial_user: 'reviewer-001' }) })
      const result = await response.json() as V2Result
      if (!response.ok) throw new Error(result.answer || '问答服务暂时不可用')
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', text: result.answer, result }])
      setSelected(result.citations[0] || null)
    } catch (error) {
      const failure = error instanceof DOMException && error.name === 'AbortError' ? '本次问答已停止。' : '问答服务暂时不可用，请稍后重试。'
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', text: failure }])
    } finally {
      setLoading(false)
      controller.current = null
    }
  }

  async function submitFeedback(result: V2Result, input: FeedbackDraft | string) {
    const draft = typeof input === 'string' ? { ...emptyFeedback(), feedback_type: input } : input
    setFeedback('正在记录反馈…')
    try {
      const response = await fetch('/api/v2/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query_id: result.query_id, trial_user: 'reviewer-001', ...draft }) })
      const payload = await response.json() as { feedback_event?: { growth_candidate_id?: string } }
      setFeedback(response.ok ? (payload.feedback_event?.growth_candidate_id ? `反馈已进入待审核修复队列：${payload.feedback_event.growth_candidate_id}` : '反馈已记录。') : '反馈暂未保存，请稍后重试。')
      if (response.ok) {
        localStorage.removeItem(feedbackDraftKey(result.query_id))
        void refreshClosures()
      }
    } catch { setFeedback('反馈暂未写入服务器，内容已暂存本机；服务恢复后可重新提交。') }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() }
  }

  return <section className="ai-chat-page">
    <aside className="chat-history panel">
      <div className="chat-side-head"><div><span className="eyebrow">V2 INTERNAL TRIAL</span><h2>对话历史</h2></div><button onClick={() => { setMessages([]); setSelected(null); setFeedback('') }}>+ 新建对话</button></div>
      <div className="history-group"><b>今天</b>{history.length ? history.slice().reverse().map((item) => <button key={item.id} onClick={() => setQuestion(item.text)}>{item.text}</button>) : <span>尚无对话记录</span>}</div>
      <p className="history-note">仅保存本机试用会话，不写入正式知识库。</p>
    </aside>
    <main className="chat-main panel">
      <header className="chat-hero"><span className="eyebrow">AI KNOWLEDGE Q&A</span><h1>AI知识问答</h1><p>基于企业知识库的可验证问答</p></header>
      <div className="chat-flow">{messages.length === 0 && <div className="chat-empty"><h2>从已有资料中查证，再回答</h2><p>你可以问我关于设计管理、技术管理、项目案例、方案比选、制度等知识。</p><div>{EXAMPLES.map((item) => <button key={item} onClick={() => void send(item)}>{item}</button>)}</div></div>}{messages.map((message) => message.role === 'user' ? <div className="user-message" key={message.id}>{message.text}</div> : <AnswerCard key={message.id} message={message} onCitation={setSelected} onFeedback={submitFeedback} />)}{loading && <div className="answer-card loading-answer"><b>正在检索知识库…</b><span>正在查找相关文档、核验证据并生成回答。</span></div>}</div>
      <footer className="chat-composer"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="输入设计管理问题，Enter发送，Shift+Enter换行" /><div><span>V2 Verified · 8010内部试用</span><button className="text-button" onClick={() => { controller.current?.abort() }} disabled={!loading}>停止</button><button className="text-button" onClick={() => { setMessages([]); setSelected(null) }}>清空当前会话</button><button className="primary-button" onClick={() => void send()} disabled={loading}>发送</button></div></footer>
    </main>
    <aside className="source-detail panel">
      <div className="source-detail-head"><span className="eyebrow">CITATION</span><h2>来源详情</h2></div>
      {selected ? <SourceDetail citation={selected} /> : <div className="source-empty">点击回答中的引用来源，可查看文件位置和证据详情。</div>}
      <FeedbackClosurePanel closures={closures} onRefresh={refreshClosures} />
      {feedback && <p className="feedback-toast">{feedback}</p>}
    </aside>
  </section>
}

function AnswerCard({ message, onCitation, onFeedback }: { message: ChatMessage; onCitation: (citation: Citation) => void; onFeedback: (result: V2Result, input: FeedbackDraft | string) => Promise<void> }) {
  const result = message.result
  const [draft, setDraft] = useState<FeedbackDraft>(() => loadFeedbackDraft(message.result).draft)
  if (!result) return <article className="answer-card"><p>{message.text}</p></article>
  const answerResult = result
  const confirmed = result.claims.filter((item) => item.claim_type === 'DIRECT')
  const limitations = result.claims.filter((item) => item.claim_type !== 'DIRECT')
  const conflict = result.answer_status === 'CONFLICTING_ANSWER'
  const partial = result.answer_status === 'PARTIAL_ANSWER'

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    localStorage.setItem(feedbackDraftKey(answerResult.query_id), JSON.stringify({ draft }))
    void onFeedback(answerResult, { ...draft, required_terms: [] })
  }

  return <article className={`answer-card ${partial ? 'partial' : ''} ${conflict ? 'conflict' : ''}`}>
    <header><span className={`answer-status ${result.answer_status.toLowerCase()}`}>{result.status_label}</span><small>{result.latency.total_ms.toFixed(0)} ms</small></header>
    {conflict && <div className="conflict-note"><b>发现不同资料口径</b><span>当前资料不足以安全判断哪一个口径正确对应本问题。</span></div>}
    {partial && <div className="partial-grid"><div><b>已确认内容</b>{confirmed.map((item) => <p key={item.claim_id}>{item.rendered_claim_text}</p>)}</div><div><b>证据不足内容</b>{limitations.map((item) => <p key={item.claim_id}>{item.rendered_claim_text}</p>)}</div></div>}
    {!partial && <div className="answer-body">{message.text}</div>}
    <section className="answer-citations"><b>引用来源</b>{result.citations.map((citation, index) => <button key={citation.citation_id} onClick={() => onCitation(citation)}>[{index + 1}] {citation.file_name} · {citation.display_location}</button>)}</section>
    <footer className="answer-actions">
      <button onClick={() => void onFeedback(result, '回答正确')}>👍 有帮助</button>
      <details className="feedback-editor">
        <summary>提交问题反馈并纳入修复闭环</summary>
        <form onSubmit={submit}>
          <label>反馈类型<select value={draft.feedback_type} onChange={(event) => setDraft({ ...draft, feedback_type: event.target.value })}><option>回答不完整</option><option>答案错误</option><option>引用不对</option><option>没有回答我的问题</option><option>资料缺失</option><option>答案冲突</option></select></label>
          <label>问题说明（必填）<textarea required value={draft.comment} onChange={(event) => setDraft({ ...draft, comment: event.target.value })} placeholder="请写明错在哪里、缺少什么，或正确答案中的关键数字" /></label>
          <label>正确答案或关键事实（可选）<textarea value={draft.expected_answer} onChange={(event) => setDraft({ ...draft, expected_answer: event.target.value })} placeholder="例如：应为21个专业" /></label>
          <small>当前问题、回答和引用已自动附带；来源文件、页码和回归关键事实可在后续反馈闭环中补充。</small>
          <button className="primary-button" type="submit">提交并创建待审核候选</button>
          <small>不会自动修改正式知识库、正式索引或正式问答。</small>
        </form>
      </details>
      <details><summary>查看检索详情</summary><pre>{JSON.stringify(result.debug, null, 2)}</pre></details>
    </footer>
  </article>
}

function FeedbackClosurePanel({ closures, onRefresh }: { closures: FeedbackClosure[]; onRefresh: () => Promise<void> }) {
  const active = closures.filter((closure) => !COMPLETED_CLOSURE_STATUSES.has(closure.closure_status))
  const completed = closures.filter((closure) => COMPLETED_CLOSURE_STATUSES.has(closure.closure_status))
  return <details className="feedback-closure-panel">
    <summary>反馈闭环队列（待处理 {active.length} / 已完成 {completed.length}）</summary>
    <p>确认来源后建立回归题；修复后再运行回归。系统不会自动发布知识。</p>
    {active.length ? active.slice(0, 8).map((closure) => <FeedbackClosureItem key={closure.candidate_id} closure={closure} onRefresh={onRefresh} />) : <span>暂无待处理反馈。</span>}
    {completed.length > 0 && <details className="completed-feedback"><summary>已完成反馈（{completed.length}）</summary>{completed.slice(0, 8).map((closure) => <FeedbackClosureItem key={closure.candidate_id} closure={closure} onRefresh={onRefresh} completed />)}</details>}
  </details>
}

function FeedbackClosureItem({ closure, onRefresh, completed = false }: { closure: FeedbackClosure; onRefresh: () => Promise<void>; completed?: boolean }) {
  const event = closure.feedback_event || {}
  const [sourcePath, setSourcePath] = useState(event.source_path || '')
  const [sourceLocation, setSourceLocation] = useState(event.source_location || '')
  const [terms, setTerms] = useState((event.required_terms || closure.regression_case?.required_terms || []).join('、'))
  const [notice, setNotice] = useState('')

  async function approve() {
    setNotice('正在确认来源…')
    const response = await fetch('/api/v2/growth-review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: closure.candidate_id, trial_user: 'reviewer-001', decision: 'APPROVE', confirmed_source_path: sourcePath, confirmed_source_location: sourceLocation, required_terms: splitTerms(terms), approved_action: 'CREATE_SHADOW_REGRESSION_CASE' }) })
    const payload = await response.json() as { regression_case?: { ready?: boolean; regression_ready_reason?: string } }
    setNotice(response.ok ? (payload.regression_case?.ready ? '已建立回归题；可运行 Shadow 回归验证。' : `已登记来源；${payload.regression_case?.regression_ready_reason || '等待完成 Source Closure 后再运行回归。'}`) : '来源确认未保存。')
    if (response.ok) await onRefresh()
  }

  async function runRegression() {
    setNotice('正在运行 Shadow 回归…')
    const response = await fetch('/api/v2/growth-regression', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: closure.candidate_id, trial_user: 'reviewer-001' }) })
    const payload = await response.json() as { regression?: { regression_status?: string }; regression_status?: string; reason?: string }
    setNotice(response.ok ? `回归结果：${payload.regression?.regression_status || payload.regression_status || 'NOT_READY'}${payload.reason ? `；${payload.reason}` : ''}` : '回归执行失败。')
    if (response.ok) await onRefresh()
  }

  return <article className={`closure-item ${completed ? 'completed' : ''}`}><b>{closure.feedback_type || '业务反馈'} · {closure.closure_status}</b><p>{closure.question}</p>{closure.regression_case?.regression_ready_reason && <small>{closure.regression_case.regression_ready_reason}</small>}{completed ? <small>该反馈已完成闭环，保留为审核记录。</small> : <><input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="确认来源文件路径" /><input value={sourceLocation} onChange={(event) => setSourceLocation(event.target.value)} placeholder="页码、行号或Sheet位置" /><input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="关键事实（逗号分隔）" /><div><button onClick={() => void approve()}>确认来源并建立回归题</button><button onClick={() => void runRegression()} disabled={!closure.regression_case?.ready} title={closure.regression_case?.ready ? '运行 Shadow 回归验证' : '来源尚未进入当前 Shadow 索引，暂不能运行回归'}>运行回归</button></div>{notice && <small>{notice}</small>}</>}</article>
}

function SourceDetail({ citation }: { citation: Citation }) {
  const ext = citation.file_name?.split('.').pop()?.toUpperCase() || '文件'
  return <div className="source-card"><b>{citation.file_name}</b><span>{ext} · {citation.display_location}</span><p>{citation.source_path}</p><h3>Evidence Text</h3><div className="evidence-text">{citation.excerpt || '当前引用未提供可展开的文本摘录。'}</div><details><summary>开发者详情</summary><pre>{JSON.stringify({ citation_id: citation.citation_id, location: citation.location }, null, 2)}</pre></details></div>
}

function loadMessages(): ChatMessage[] {
  try { const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); return Array.isArray(value) ? value : [] } catch { return [] }
}
