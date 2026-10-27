import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LOCAL_PLATFORM } from '../../localPlatform'

export function TopBar() {
  const [keyword, setKeyword] = useState('')
  const navigate = useNavigate()
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = keyword.trim()
    navigate(LOCAL_PLATFORM ? (value ? `/materials?q=${encodeURIComponent(value)}` : '/materials') : (value ? `/search?q=${encodeURIComponent(value)}` : '/search'))
  }

  return (
    <header className="topbar">
      <div className="topbar-title">知识框架工作台</div>
      <form className="global-search" onSubmit={submit}>
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={LOCAL_PLATFORM ? '查找当前资料名称' : '搜索知识节点、专题或来源'} />
        <button type="submit">搜索</button>
      </form>
      <div className="profile"><span className="avatar">刘</span><span>业务负责人</span></div>
    </header>
  )
}
