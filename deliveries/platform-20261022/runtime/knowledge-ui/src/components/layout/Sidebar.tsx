import { NavLink } from 'react-router-dom'
import { LOCAL_PLATFORM } from '../../localPlatform'

const primary = [
  ['/', '首页'],
  ['/manage', '管理工作台'],
  ['/framework', '知识框架'],
  ['/materials', '现有资料'],
  ['/topics', '专题知识'],
  ['/projects', '项目知识'],
  ['/ai', 'AI问答'],
  ['/batch', '批量验收'],
  ['/sources', '知识资产'],
  ['/knowledge-os/diagnostics', '问答诊断'],
  ['/knowledge-os/gold-review', 'Gold 审核'],
]

const localPrimary = [['/', '首页'], ['/framework', '知识框架'], ['/materials', '当前资料'], ['/ai', '业务问答'], ['/search', '已发布知识'], ['/manage', '管理工作台']]

const secondary = [
  ['/favorites', '我的收藏'],
  ['/recent', '最近浏览'],
]

export function Sidebar() {
  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand">
        <span className="brand-mark">K</span>
        <span>
          <b>企业知识库</b>
          <small>{LOCAL_PLATFORM ? 'Knowledge OS · 本机有限资料' : 'Knowledge OS · V2 Trial'}</small>
        </span>
      </NavLink>
      <nav className="navigation" aria-label="主导航">
        {(LOCAL_PLATFORM ? localPrimary : primary).map(([to, label]) => <NavLink key={to} to={to} end={to === '/'}>{label}</NavLink>)}
      </nav>
      <div className="navigation secondary" aria-label="个人导航">
        {secondary.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
      </div>
      <div className="side-note">
        <span className="status-dot" />
        <p>知识框架优先于文件目录。<br />{LOCAL_PLATFORM ? '本期聚焦设计管理，业务核对待确认。' : 'AI问答为V2内部试用。'}</p>
      </div>
    </aside>
  )
}
