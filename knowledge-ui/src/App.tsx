import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { Dashboard } from './pages/Dashboard'
import { KnowledgeFramework } from './pages/KnowledgeFramework'
import { KnowledgeNode } from './pages/KnowledgeNode'
import { KnowledgeSources } from './pages/KnowledgeSources'
import { KnowledgeSpace } from './pages/KnowledgeSpace'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { AIChat } from './pages/AIChat'
import { TopicKnowledge } from './pages/TopicKnowledge'

export default function App() {
  return <Routes>
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
      <Route path="/sources" element={<KnowledgeSources />} />
      <Route path="/favorites" element={<PlaceholderPage title="我的收藏" description="V0.1 先保留个人入口，后续接入收藏关系。" />} />
      <Route path="/recent" element={<PlaceholderPage title="最近浏览" description="V0.1 先保留个人入口，后续接入最近浏览记录。" />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes>
}

function TopicKnowledgeList() {
  return <section className="topic-index"><span className="eyebrow">CROSS-DOMAIN TOPICS</span><h1>专题知识</h1><p>V0.1 已预置 EPC、价值创造和 AI 三个横向专题入口。</p><div className="topic-index-links"><Link to="/topics/epc">EPC</Link><Link to="/topics/value">价值创造</Link><Link to="/topics/ai">AI</Link></div></section>
}
