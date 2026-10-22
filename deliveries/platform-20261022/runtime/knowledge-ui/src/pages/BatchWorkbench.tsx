import { useEffect, useMemo, useRef, useState } from 'react'

type SourceFile = { source_path: string; file_name: string; file_type: string; size: number; sha256: string; parse_probe: string; error?: string }
type BatchCase = { case_id: string; question: string; expected_source_path: string; expected_source_location: string; required_terms: string[]; generation_mode: string }
type BatchRun = { case_id: string; regression_status: string; answer_status?: string; dense_runtime?: string; missing_required_terms?: string[]; reason?: string; answer_excerpt?: string }
type Summary = { approved_source_count: number; question_count: number; run_count: number; anomaly_count: number; passed_count: number }
const SOURCE_INPUT_KEY = 'v2_trial_batch_source_input'
const ACTIVE_SOURCES_KEY = 'v2_trial_batch_active_sources'

export function BatchWorkbench() {
  const [sourceInput, setSourceInput] = useState(() => localStorage.getItem(SOURCE_INPUT_KEY) || '')
  const [activeSources, setActiveSources] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(ACTIVE_SOURCES_KEY) || '[]') as string[] } catch { return [] } })
  const [preview, setPreview] = useState<SourceFile[]>([])
  const [cases, setCases] = useState<BatchCase[]>([])
  const [anomalies, setAnomalies] = useState<BatchRun[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selectedCases, setSelectedCases] = useState<string[]>([])
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const folderInput = useRef<HTMLInputElement>(null)

  useEffect(() => { localStorage.setItem(SOURCE_INPUT_KEY, sourceInput) }, [sourceInput])
  useEffect(() => { localStorage.setItem(ACTIVE_SOURCES_KEY, JSON.stringify(activeSources)) }, [activeSources])
  useEffect(() => { if (activeSources.length) void refresh(activeSources) }, [])
  useEffect(() => { folderInput.current?.setAttribute('webkitdirectory', '') }, [])

  const paths = useMemo(() => sourceInput.split(/\r?\n/).map((item) => item.trim()).filter(Boolean), [sourceInput])

  async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
    const payload = await response.json() as { detail?: string } & Record<string, unknown>
    if (!response.ok) throw new Error(String(payload.detail || '批处理接口请求失败'))
    return payload
  }

  function scoped(path: string, sourcePaths = activeSources): string {
    const query = new URLSearchParams({ trial_user: 'reviewer-001' })
    sourcePaths.forEach((item) => query.append('source_paths', item))
    return `${path}?${query.toString()}`
  }

  async function refresh(sourcePaths = activeSources) {
    if (!sourcePaths.length) {
      setSummary(null)
      setCases([])
      setAnomalies([])
      return
    }
    try {
      const [summaryPayload, questionPayload, anomalyPayload] = await Promise.all([
        api(scoped('/api/v2/batch/summary', sourcePaths)), api(scoped('/api/v2/batch/questions', sourcePaths)), api(scoped('/api/v2/batch/anomalies', sourcePaths)),
      ])
      setSummary(summaryPayload as unknown as Summary)
      setCases((questionPayload.questions || []) as BatchCase[])
      setAnomalies((anomalyPayload.anomalies || []) as BatchRun[])
    } catch (error) { setNotice(error instanceof Error ? error.message : '批处理工作台暂不可用。') }
  }

  async function continueBatch(sourcePaths: string[]) {
    if (!sourcePaths.length) return
    setNotice('已进入 Shadow，正在自动生成验收问题…')
    const generated = await api('/api/v2/batch/questions/generate', 'POST', { paths: sourcePaths, trial_user: 'reviewer-001' })
    const questionPayload = await api(scoped('/api/v2/batch/questions', sourcePaths))
    const currentCases = (questionPayload.questions || []) as BatchCase[]
    if (!currentCases.length) {
      await refresh(sourcePaths)
      setNotice(`自动验收完成：新增 ${Number(generated.created_count || 0)} 道题；当前资料没有可安全推导的验收题。`)
      return
    }
    setNotice(`已生成/保留 ${currentCases.length} 道验收题，正在自动批量回归…`)
    const result = await api('/api/v2/batch/regressions/run', 'POST', { case_ids: currentCases.map((item) => item.case_id), trial_user: 'reviewer-001' })
    await refresh(sourcePaths)
    setNotice(`自动验收完成：通过 ${Number(result.passed_count || 0)}，失败 ${Number(result.failed_count || 0)}，待人工确认 ${Number(result.observed_count || 0)}，未就绪 ${Number(result.not_ready_count || 0)}。`)
  }

  async function previewSources() {
    setBusy(true); setNotice('正在只读扫描来源…')
    try {
      const payload = await api('/api/v2/batch/sources/preview', 'POST', { paths, recursive: true })
      const files = (payload.files || []) as SourceFile[]
      setPreview(files)
      const nextSources = files.map((item) => item.source_path)
      setActiveSources(nextSources)
      setSelectedCases([])
      setNotice(`扫描完成：发现 ${Number(payload.source_count || 0)} 个可处理文件。`)
      await refresh(nextSources)
    } catch (error) { setNotice(error instanceof Error ? error.message : '来源扫描失败。') } finally { setBusy(false) }
  }

  async function uploadFolder() {
    if (!selectedFiles.length) return
    setBusy(true); setNotice(`正在上传 ${selectedFiles.length} 个文件…`)
    try {
      const started = await api('/api/v2/batch/uploads', 'POST', { trial_user: 'reviewer-001' }) as { upload_id: string; upload_token: string }
      for (const file of selectedFiles) {
        const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
        const response = await fetch(`/api/v2/batch/uploads/${started.upload_id}/file?relative_path=${encodeURIComponent(relativePath)}`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream', 'X-Upload-Token': started.upload_token }, body: file })
        if (!response.ok) throw new Error((await response.text()) || '文件上传失败')
      }
      const completed = await api(`/api/v2/batch/uploads/${started.upload_id}/complete`, 'POST', { trial_user: 'reviewer-001' }) as { files: string[]; file_count: number }
      const payload = await api('/api/v2/batch/sources/preview', 'POST', { paths: completed.files, recursive: false })
      const files = (payload.files || []) as SourceFile[]
      setPreview(files)
      setActiveSources(completed.files)
      setSelectedCases([])
      setSelectedFiles([])
      if (folderInput.current) folderInput.current.value = ''
      await api('/api/v2/batch/sources/approve', 'POST', { paths: completed.files, recursive: false, trial_user: 'reviewer-001' })
      await continueBatch(completed.files)
    } catch (error) { setNotice(error instanceof Error ? error.message : '文件夹上传失败。') } finally { setBusy(false) }
  }

  async function approveSources() {
    const approvedPaths = preview.filter((item) => !item.error && item.parse_probe !== 'read_error').map((item) => item.source_path)
    setBusy(true); setNotice('正在登记 Shadow 只读来源…')
    try {
      const payload = await api('/api/v2/batch/sources/approve', 'POST', { paths: approvedPaths, recursive: false })
      setNotice(`已批准 ${Number(payload.approved_count || 0)} 个来源；运行时将只读加载。`)
      setActiveSources(approvedPaths)
      setSelectedCases([])
      await continueBatch(approvedPaths)
    } catch (error) { setNotice(error instanceof Error ? error.message : '来源登记失败。') } finally { setBusy(false) }
  }

  async function generateQuestions() {
    setBusy(true); setNotice('正在从结构化来源生成验收问题…')
    try {
      const payload = await api('/api/v2/batch/questions/generate', 'POST', { paths: activeSources, trial_user: 'reviewer-001' })
      setNotice(`已生成 ${Number(payload.created_count || 0)} 个验收问题。`)
      await refresh(activeSources)
    } catch (error) { setNotice(error instanceof Error ? error.message : '问题生成失败。') } finally { setBusy(false) }
  }

  async function runRegressions() {
    setBusy(true); setNotice('正在批量运行 Shadow 回归…')
    try {
      const payload = await api('/api/v2/batch/regressions/run', 'POST', { case_ids: selectedCases })
      setNotice(`回归完成：通过 ${Number(payload.passed_count || 0)}，失败 ${Number(payload.failed_count || 0)}，待人工确认 ${Number(payload.observed_count || 0)}，未就绪 ${Number(payload.not_ready_count || 0)}。`)
      await refresh(activeSources)
    } catch (error) { setNotice(error instanceof Error ? error.message : '批量回归失败。') } finally { setBusy(false) }
  }

  function toggleCase(caseId: string) {
    setSelectedCases((items) => items.includes(caseId) ? items.filter((item) => item !== caseId) : [...items, caseId])
  }

  return <section className="batch-page">
    <header className="page-hero">
      <div><span className="eyebrow">BATCH ACCEPTANCE WORKFLOW</span><h1>批量验收工作台</h1><p>批量资料入库 → 自动生成问题 → 批量回归 → 异常清单 → 人工确认</p></div>
      <button className="outline-button" onClick={() => void refresh()} disabled={busy}>刷新状态</button>
    </header>

    <div className="batch-grid">
      <article className="panel batch-card">
        <span className="eyebrow">01 · SOURCE INTAKE</span><h2>批量资料入库</h2>
        <p>可填写服务器本机路径，也可选择本机文件夹上传。浏览器上传完成后会自动批准进入 Shadow、生成验收题并批量回归；服务器路径仍需点击一次批准。</p>
        <div className="batch-upload"><label>选择文件夹<input ref={folderInput} type="file" multiple onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))} /></label><button className="outline-button" onClick={() => void uploadFolder()} disabled={busy || selectedFiles.length === 0}>上传并预览 ({selectedFiles.length})</button></div>
        <textarea value={sourceInput} onChange={(event) => setSourceInput(event.target.value)} placeholder={'D:\\工作\\二公司技术部\\2026\\知识库\\高频设计风险清单\nD:\\工作\\二公司技术部\\2026\\概算及策划评审'} />
        <div className="batch-actions"><button className="outline-button" onClick={() => void previewSources()} disabled={busy || paths.length === 0}>只读预览</button><button className="primary-button" onClick={() => void approveSources()} disabled={busy || preview.length === 0}>批准进入 Shadow</button></div>
        {preview.length > 0 && <div className="batch-file-list">{preview.map((file) => <div key={file.source_path}><b>{file.file_name}</b><small>{file.parse_probe} · {(file.size / 1024 / 1024).toFixed(2)} MB</small></div>)}</div>}
      </article>

      <article className="panel batch-card">
        <span className="eyebrow">02 · QUESTION FACTORY</span><h2>自动生成验收问题</h2>
        <p>从可直接推导事实的资料生成严格验收题；进入 Shadow 后自动执行，无法安全推导的资料列入跳过说明。</p>
        <button className="primary-button" onClick={() => void generateQuestions()} disabled={busy || !summary?.approved_source_count}>生成验收问题</button>
        <div className="batch-metrics"><div><b>{summary?.approved_source_count ?? 0}</b><small>Shadow来源</small></div><div><b>{summary?.question_count ?? 0}</b><small>验收问题</small></div><div><b>{summary?.passed_count ?? 0}</b><small>已通过回归</small></div></div>
      </article>
    </div>

    <article className="panel batch-card batch-run-card">
      <div className="batch-section-head"><div><span className="eyebrow">03 · REGRESSION RUN</span><h2>批量回归</h2></div><button className="primary-button" onClick={() => void runRegressions()} disabled={busy || cases.length === 0}>运行{selectedCases.length ? `选中 ${selectedCases.length} 个` : '全部'}回归</button></div>
      {!activeSources.length ? <p className="batch-empty">请先在上方预览或上传一批来源。</p> : cases.length === 0 ? <p className="batch-empty">当前批次尚未生成验收问题；PDF 等未配置题型的资料不会显示历史问题。</p> : <div className="batch-case-list">{cases.map((item) => <label key={item.case_id}><input type="checkbox" checked={selectedCases.includes(item.case_id)} onChange={() => toggleCase(item.case_id)} /><span><b>{item.question}</b><small>{item.generation_mode} · {item.expected_source_location} · {item.required_terms.length} 个验收事实</small></span></label>)}</div>}
    </article>

    <article className="panel batch-card">
      <div className="batch-section-head"><div><span className="eyebrow">04 · EXCEPTIONS</span><h2>异常清单</h2></div><span className="batch-count">{anomalies.length} 项</span></div>
      {anomalies.length === 0 ? <p className="batch-empty">暂无异常。</p> : <div className="batch-anomaly-list">{anomalies.map((item) => <div key={item.case_id}><b>{item.regression_status} · {item.case_id}</b><span>{item.reason || `缺失事实：${(item.missing_required_terms || []).join('、') || '答案或引用未通过校验'}`}</span><small>{item.answer_excerpt || ''}</small></div>)}</div>}
    </article>

    {notice && <p className="batch-notice">{notice}</p>}
    <p className="panel-note">当前仍为受控试用：批量批准只写入 Shadow 来源登记，批量回归只写入审计结果，不自动发布正式知识。</p>
  </section>
}
