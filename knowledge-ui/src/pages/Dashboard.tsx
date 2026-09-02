import { Link, useNavigate } from 'react-router-dom'
import { KnowledgeCard } from '../components/knowledge/KnowledgeCard'
import { CoverageBar } from '../components/knowledge/CoverageBar'
import { domains } from '../data/mock/knowledgeTree'
import { topics } from '../data/mock/topics'
import { growthItems } from '../data/mock/growth'
import { knowledgeGaps } from '../data/mock/gaps'

const coverage = [
  ['01 设计管理体系', 88], ['02 投标与前期设计管理', 68], ['03 设计策划管理', 92], ['04 设计过程管理', 84],
  ['05 阶段性设计成果管理', 87], ['06 设计成果库', 81], ['07 设计资源库', 63], ['08 设计资料库', 76],
]

export function Dashboard() {
  const navigate = useNavigate()
  return <>
    <section className="page-hero">
      <div><span className="eyebrow">KNOWLEDGE OS</span><h1>知识总览</h1><p>从知识体系进入企业经验、制度、模板与原始资料，而不是从文件夹开始。</p></div>
      <Link className="outline-button" to="/framework">查看知识框架</Link>
    </section>
    <section className="domain-grid">
      {domains.map((node) => <KnowledgeCard key={node.id} node={node} />)}
    </section>
    <section className="topic-strip"><div className="section-heading"><div><span className="eyebrow">CROSS-DOMAIN</span><h2>横向专题</h2></div><p>专题只建立关联，不复制三大板块中的知识。</p></div>
      <div className="topic-grid">{topics.map((topic) => <button className={`topic-card ${topic.color}`} key={topic.id} onClick={() => navigate(`/topics/${topic.id}`)}><span>专题知识</span><b>{topic.name}</b><small>{topic.description}</small><i>{topic.children.length} 个子专题</i></button>)}</div>
    </section>
    <section className="dashboard-grid">
      <article className="panel coverage-panel"><div className="section-heading"><div><span className="eyebrow">COVERAGE</span><h2>知识框架覆盖度</h2></div><span className="panel-note">V0.1 Mock</span></div>{coverage.map(([label, value]) => <div className="coverage-row" key={label}><b>{label}</b><CoverageBar value={value as number} /></div>)}</article>
      <article className="panel growth-panel"><div className="section-heading"><div><span className="eyebrow">GROWTH</span><h2>最近知识生长</h2></div></div><div className="growth-list">{growthItems.slice(0, 5).map((item) => <div className="growth-item" key={item.id}><i className={item.action} /> <div><b>{item.title}</b><small>{item.path.join(' / ')} · {item.date}</small></div></div>)}</div></article>
      <article className="panel gap-panel"><div className="section-heading"><div><span className="eyebrow">GAPS</span><h2>知识缺口</h2></div></div>{knowledgeGaps.slice(0, 3).map((gap) => <div className="gap-item" key={gap.id}><span className={gap.level}>{gap.level}</span><div><b>{gap.title}</b><small>{gap.reason}</small></div></div>)}</article>
      <article className="panel hot-panel"><div className="section-heading"><div><span className="eyebrow">POPULAR</span><h2>热门知识</h2></div></div>{['设计审查', '深化设计', '价值创造', '设计任务书', 'BIM与数字化'].map((item, index) => <button key={item} onClick={() => navigate('/framework')}><em>{String(index + 1).padStart(2, '0')}</em><span>{item}</span><small>{68 - index * 7} 次浏览</small></button>)}</article>
    </section>
  </>
}
