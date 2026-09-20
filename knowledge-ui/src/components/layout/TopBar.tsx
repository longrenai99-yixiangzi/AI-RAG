import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export function TopBar() {
  const [keyword, setKeyword] = useState('')
  const navigate = useNavigate()
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = keyword.trim()
    navigate(value ? `/search?q=${encodeURIComponent(value)}` : '/search')
  }

  return (
    <header className="topbar">
      <div className="topbar-title">知识框架工作台</div>
      <form className="global-search" onSubmit={submit}>
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索知识节点、专题或来源" />
        <button type="submit">搜索</button>
      </form>
      <div className="profile"><span className="avatar">刘</span><span>业务负责人</span></div>
    </header>
  )
}
