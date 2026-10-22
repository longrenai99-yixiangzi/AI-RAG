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
      .catch(() => setError('真实知识状态暂时无法读取，请检查 8010 服务。'))
  }, [])

  const growth = (overview?.recent_events || []).filter((event) => eventLabel[event.type])
  return <>
    <section className="page-hero">
      <div><span className="eyebrow">KNOWLEDGE OS</span><h1>知识总览</h1><p>分类框架由业务维护，运行数字来自当前 8010 试用知识状态。</p></div>
      <Link className="outline-button" to="/framework">查看知识框架</Link>
    </section>
    {error && <p className="runtime-error">{error}</p>}
    <section className="runtime-metrics" aria-label="当前试用知识状态">
      <article><b>{overview?.sources ?? '读取中'}</b><span>已登记来源</span></article>
      <article><b>{overview?.indexed_sources ?? '读取中'}</b><span>正文已入库</span></article>
      <article><b>{overview?.active_knowledge ?? '读取中'}</b><span>已生效更正知识</span></article>
      <article><b>{overview?.pending_feedback ?? '读取中'}</b><span>待处理反馈</span></article>
    </section>
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
    {overview && <p className="state-version">试用知识状态版本：{overview.state_version}</p>}
  </>
}
