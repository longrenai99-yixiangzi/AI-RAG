import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { bodyLink,fileLink } from './ProjectRecords'
type Period={id:string;name:string;organization:string;year:number;period:string;boundary:string;coverage:string;source:{source_id:string;source_version:string;file_name:string};primary_sources:{sha256:string;source_path:string}[]}
export function PeriodRecords(){
  const [items,setItems]=useState<Period[]>([]);const [message,setMessage]=useState('正在读取部门与期间资料…')
  useEffect(()=>{const c=new AbortController();fetch('/api/v2/knowledge/periods',{cache:'no-store',signal:c.signal}).then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(p=>{if(c.signal.aborted)return;setItems(p.items);setMessage('')}).catch(()=>{if(!c.signal.aborted)setMessage('期间资料读取失败。')});return()=>c.abort()},[])
  return <section><header className="page-hero compact"><div><h1>部门与期间资料</h1><p>先选择部门、年份和期间，浏览整份资料，再查具体指标。本页不以少数问答摘录代表指标全集。</p></div></header>{message&&<p>{message}</p>}<div className="domain-grid">{items.map(p=><article className="panel" key={p.id}><span>{p.organization} · {p.year}年 · {p.period}</span><h2>{p.name}</h2><p>{p.boundary}</p><p>{p.coverage}</p><Link className="primary-link" to={bodyLink(p.source)}>浏览整份已提取正文</Link><p><a href={fileLink(p.source)}>打开同版资料摘录</a></p>{p.primary_sources.map(s=><p key={s.sha256}><a href={'/api/v2/knowledge/primary-sources/'+s.sha256}>打开原始文档 · {s.source_path.split(/[\\/]/).pop()}</a></p>)}</article>)}</div></section>
}
