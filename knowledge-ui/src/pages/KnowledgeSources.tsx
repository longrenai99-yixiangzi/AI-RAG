import { useMemo, useState } from 'react'
import { sources } from '../data/mock/sources'

export function KnowledgeSources() {
  const [filter, setFilter] = useState('全部')
  const visible = useMemo(() => filter === '全部' ? sources : sources.filter((source) => source.type === filter), [filter])
  const filters = ['全部', '制度', '规范', '标准', '项目案例', '模板', 'Word', 'PDF', 'Excel', 'PPT', '其他资料']
  return <section><header className="page-hero compact"><div><span className="eyebrow">KNOWLEDGE SOURCES</span><h1>知识来源</h1><p>文件是知识节点的来源，不是系统的主入口。</p></div></header><div className="source-filter">{filters.map((item) => <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>)}</div><article className="panel source-table"><div className="table-head"><span>资料名称</span><span>资料类型</span><span>来源</span><span>所属知识</span><span>版本</span><span>更新时间</span></div>{visible.map((source) => <div className="table-row" key={source.id}><b>{source.name}</b><span>{source.type}</span><span className={source.authority === '待审' ? 'pending-text' : ''}>{source.source}</span><span>{source.knowledge}</span><span>{source.version}</span><span>{source.updatedAt}</span></div>)}</article></section>
}
