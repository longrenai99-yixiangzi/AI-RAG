import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ExistingAsk, ExistingLibrary } from './PlatformContent'
import { PlatformSearch } from './PlatformTools'
import type { Snapshot, Knowledge } from './PlatformWorkbench'
import { platformApi as api } from './platformApi'
import './PlatformWorkbench.css'
import './LocalPlatformPages.css'

function useSnapshot() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    try { setData(await api<Snapshot>('state')); setError('') }
    catch (e) { setError(e instanceof Error ? e.message : '本机平台暂时无法连接'); throw e }
  }, [])
  useEffect(() => { refresh().catch(() => undefined) }, [refresh])
  return { data, error, refresh }
}

export function LocalScopeNotice() {
  return <p className="panel local-scope-note">本期为本机设计管理有限资料版。知识框架用于分类浏览，目录中的资料数量不代表已审核知识或问答覆盖率。<Link to="/materials">查看当前检索资料</Link> · <Link to="/ai">进入当前问答</Link></p>
}

export function LocalDashboard() {
  const { data, error, refresh } = useSnapshot()
  return <>
    <section className="page-hero"><div><span className="eyebrow">KNOWLEDGE OS</span><h1>设计管理知识库</h1><p>从知识框架查找业务主题，在同一入口查看当前资料、提问和核对原文。</p></div><Link className="outline-button" to="/framework">查看知识框架</Link></section>
    {error && <p role="alert" className="runtime-error">{error} <button onClick={() => refresh().catch(() => undefined)}>重新连接</button></p>}
    <section className="runtime-metrics">
      <article><b>{data?.runtime?.sources ?? '读取中'}</b><span>当前检索来源</span></article>
      <article><b>{data?.runtime?.records ?? '读取中'}</b><span>当前索引片段</span></article>
      <article><b>{data ? data.knowledge.filter(k => k.status === 'ACTIVE').length : '读取中'}</b><span>本地发布记录</span></article>
      <article><b>{data ? data.candidates.filter(k => k.status === 'IN_REVIEW').length : '读取中'}</b><span>待审核候选</span></article>
    </section>
    <LocalScopeNotice />
    <section className="domain-grid">
      <Link className="space-card" to="/framework"><span className="space-type">业务导航</span><h3>知识框架</h3><p>沿用共用分类定义，设计管理按既定四类13动作浏览。</p></Link>
      <Link className="space-card" to="/materials"><span className="space-type">资料查阅</span><h3>当前资料</h3><p>查看当前检索来源及证据片段，打开原件核对。</p></Link>
      <Link className="space-card" to="/ai"><span className="space-type">问答与引用</span><h3>业务提问</h3><p>使用当前本机问答流程，按实际证据答复，范围不清时提示补充。</p></Link>
    </section>
    <section className="panel"><h2>使用范围</h2><p>当前来源中正文处理和业务核验程度不同；有来源不等于所有问题都能正确回答。本地发布记录的适用范围及原件版本仍需核对。技术管理、科技管理保留为后续补充，当前不扩展。</p><p>日常模型是否启用、批准资料范围、剩余额度和到期时间见问答页；未批准资料保持本地检索。</p><Link to="/manage?tab=overview">进入管理工作台</Link></section>
    {data && <p className="state-version">当前问答修订：{data.runtime?.content_revision || '读取中'} · 业务验收尚未确认</p>}
  </>
}

export function LocalAsk() {
  const { data, error, refresh } = useSnapshot()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  if (error) return <section className="panel"><h1>业务问答</h1><p role="alert">{error}</p><button onClick={() => refresh().catch(() => undefined)}>重新连接</button></section>
  if (!data) return <section className="panel" role="status">正在读取本机资料范围与问答策略……</section>
  return <><section className="page-hero compact"><div><span className="eyebrow">BUSINESS Q&amp;A</span><h1>业务问答</h1><p>与当前资料、管理记录共用同一本机服务。当前修订：{data.runtime?.content_revision || '待核对'}。</p></div><Link className="outline-button" to="/framework">返回知识框架</Link></section>
    <div className="platform-workbench local-platform"><ExistingAsk data={data} actor="本机负责人" seed={params.get('q') || ''} refresh={refresh} openCandidate={() => navigate('/manage?tab=candidates')} /></div></>
}

export function LocalLibrary() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  return <><section className="page-hero compact"><div><span className="eyebrow">SOURCE LIBRARY</span><h1>当前检索资料</h1><p>本页读取当前问答服务的资料清单；正文处理及核验程度见来源说明。原件路径保持稳定。</p></div><Link className="outline-button" to="/catalog">业务分类目录</Link></section>
    <div className="platform-workbench local-platform"><ExistingLibrary seed={params.get('q') || ''} ask={q => navigate('/ai?q=' + encodeURIComponent(q))} /></div></>
}

export function LocalKnowledgeSearch() {
  const { data, error } = useSnapshot()
  const navigate = useNavigate()
  if (error) return <p role="alert" className="runtime-error">{error}</p>
  if (!data) return <p role="status">正在读取已发布知识……</p>
  return <div className="platform-workbench local-platform"><PlatformSearch data={data} search={query => api<{ items: Knowledge[]; notice: string }>('search?' + query)} openKnowledge={() => navigate('/manage?tab=knowledge')} /></div>
}

export function LocalUnavailable() {
  return <section className="panel"><h1>此历史入口尚未接通当前版本</h1><p>可通过知识框架、当前资料和业务问答使用本机有限资料版。</p><Link to="/framework">返回知识框架</Link> · <Link to="/manage">管理工作台</Link></section>
}
