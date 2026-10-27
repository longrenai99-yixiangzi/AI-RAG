import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { LOCAL_PLATFORM } from '../localPlatform'
import { codeForNode, sharedKnowledge } from '../data/sharedKnowledge'

const labels: Record<string,string> = { original_material_unverified_facts:'原始资料，事实与有效性仍须核验', reviewed_knowledge_hash_verified:'知识审核与文件版本已匹配', knowledge_review_pending:'知识整理待审核', generated_or_navigation_note:'生成或导航笔记，仅供浏览', navigation_only:'导航，仅供浏览', excluded_root:'候选或归档，不作回答依据', invalid_frontmatter:'笔记属性无法解析，暂不入库' }

export function ExistingMaterials({ nodeId = '' }: { nodeId?: string }) {
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState(nodeId === 'domain-technical' ? 'technical' : nodeId === 'domain-science' ? 'science' : nodeId ? 'design' : '')
  const [code, setCode] = useState(codeForNode(nodeId))
  const [product, setProduct] = useState('')
  const [includeRelated, setIncludeRelated] = useState(false)
  const [includeCandidates, setIncludeCandidates] = useState(false)
  const [page, setPage] = useState(0)
  const rows = useMemo(() => sharedKnowledge.records.filter(r => (includeCandidates || r.layer !== '候选待审核') && (!domain || r.domain === domain) && (!code || r.primary === code || r.primary?.startsWith(code+'.') || (includeRelated && r.related.includes(code))) && (!product || r.product_line_candidates.includes(product)) && (!query || (r.title+' '+r.path).toLowerCase().includes(query.toLowerCase()))), [query,domain,code,product,includeRelated,includeCandidates])
  const lastPage = Math.max(0, Math.ceil(rows.length/50)-1)
  const currentPage = Math.min(page,lastPage)
  const sectionName = sharedKnowledge.taxonomy.find(s => s.id === code)?.name
  const leafName = sharedKnowledge.taxonomy.flatMap(s => s.children).find(([id]) => id === code)?.[1]
  const domainName = sharedKnowledge.architecture.management_domains.find(d => d.id === domain)?.name
  const title = LOCAL_PLATFORM && nodeId ? `${code ? code + ' ' : ''}${sectionName || leafName || domainName || '业务'} · 分类资料` : '现有资料'
  return <section className="panel materials-panel"><h1>{title}</h1>{LOCAL_PLATFORM && nodeId && <p><Link to={'/framework?node=' + encodeURIComponent(nodeId)}>返回当前知识节点</Link></p>}<p>按业务分类查找原件。产品线按名称线索筛选，尚未完成适用性审核；未命中不代表没有资料。</p>
    <p className="sample-empty">{LOCAL_PLATFORM ? <>本页为业务分类目录，包含未进入当前问答范围的资料。分类为待抽检线索，不等于已核知识。<Link to="/materials">查看当前检索资料</Link> · <Link to="/ai">进入当前问答</Link></> : "本页为分类兼容预览；问答仍使用现有平台版本，新候选索引尚未在线生效。"}</p>
    <div className="materials-filters">
      <input aria-label="文件名或路径" placeholder="搜索文件名、路径" value={query} onChange={e => {setQuery(e.target.value);setPage(0)}} />
      <select aria-label="管理域" value={domain} onChange={e=>{setDomain(e.target.value);setCode('');setPage(0)}}><option value="">全部管理域</option>{sharedKnowledge.architecture.management_domains.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
      <select aria-label="业务分类" value={code} onChange={e=>{setCode(e.target.value);setDomain(e.target.value ? 'design' : domain);setPage(0)}}><option value="">全部业务分类</option>{sharedKnowledge.taxonomy.map(s=><optgroup key={s.id} label={s.id+' '+s.name}><option value={s.id}>{s.id+' '+s.name+'（全部）'}</option>{s.children.map(([id,name])=><option key={id} value={id}>{id+' '+name}</option>)}</optgroup>)}</select>
      <select aria-label="产品线名称线索" value={product} onChange={e=>{setProduct(e.target.value);setPage(0)}}><option value="">全部产品线（名称线索）</option>{sharedKnowledge.architecture.product_lines.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <label><input type="checkbox" checked={includeRelated} onChange={e=>{setIncludeRelated(e.target.checked);setPage(0)}}/> 包含相关主题</label>
      <label><input type="checkbox" checked={includeCandidates} onChange={e=>{setIncludeCandidates(e.target.checked);setPage(0)}}/> 显示待审核候选</label>
    </div><p>找到 {rows.length} 条资料记录，其中 {rows.filter(r=>r.answer_eligible).length} 条符合入库身份规则；尚不表示已解析、已索引或能正确回答。</p>
    <div style={{overflowX:'auto'}}><table className="materials-table"><thead><tr><th>资料与原路径</th><th>分类依据</th><th>回答依据身份</th></tr></thead><tbody>{rows.slice(currentPage*50,currentPage*50+50).map(r=><tr key={r.id}><td><a href={'obsidian://open?path='+encodeURIComponent(r.absolute_path)}>{r.title}</a><small style={{display:'block',overflowWrap:'anywhere'}}>{r.path}</small></td><td>{r.primary ? <Link to={'/knowledge/design-code-'+r.primary}>{r.primary}</Link> : '待归类'}<br/>{r.classification_review}</td><td>{labels[r.eligibility_reason] || r.eligibility_reason}</td></tr>)}</tbody></table></div>
    {!rows.length && <p>当前筛选没有匹配资料；可清除产品线或关键词后重试。</p>}
    <button disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>上一屏</button><span> {currentPage+1} / {lastPage+1} </span><button disabled={currentPage===lastPage} onClick={()=>setPage(currentPage+1)}>下一屏</button>
  </section>
}
