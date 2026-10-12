import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { domains } from '../data/mock/knowledgeTree'
import { topics } from '../data/mock/topics'

type Overview = {
  sources: number
  indexed_sources: number
  active_knowledge: number
  pending_feedback: number
  recent_events: Array<{ event_id: string; type: string; knowledge_id?: string; source_id?: string; at: string }>
  state_version: string
  feedback_summary?: { total: number; technical: number; unclassified: number; pending_business_review: number }
  source_count_scope?: string
  release_name?: string
}

const eventLabel: Record<string, string> = {
  KNOWLEDGE_ACTIVATED: '更正知识已生效',
  KNOWLEDGE_WITHDRAWN: '知识已撤回',
  KNOWLEDGE_ROLLED_BACK: '知识已回滚并重新校验',
}

export function Dashboard() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<Overview | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/v2/knowledge/overview', { cache: 'no-store' })
      .then(async (response) => { if (!response.ok) throw new Error(String(response.status)); return response.json() })
      .then(setOverview)
      .catch(() => setError('真实知识状态暂时无法读取，请检查当前服务。'))
  }, [])

  const growth = (overview?.recent_events || []).filter((event) => eventLabel[event.type])
  const unavailable = error ? '读取失败' : '读取中'
  return <>
    <section className="page-hero">
      <div><span className="eyebrow">KNOWLEDGE OS</span><h1>知识总览</h1><p>通用问题查全库；有项目背景的问题先确定项目，再查事项和原文。</p></div>
      <Link className="outline-button" to="/framework">查看知识框架</Link>
    </section>
    <section className="domain-grid query-entry"><Link className="space-card" to="/ai"><h2>通用问题与全库问答</h2><p>查询制度、方法和技术知识，无需选择项目。</p></Link><Link className="space-card" to="/projects"><h2>按项目查阅</h2><p>已有项目背景时，查合同、界面、设计进度和复盘原文。</p></Link><Link className="space-card" to="/periods"><h2>部门与期间资料</h2><p>按部门、年份和期间浏览整份总结，区分本期完成与后续计划。</p></Link></section>
    {error && <p className="runtime-error">{error}</p>}
    <section className="runtime-metrics" aria-label="当前版本知识状态">
      <article><b>{overview?.sources ?? unavailable}</b><span>当前版本来源</span></article>
      <article><b>{overview?.indexed_sources ?? unavailable}</b><span>主答已收录来源</span></article>
      <article><b>{overview?.active_knowledge ?? unavailable}</b><span>当前受控知识</span></article>
      <article><b>{overview?.pending_feedback ?? unavailable}</b><span>待核对或业务复核</span></article>
    </section>
    {overview && <p>来源总数和收录数按同一份当前版本资料清单计算。{overview.feedback_summary && <>反馈历史共{overview.feedback_summary.total}条，其中技术记录{overview.feedback_summary.technical}条、未分类{overview.feedback_summary.unclassified}条、已修复待业务复核{overview.feedback_summary.pending_business_review}条。<Link to="/feedback">查看反馈记录</Link></>}</p>}
    <section className="domain-grid">
      {domains.map((node) => <Link className="space-card" key={node.id} to={`/knowledge/${node.id}`}><span className="space-type">人工维护框架</span><h3>{node.name}</h3><p>{node.description}</p><div><span>{node.childrenCount} 类知识</span><span>运行统计待关联</span></div></Link>)}
    </section>
    <section className="topic-strip"><div className="section-heading"><div><span className="eyebrow">CROSS-DOMAIN</span><h2>横向专题</h2></div><p>专题为框架入口，不代表其中内容已经进入问答。</p></div>
      <div className="topic-grid">{topics.map((topic) => <button className={`topic-card ${topic.color}`} key={topic.id} onClick={() => navigate(`/topics/${topic.id}`)}><span>专题入口</span><b>{topic.name}</b><small>{topic.description}</small><i>{topic.children.length} 个配置子专题</i></button>)}</div>
    </section>
    <section className="dashboard-grid">
      <article className="panel growth-panel"><div className="section-heading"><div><span className="eyebrow">GROWTH</span><h2>最近已生效变更</h2></div></div><div className="growth-list">{growth.length ? growth.slice(0, 6).map((event) => <div className="growth-item" key={event.event_id}><i className="update" /><div><b>{eventLabel[event.type]}</b><small>{event.knowledge_id || event.source_id} · {new Date(event.at).toLocaleString('zh-CN')}</small></div></div>) : <p className="empty-runtime">暂无已生效的知识变更。</p>}</div></article>
      <article className="panel hot-panel"><div className="section-heading"><div><span className="eyebrow">SHORTCUTS</span><h2>常用入口</h2></div><span className="panel-note">不统计虚构浏览次数</span></div>{['设计审查', '深化设计', '价值创造', '设计任务书', 'BIM与数字化'].map((item, index) => <button key={item} onClick={() => navigate(`/search?q=${encodeURIComponent(item)}`)}><em>{String(index + 1).padStart(2, '0')}</em><span>{item}</span><small>搜索</small></button>)}</article>
    </section>
    {overview && <p className="state-version">运行版本：{overview.release_name || '内部试用'} · 本机记录版本：{overview.state_version}</p>}
  </>
}
