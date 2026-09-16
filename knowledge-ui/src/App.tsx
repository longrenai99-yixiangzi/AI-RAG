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

export default function App() {
  return <AppErrorBoundary><Routes>
    <Route element={<AppLayout />}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/knowledge-os" element={<Dashboard />} />
      <Route path="/framework" element={<KnowledgeFramework />} />
      <Route path="/knowledge/:id" element={<KnowledgeSpace />} />
      <Route path="/node/:id" element={<KnowledgeNode />} />
      <Route path="/topics" element={<TopicKnowledgeList />} />
      <Route path="/topics/:id" element={<TopicKnowledge />} />
      <Route path="/projects" element={<PlaceholderPage title="项目知识" description="V0.1 保留入口，项目知识将在下一阶段关联项目页、项目案例与知识节点。" />} />
      <Route path="/ai" element={<AIChat />} />
      <Route path="/batch" element={<BatchWorkbench />} />
      <Route path="/sources" element={<KnowledgeSources />} />
      <Route path="/search" element={<SearchResults />} />
      <Route path="/knowledge-os/diagnostics" element={<Diagnostics />} />
      <Route path="/knowledge-os/gold-review" element={<GoldReview />} />
      <Route path="/favorites" element={<PlaceholderPage title="我的收藏" description="V0.1 先保留个人入口，后续接入收藏关系。" />} />
      <Route path="/recent" element={<PlaceholderPage title="最近浏览" description="V0.1 先保留个人入口，后续接入最近浏览记录。" />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes></AppErrorBoundary>
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
