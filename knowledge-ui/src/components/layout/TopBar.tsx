import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { knowledgeNodes } from '../../data/mock/knowledgeTree'

export function TopBar() {
  const [keyword, setKeyword] = useState('')
  const navigate = useNavigate()
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const match = knowledgeNodes.find((node) => node.name.includes(keyword.trim()))
    navigate(match ? `/framework?node=${match.id}` : '/framework')
  }

  return (
    <header className="topbar">
      <div className="topbar-title">知识框架工作台</div>
      <form className="global-search" onSubmit={submit}>
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索知识节点、专题或来源" />
        <button type="submit">搜索</button>
      </form>
      <div className="profile"><span className="notification">3</span><span className="avatar">刘</span><span>业务负责人</span></div>
    </header>
  )
}
