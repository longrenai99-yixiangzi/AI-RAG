import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { Dashboard } from './pages/Dashboard'
import { KnowledgeFramework } from './pages/KnowledgeFramework'
import { KnowledgeNode } from './pages/KnowledgeNode'
import { KnowledgeSources } from './pages/KnowledgeSources'
import { KnowledgeSpace } from './pages/KnowledgeSpace'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { AIChat } from './pages/AIChat'
import { BatchWorkbench } from './pages/BatchWorkbench'
import { TopicKnowledge } from './pages/TopicKnowledge'
import { SearchResults } from './pages/SearchResults'
import { Diagnostics } from './pages/Diagnostics'
import { GoldReview } from './pages/GoldReview'
import { FeedbackRecords } from './pages/FeedbackRecords'
import { ProjectRecords } from './pages/ProjectRecords'
import { PeriodRecords } from './pages/PeriodRecords'
import { SourceReader } from './pages/SourceReader'
import { TaskbookDraft } from './pages/TaskbookDraft'
import { AssessmentHandoff } from './pages/AssessmentHandoff'
import { SchemeComparison } from './pages/SchemeComparison'
import { GrowthQueue } from './pages/GrowthQueue'
import { RuntimeCapabilitiesProvider, RuntimeFeature } from './components/layout/RuntimeCapabilities'

export default function App() {
  return <AppErrorBoundary><RuntimeCapabilitiesProvider><Routes>
    <Route element={<AppLayout />}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/knowledge-os" element={<Dashboard />} />
      <Route path="/framework" element={<KnowledgeFramework />} />
      <Route path="/knowledge/:id" element={<KnowledgeSpace />} />
      <Route path="/node/:id" element={<KnowledgeNode />} />
      <Route path="/topics" element={<TopicKnowledgeList />} />
      <Route path="/topics/:id" element={<TopicKnowledge />} />
      <Route path="/projects" element={<RuntimeFeature feature="projects" title="项目资料"><ProjectRecords /></RuntimeFeature>} />
      <Route path="/projects/:id" element={<RuntimeFeature feature="projects" title="项目资料"><ProjectRecords /></RuntimeFeature>} />
      <Route path="/projects/:id/assessment-tasks" element={<RuntimeFeature feature="projects" title="评估任务准备"><AssessmentHandoff /></RuntimeFeature>} />
      <Route path="/projects/:id/scheme-comparison" element={<RuntimeFeature feature="projects" title="方案比选准备"><SchemeComparison /></RuntimeFeature>} />
      <Route path="/periods" element={<RuntimeFeature feature="periods" title="部门与期间资料"><PeriodRecords /></RuntimeFeature>} />
      <Route path="/read" element={<SourceReader />} />
      <Route path="/ai" element={<AIChat />} />
      <Route path="/taskbook" element={<RuntimeFeature feature="taskbook_draft" title="任务书编制"><TaskbookDraft /></RuntimeFeature>} />
      <Route path="/batch" element={<RuntimeFeature feature="batch" title="批量验收"><BatchWorkbench /></RuntimeFeature>} />
      <Route path="/sources" element={<KnowledgeSources />} />
      <Route path="/search" element={<SearchResults />} />
      <Route path="/knowledge-os/diagnostics" element={<Diagnostics />} />
      <Route path="/knowledge-os/gold-review" element={<RuntimeFeature feature="gold_review" title="来源审核"><GoldReview /></RuntimeFeature>} />
      <Route path="/feedback" element={<RuntimeFeature feature="feedback_records" title="反馈记录"><FeedbackRecords /></RuntimeFeature>} />
      <Route path="/growth" element={<RuntimeFeature feature="growth_queue" title="知识补充与改进"><GrowthQueue /></RuntimeFeature>} />
      <Route path="/favorites" element={<RuntimeFeature feature="favorites" title="我的收藏"><PlaceholderPage title="我的收藏" description="收藏入口尚待接入。" /></RuntimeFeature>} />
      <Route path="/recent" element={<RuntimeFeature feature="recent" title="最近浏览"><PlaceholderPage title="最近浏览" description="最近浏览入口尚待接入。" /></RuntimeFeature>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes></RuntimeCapabilitiesProvider></AppErrorBoundary>
}

class AppErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Knowledge OS UI render failure', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return <main className="panel runtime-error-page"><h1>页面渲染失败</h1><p>后端问题记录仍然保留。请点击下方按钮清理本机当前会话后重试。</p><pre>{this.state.error.message}</pre><button className="primary-button" onClick={() => { localStorage.removeItem('v2_trial_ai_chat_messages'); localStorage.removeItem('v2_trial_ai_chat_draft'); location.reload() }}>清理当前会话并重试</button></main>
  }
}

function TopicKnowledgeList() {
  return <section className="topic-index"><span className="eyebrow">CROSS-DOMAIN TOPICS</span><h1>专题知识</h1><p>V0.1 已预置 EPC、价值创造和 AI 三个横向专题入口。</p><div className="topic-index-links"><Link to="/topics/epc">EPC</Link><Link to="/topics/value">价值创造</Link><Link to="/topics/ai">AI</Link></div></section>
}
