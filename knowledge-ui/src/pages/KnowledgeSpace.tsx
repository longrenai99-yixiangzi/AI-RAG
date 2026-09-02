import { Link, useParams } from 'react-router-dom'
import type { ReactNode } from 'react'
import { CoverageBar } from '../components/knowledge/CoverageBar'
import { getAncestors, getChildren, getNode } from '../data/mock/knowledgeTree'
import { getTechnicalConstructionSample } from '../data/mock/technicalConstructionSample'

export function KnowledgeSpace() {
  const { id = '' } = useParams()
  const node = getNode(id)
  if (!node) return <Empty title="未找到知识空间" />
  const sample = getTechnicalConstructionSample(node.id)
  if (sample) return <TechnicalConstructionSpace sample={sample} />
  const children = getChildren(node.id)
  const ancestors = getAncestors(node.id)
  return <section><div className="breadcrumbs page-breadcrumbs">{ancestors.map((item) => <Link key={item.id} to={`/knowledge/${item.id}`}>{item.name}</Link>)}</div><section className="space-hero"><span className="eyebrow">KNOWLEDGE SPACE</span><h1>{node.name}</h1><p>{node.description}</p></section><div className="space-grid">{children.length ? children.map((child) => <Link className="space-card" key={child.id} to={child.childrenCount ? `/knowledge/${child.id}` : `/node/${child.id}`}><span className="space-type">{child.childrenCount ? '知识空间' : '知识节点'}</span><h3>{child.name}</h3><p>{child.description}</p><div><span>{child.childrenCount} 个子节点</span><span>{child.knowledgeCount} 个知识</span></div><CoverageBar value={child.coverage} /></Link>) : <Link className="space-card" to={`/node/${node.id}`}><span className="space-type">知识节点</span><h3>查看结构化知识</h3><p>进入该节点的知识概述、要点、案例与来源。</p></Link>}</div></section>
}

function TechnicalConstructionSpace({ sample }: { sample: NonNullable<ReturnType<typeof getTechnicalConstructionSample>> }) {
  const sourceById = new Map(sample.sources.map((source) => [source.id, source]))
  const templateSources = sample.sources.filter((source) => source.type === '模板')
  return <section className="sample-space">
    <div className="breadcrumbs page-breadcrumbs"><Link to={`/framework?node=${sample.graph.node.id}`}>{sample.graph.domain.name} / {sample.graph.category.name} / {sample.graph.node.name}</Link></div>
    <header className="space-hero"><span className="eyebrow">KNOWLEDGE SPACE · MOCK SAMPLE</span><h1>{sample.graph.node.name}</h1><p>{sample.space.overview}</p><div className="space-stat-row"><span>{sample.cards.length} 张知识卡片</span><span>{sample.sources.length} 条资料来源</span><span>{sample.cases.length} 个项目案例</span></div></header>
    <SpaceSection title="概览"><p>本空间以“总体施组”这一叶子节点为样板，完整保留知识卡片、来源和案例之间的引用关系。</p></SpaceSection>
    <SpaceSection title="核心知识"><div className="sample-card-grid">{sample.cards.map((card) => <article key={card.id}><span>KnowledgeCard</span><h3>{card.title}</h3><p>{card.summary}</p><ul>{card.keyPoints.map((item) => <li key={item}>{item}</li>)}</ul><small>依据：{card.sourceIds.map((sourceId) => sourceById.get(sourceId)?.name).join('；')}</small></article>)}</div></SpaceSection>
    <SpaceSection title="管理要点"><ol className="management-list">{sample.space.managementPoints.map((point) => <li key={point}>{point}</li>)}</ol></SpaceSection>
    <SpaceSection title="模板工具"><div className="tool-list">{templateSources.map((source) => <SourceItem key={source.id} source={source} />)}</div></SpaceSection>
    <SpaceSection title="项目案例"><div className="case-grid">{sample.cases.map((item) => <article key={item.id}><span>Case · Mock</span><h3>{item.name}</h3><p><b>场景：</b>{item.scenario}</p><p><b>做法：</b>{item.outcome}</p><small>来源：{item.sourceIds.map((sourceId) => sourceById.get(sourceId)?.name).join('；')}</small></article>)}</div></SpaceSection>
    <SpaceSection title="知识来源"><div className="tool-list">{sample.sources.map((source) => <SourceItem key={source.id} source={source} />)}</div></SpaceSection>
  </section>
}

function SpaceSection({ title, children }: { title: string; children: ReactNode }) { return <section className="sample-space-section"><div className="section-heading"><h2>{title}</h2></div>{children}</section> }
function SourceItem({ source }: { source: { name: string; type: string; authority: string; location: string; excerpt: string } }) { return <article className="sample-source"><div><span>{source.type} · {source.authority}</span><h3>{source.name}</h3><p>{source.excerpt}</p></div><small>{source.location}</small></article> }

function Empty({ title }: { title: string }) { return <div className="empty-page"><h1>{title}</h1><Link to="/framework">返回知识框架</Link></div> }
