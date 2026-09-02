import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export function AppLayout() {
  return <div className="app-layout"><Sidebar /><section className="main-shell"><TopBar /><main className="page-container"><Outlet /></main></section></div>
}
