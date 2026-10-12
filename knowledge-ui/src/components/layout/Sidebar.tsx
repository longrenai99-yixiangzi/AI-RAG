import { NavLink } from 'react-router-dom'
import { useRuntimeCapabilities } from './RuntimeCapabilities'

const primary = [
  ['/', '首页', 'dashboard'],
  ['/projects', '按项目查阅', 'projects'],
  ['/periods', '部门与期间资料', 'periods'],
  ['/framework', '通用方法与分类', 'framework'],
  ['/topics', '专题知识', 'topics'],
  ['/ai', 'AI问答', 'ai_query'],
  ['/taskbook', '任务书编制', 'taskbook_draft'],
  ['/batch', '批量验收', 'batch'],
  ['/sources', '知识资产', 'sources'],
  ['/knowledge-os/diagnostics', '问答诊断', 'diagnostics'],
  ['/feedback', '反馈记录', 'feedback_records'],
  ['/growth', '知识补充与改进', 'growth_queue'],
  ['/knowledge-os/gold-review', '来源审核', 'gold_review'],
]

const secondary = [
  ['/favorites', '我的收藏', 'favorites'],
  ['/recent', '最近浏览', 'recent'],
]

export function Sidebar() {
  const { runtime, error } = useRuntimeCapabilities()
  const visible = (items: string[][]) => items.filter(([, , feature]) => runtime?.features[feature])
  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand">
        <span className="brand-mark">K</span>
        <span>
          <b>企业知识库</b>
          <small>{runtime?.display_name || '正在核对当前版本'}</small>
        </span>
      </NavLink>
      <nav className="navigation" aria-label="主导航">
        {visible(primary).map(([to, label]) => <NavLink key={to} to={to} end={to === '/'}>{label}</NavLink>)}
      </nav>
      <div className="navigation secondary" aria-label="个人导航">
        {visible(secondary).map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
      </div>
      <div className="side-note">
        <span className="status-dot" />
        <div><p>通用问题可查全库。<br />项目问题按项目和事项核对原文。</p>
        {error && <p className="runtime-error">{error}</p>}
        {runtime && <p>{runtime.release_name}</p>}</div>
      </div>
    </aside>
  )
}
