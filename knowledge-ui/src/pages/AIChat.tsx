import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

type Citation = { citation_id: string; evidence_id?: string; source_id?: string; source_version?: string; file_name?: string; source_path?: string; display_location?: string; excerpt?: string; location?: Record<string, unknown> }
type Claim = { claim_id: string; rendered_claim_text: string; claim_type: string }
type ReviewCandidate = Citation & { role?: string; scope?: Record<string, string> }
type V2Result = { query_id: string; query_run_id: string; question: string; resolved_question?: string; answer: string; answer_status: string; status_label: string; citations: Citation[]; claims: Claim[]; growth_candidate_ids: string[]; latency: { total_ms: number }; failure_reason?: string; failure_message?: string; review_candidates?: ReviewCandidate[]; debug: unknown }
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string; result?: V2Result }
type FeedbackDraft = {
  feedback_type: string
  comment: string
  source_path: string
  source_location: string
  expected_answer: string
  required_terms: string
  standard_question: string
  similar_questions: string
  negative_questions: string
  applicability: string
  idempotency_key: string
}
type Workflow = {
  feedback_id: string
  question: string
  query_run_id?: string
  feedback_type: string
  comment?: string
  source_path?: string
  source_location?: string
  expected_answer?: string
  required_terms?: string[]
  standard_question?: string
  similar_questions?: string[]
  negative_questions?: string[]
  applicability?: string
  status: string
  closure_status: string
  knowledge_id?: string
  source_runtime_status?: string
  latest_regression?: { regression_status?: string }
  failure_stage?: string
  failure_code?: string
  root_cause?: string
  system_fix_required?: boolean
  standard_answer_required?: boolean
}

const EXAMPLES = ['中建三局二公司设计与技术支持中心的组织架构是什么样的？', '设计任务书需要包含哪些内容？', '自动喷淋系统管材有哪些方案可以比选？', '2025年公司设计创效情况如何？']
const STORAGE_KEY = 'v2_trial_ai_chat_messages'
const CONVERSATION_KEY = 'v2_trial_conversation_id'
const QUESTION_DRAFT_KEY = 'v2_trial_ai_chat_draft'
const FEEDBACK_DRAFT_KEY = 'v2_trial_feedback_draft_'
const PERSISTED_MESSAGE_LIMIT = 20
const workflowLabel: Record<string, string> = {
  RECORDED: '已记录，待核对',
  APPROVED: '来源已确认，待生效',
  ACTIVE: '更正已生效',
  REJECTED: '已驳回',
  DEFERRED: '已暂缓',
  WITHDRAWN: '更正知识已撤回',
  REVIEW_REQUIRED: '来源版本变化，待复核',
  SOURCE_CLOSURE_REQUIRED: '来源正文尚未入库',
}

function emptyFeedback(question = ''): FeedbackDraft {
  return { feedback_type: '回答不完整', comment: '', source_path: '', source_location: '', expected_answer: '', required_terms: '', standard_question: question, similar_questions: '', negative_questions: '', applicability: '', idempotency_key: crypto.randomUUID() }
}

function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[，,、\n]/).map((item) => item.trim()).filter(Boolean))]
}

function feedbackDraftKey(queryRunId: string): string {
  return `${FEEDBACK_DRAFT_KEY}${queryRunId}`
}

function compactMessage(message: ChatMessage): ChatMessage {
  if (message.role === 'user' || !message.result) return { id: message.id, role: message.role, text: message.text }
  const result = message.result
  return {
    id: message.id,
    role: 'assistant',
    text: message.text,
    result: {
      query_id: result.query_id,
      query_run_id: result.query_run_id,
      question: result.question,
      resolved_question: result.resolved_question,
      answer: result.answer,
      answer_status: result.answer_status,
      status_label: result.status_label,
      citations: Array.isArray(result.citations) ? result.citations.slice(0, 8) : [],
      claims: Array.isArray(result.claims) ? result.claims.slice(0, 12) : [],
      growth_candidate_ids: Array.isArray(result.growth_candidate_ids) ? result.growth_candidate_ids : [],
      latency: { total_ms: Number(result.latency?.total_ms) || 0 },
      failure_message: result.failure_message,
      review_candidates: Array.isArray(result.review_candidates) ? result.review_candidates.slice(0, 8) : [],
      debug: {},
    },
  }
}

function persistMessages(messages: ChatMessage[]) {
  const compact = messages.slice(-PERSISTED_MESSAGE_LIMIT).map(compactMessage)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(compact))
  } catch {
    try {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(compact.filter((item) => item.role === 'user').slice(-8)))
    } catch {
      // Quota errors must never take down the Q&A page.
    }
  }
}

function loadFeedbackDraft(result: V2Result): FeedbackDraft {
  try {
    const saved = JSON.parse(localStorage.getItem(feedbackDraftKey(result.query_run_id)) || 'null') as Partial<FeedbackDraft> | null
    const citation = Array.isArray(result.citations) ? result.citations[0] : undefined
    return { ...emptyFeedback(result.question), ...(citation ? { source_path: citation.source_path || '', source_location: citation.display_location || '' } : {}), ...(saved || {}) }
  } catch { return emptyFeedback(result.question) }
}

export function AIChat() {
  const [params] = useSearchParams()
  const nodeId = params.get('node') || ''
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages())
  const [conversationId, setConversationId] = useState(() => localStorage.getItem(CONVERSATION_KEY) || crypto.randomUUID())
  const [question, setQuestion] = useState(() => localStorage.getItem(QUESTION_DRAFT_KEY) || '')
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Citation | null>(null)
  const [notice, setNotice] = useState('')
  const [workflow, setWorkflow] = useState<Workflow[]>([])
  const controller = useRef<AbortController | null>(null)
  const history = useMemo(() => messages.filter((item) => item.role === 'user'), [messages])
  const currentRunId = [...messages].reverse().find((item) => item.result)?.result?.query_run_id

  useEffect(() => { persistMessages(messages) }, [messages])
  useEffect(() => { localStorage.setItem(CONVERSATION_KEY, conversationId) }, [conversationId])
  useEffect(() => { question ? localStorage.setItem(QUESTION_DRAFT_KEY, question) : localStorage.removeItem(QUESTION_DRAFT_KEY) }, [question])
  useEffect(() => { void refreshWorkflow() }, [])

  async function refreshWorkflow() {
    try {
      const response = await fetch('/api/v2/feedback-workflow', { cache: 'no-store' })
      const payload = await response.json() as { items?: Workflow[] }
      if (response.ok) setWorkflow(Array.isArray(payload.items) ? payload.items : [])
    } catch { setNotice('反馈记录暂时无法读取。') }
  }

  async function send(value = question) {
    const text = value.trim()
    if (!text || loading) return
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'user', text }])
    setQuestion('')
    setNotice('')
    setLoading(true)
    controller.current = new AbortController()
    try {
      const response = await fetch('/api/v2/query', { method: 'POST', signal: controller.current.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, trial_user: 'reviewer-001', conversation_id: conversationId, node_id: nodeId }) })
      const result = await response.json() as V2Result
      if (!response.ok) throw new Error(result.answer || '问答服务暂时不可用')
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', text: result.answer, result }])
      setSelected(Array.isArray(result.citations) ? result.citations[0] || null : null)
    } catch (error) {
      const failure = error instanceof DOMException && error.name === 'AbortError' ? '本次问答已停止。' : '问答服务暂时不可用，请稍后重试。'
      setMessages((items) => [...items, { id: crypto.randomUUID(), role: 'assistant', text: failure }])
      setQuestion(text)
    } finally {
      setLoading(false)
      controller.current = null
    }
  }

  async function submitFeedback(result: V2Result, draft: FeedbackDraft): Promise<boolean> {
    setNotice('正在记录更正…')
    try {
      const response = await fetch('/api/v2/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query_id: result.query_id,
          query_run_id: result.query_run_id,
          trial_user: 'reviewer-001',
          feedback_type: draft.feedback_type,
          comment: draft.comment,
          source_path: draft.source_path,
          source_location: draft.source_location,
          expected_answer: draft.expected_answer,
          required_terms: splitTerms(draft.required_terms),
          standard_question: draft.standard_question,
          similar_questions: splitTerms(draft.similar_questions),
          negative_questions: splitTerms(draft.negative_questions),
          applicability: draft.applicability,
          idempotency_key: draft.idempotency_key,
        }),
      })
      const payload = await response.json() as { deduplicated?: boolean }
      if (!response.ok) throw new Error('save failed')
      localStorage.removeItem(feedbackDraftKey(result.query_run_id))
      setNotice(payload.deduplicated ? '该次提交已记录，无需重复创建。' : '更正已记录，请在右侧核对来源并发布到试用知识。')
      await refreshWorkflow()
      return true
    } catch {
      setNotice('更正暂未写入服务器，草稿仍保存在本机。')
      return false
    }
  }

  function newConversation() {
    const id = crypto.randomUUID()
    setConversationId(id)
    setMessages([])
    setSelected(null)
    setNotice('')
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(QUESTION_DRAFT_KEY)
    setQuestion('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() }
  }

  const relevantWorkflow = workflow.filter((item) => !currentRunId || item.query_run_id === currentRunId)
  return <section className="ai-chat-page">
    <aside className="chat-history panel">
      <div className="chat-side-head"><div><span className="eyebrow">V2 INTERNAL TRIAL</span><h2>对话历史</h2></div><button onClick={newConversation}>+ 新建对话</button></div>
      <div className="history-group"><b>当前会话</b>{history.length ? history.slice().reverse().map((item) => <button key={item.id} onClick={() => setQuestion(item.text)}>{item.text}</button>) : <span>尚无对话记录</span>}</div>
      <p className="history-note">历史问题只帮助恢复追问主体；回答事实仍来自可核查证据。</p>
    </aside>
    <main className="chat-main panel">
      <header className="chat-hero"><span className="eyebrow">AI KNOWLEDGE Q&A</span><h1>AI知识问答</h1><p>{nodeId ? `当前从知识节点 ${nodeId} 发起；答案仍需可核查来源。` : '基于当前 8010 试用知识范围的可验证问答'}</p></header>
      <div className="chat-flow">{messages.length === 0 && <div className="chat-empty"><h2>先查证，再回答</h2><p>回答中的制度、数字和项目事实都应能回到原文位置。</p><div>{EXAMPLES.map((item) => <button key={item} onClick={() => void send(item)}>{item}</button>)}</div></div>}{messages.map((message) => message.role === 'user' ? <div className="user-message" key={message.id}>{message.text}</div> : <AnswerCard key={message.id} message={message} onCitation={setSelected} onFeedback={submitFeedback} />)}{loading && <div className="answer-card loading-answer"><b>正在检索知识库…</b><span>正在查找相关文档、核验证据并生成回答。</span></div>}</div>
      <footer className="chat-composer"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="输入设计管理问题，Enter发送，Shift+Enter换行" /><div><span>V2 Verified · 8010内部试用</span><button className="text-button" onClick={() => controller.current?.abort()} disabled={!loading}>停止</button><button className="text-button" onClick={() => setMessages([])}>清空当前会话</button><button className="primary-button" onClick={() => void send()} disabled={loading}>发送</button></div></footer>
    </main>
    <aside className="source-detail panel">
      <div className="source-detail-head"><span className="eyebrow">CITATION & CORRECTION</span><h2>来源与更正</h2></div>
      {selected ? <SourceDetail citation={selected} /> : <div className="source-empty">点击回答中的引用来源，可查看真实文件、位置和证据。</div>}
      <FeedbackWorkflow items={relevantWorkflow} onRefresh={refreshWorkflow} />
      {notice && <p className="feedback-toast">{notice}</p>}
    </aside>
  </section>
}

function AnswerCard({ message, onCitation, onFeedback }: { message: ChatMessage; onCitation: (citation: Citation) => void; onFeedback: (result: V2Result, draft: FeedbackDraft) => Promise<boolean> }) {
  const result = message.result
  const [draft, setDraft] = useState<FeedbackDraft>(() => result ? loadFeedbackDraft(result) : emptyFeedback())
  const [submitting, setSubmitting] = useState(false)
  if (!result) return <article className="answer-card"><p>{message.text}</p></article>
  const answerResult = result
  const claims = Array.isArray(answerResult.claims) ? answerResult.claims : []
  const citations = Array.isArray(answerResult.citations) ? answerResult.citations : []
  const status = String(answerResult.answer_status || 'UNKNOWN')
  const latencyMs = Number(answerResult.latency?.total_ms) || 0
  const confirmed = claims.filter((item) => item.claim_type === 'DIRECT')
  const limitations = claims.filter((item) => item.claim_type !== 'DIRECT')
  const partial = answerResult.answer_status === 'PARTIAL_ANSWER'
  const conflict = answerResult.answer_status === 'CONFLICTING_ANSWER'

  function change(value: Partial<FeedbackDraft>) {
    const next = { ...draft, ...value }
    setDraft(next)
    localStorage.setItem(feedbackDraftKey(answerResult.query_run_id), JSON.stringify(next))
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    const saved = await onFeedback(answerResult, draft)
    if (saved) setDraft(emptyFeedback(answerResult.question))
    setSubmitting(false)
  }

  return <article className={`answer-card ${partial ? 'partial' : ''} ${conflict ? 'conflict' : ''}`}>
    <header><span className={`answer-status ${status.toLowerCase()}`}>{result.status_label || status}</span><small>{latencyMs.toFixed(0)} ms</small></header>
    {partial && <div className="partial-grid"><div><b>已确认内容</b>{confirmed.map((item) => <p key={item.claim_id}>{item.rendered_claim_text}</p>)}</div><div><b>证据不足内容</b>{limitations.map((item) => <p key={item.claim_id}>{item.rendered_claim_text}</p>)}</div></div>}
    {!partial && <div className="answer-body">{message.text}</div>}
    {result.failure_message && <p className="runtime-error">{result.failure_message}</p>}
    {result.resolved_question && result.resolved_question !== result.question && <small className="resolved-question">本轮检索问题：{result.resolved_question}</small>}
    <section className="answer-citations"><b>引用来源</b>{citations.length ? citations.map((citation, index) => <button key={citation.citation_id || `${index}`} onClick={() => onCitation(citation)}>[{index + 1}] {citation.file_name} · {citation.display_location}</button>) : <span>本次没有形成可定位引用。</span>}</section>
    <footer className="answer-actions"><details className="feedback-editor"><summary>纠正这条回答</summary><form onSubmit={submit}>
      <label>反馈类型<select value={draft.feedback_type} onChange={(event) => change({ feedback_type: event.target.value })}><option>回答不完整</option><option>答案错误</option><option>引用不对</option><option>没有回答我的问题</option><option>资料缺失</option><option>答案冲突</option></select></label>
      <label>问题说明（必填）<textarea required value={draft.comment} onChange={(event) => change({ comment: event.target.value })} placeholder="错在哪里、缺少什么或适用范围有什么问题" /></label>
      <label>正确答案或关键事实<textarea value={draft.expected_answer} onChange={(event) => change({ expected_answer: event.target.value })} /></label>
      {!!answerResult.review_candidates?.length && <div className="review-candidates"><b>已召回但尚未通过核验的候选来源</b>{answerResult.review_candidates.map((item) => <button type="button" key={item.evidence_id} onClick={() => change({ source_path: item.source_path || '', source_location: item.display_location || '' })}>{item.file_name} · {item.display_location || '位置待核对'}</button>)}<small>候选不等于正确来源，请核对原文后再提交。</small></div>}
      <label>来源文件路径<input value={draft.source_path} onChange={(event) => change({ source_path: event.target.value })} placeholder="确认后只读接入该文件" /></label>
      <label>页码、段落或表格位置<input value={draft.source_location} onChange={(event) => change({ source_location: event.target.value })} placeholder="例如：第1页" /></label>
      <label>必须出现的关键事实<input value={draft.required_terms} onChange={(event) => change({ required_terms: event.target.value })} placeholder="用逗号分隔" /></label>
      <details><summary>相似问、反例与适用范围</summary><label>标准问题<input value={draft.standard_question} onChange={(event) => change({ standard_question: event.target.value })} /></label><label>相似问<textarea value={draft.similar_questions} onChange={(event) => change({ similar_questions: event.target.value })} placeholder="一行一个或逗号分隔" /></label><label>容易误套的反例<textarea value={draft.negative_questions} onChange={(event) => change({ negative_questions: event.target.value })} /></label><label>适用范围<textarea value={draft.applicability} onChange={(event) => change({ applicability: event.target.value })} placeholder="主体、时间、条件、必设/选设边界" /></label></details>
      <button className="primary-button" type="submit" disabled={submitting}>{submitting ? '正在提交…' : '保存更正并进入核对'}</button>
      <small>保存不等于生效；核对来源并发布到试用知识后，普通问答才会使用。</small>
    </form></details><details><summary>查看检索诊断</summary><pre>{JSON.stringify(result.debug, null, 2)}</pre></details></footer>
  </article>
}

function FeedbackWorkflow({ items, onRefresh }: { items: Workflow[]; onRefresh: () => Promise<void> }) {
  const safeItems = Array.isArray(items) ? items.filter((item) => item && typeof item === 'object') : []
  return <details className="feedback-closure-panel"><summary>本题更正记录（{safeItems.length}）</summary><p>知识缺失经来源核对后发布；系统能力失败进入缺陷池修复。</p><div className="workflow-scroll">{safeItems.slice(0, 4).map((item) => <WorkflowItem key={item.feedback_id} item={item} onRefresh={onRefresh} />)}{!safeItems.length && <span className="source-empty">本题暂无更正记录。</span>}</div></details>
}

function WorkflowItem({ item, onRefresh }: { item: Workflow; onRefresh: () => Promise<void> }) {
  const [sourcePath, setSourcePath] = useState(item.source_path || '')
  const [sourceLocation, setSourceLocation] = useState(item.source_location || '')
  const [terms, setTerms] = useState(Array.isArray(item.required_terms) ? item.required_terms.join('、') : String(item.required_terms || ''))
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  async function review(decision: 'APPROVE' | 'REJECT' | 'DEFER') {
    setBusy(true)
    const response = await fetch(`/api/v2/feedback-workflow/${item.feedback_id}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trial_user: 'reviewer-001', decision, source_path: sourcePath, source_location: sourceLocation, required_terms: splitTerms(terms), standard_question: item.standard_question || item.question, similar_questions: item.similar_questions || [], negative_questions: item.negative_questions || [], applicability: item.applicability || '' }) })
    const payload = await response.json()
    setNotice(response.ok ? payload.status === 'SOURCE_INDEX_FAILED' ? '来源解析或索引失败，请查看知识资产中的原因。' : decision === 'APPROVE' ? '已核对并发布到试用知识。' : decision === 'REJECT' ? '已驳回。' : '已暂缓。' : (payload.detail || '操作失败。'))
    setBusy(false)
    if (response.ok) await onRefresh()
  }
  async function regress() {
    setBusy(true)
    const response = await fetch(`/api/v2/feedback-workflow/${item.feedback_id}/regression`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trial_user: 'reviewer-001' }) })
    const payload = await response.json()
    setNotice(response.ok ? `回归结果：${payload.regression?.regression_status || payload.regression_status}${payload.reason ? `；${payload.reason}` : ''}` : '回归失败。')
    setBusy(false)
    if (response.ok) await onRefresh()
  }
  async function withdraw() {
    if (!item.knowledge_id) return
    setBusy(true)
    const response = await fetch(`/api/v2/knowledge/items/${item.knowledge_id}/withdraw`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trial_user: 'reviewer-001' }) })
    setNotice(response.ok ? '更正知识已撤回；原始来源仍保留。' : '撤回失败。')
    setBusy(false)
    if (response.ok) await onRefresh()
  }
  async function rollback() {
    if (!item.knowledge_id) return
    setBusy(true)
    const response = await fetch(`/api/v2/knowledge/items/${item.knowledge_id}/rollback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trial_user: 'reviewer-001', target_version: 1, reason: '业务负责人从更正记录恢复首次审核版本' }) })
    const payload = await response.json()
    setNotice(response.ok ? payload.knowledge?.status === 'ACTIVE' ? '已回滚到首次审核版本并恢复试用。' : '已回滚内容，但来源版本已变化，需要重新核对。' : '回滚失败。')
    setBusy(false)
    if (response.ok) await onRefresh()
  }
  const active = item.status === 'ACTIVE'
  return <article className="closure-item"><b>{item.feedback_type} · {workflowLabel[item.closure_status] || workflowLabel[item.status] || item.closure_status}</b><p>{item.question}</p>{item.failure_code && <small>{item.failure_stage || '待分类'} · {item.failure_code}：{item.root_cause}</small>}{item.system_fix_required && <p>已进入 RAG 系统缺陷池，不能发布为标准答案。</p>}{!item.system_fix_required && !active && !['REJECTED', 'DEFERRED', 'WITHDRAWN'].includes(item.status) && <><input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="来源文件路径" /><input value={sourceLocation} onChange={(event) => setSourceLocation(event.target.value)} placeholder="页码、段落或Sheet" /><input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="关键事实，逗号分隔" /><div><button disabled={busy} onClick={() => void review('APPROVE')}>核对并发布</button><button disabled={busy} onClick={() => void review('DEFER')}>暂缓</button><button disabled={busy} onClick={() => void review('REJECT')}>驳回</button></div></>}{active && <div><button disabled={busy} onClick={() => void regress()}>运行全库回归</button><button disabled={busy} onClick={() => void withdraw()}>撤回更正知识</button></div>}{item.status === 'WITHDRAWN' && <div><button disabled={busy} onClick={() => void rollback()}>回滚到首次审核版本</button></div>}{notice && <small>{notice}</small>}</article>
}

function SourceDetail({ citation }: { citation: Citation }) {
  const ext = citation.file_name?.split('.').pop()?.toUpperCase() || '文件'
  return <div className="source-card"><b>{citation.file_name}</b><span>{ext} · {citation.display_location}</span><p>{citation.source_path}</p><small>{citation.source_id || '来源ID待补'} · 版本 {(citation.source_version || '待核实').slice(0, 12)}</small><h3>原文证据</h3><div className="evidence-text">{citation.excerpt || '当前引用未提供可展开的原文。'}</div></div>
}

function loadMessages(): ChatMessage[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(value) ? value.filter((item) => item && (item.role === 'user' || item.role === 'assistant') && typeof item.text === 'string') : []
  } catch { return [] }
}
