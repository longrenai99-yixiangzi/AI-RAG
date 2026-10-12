import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ReadableText } from '../components/ReadableText'

type Source={source_id:string;source_version:string;file_name:string;role?:string;primary_version?:string}
type Subject={id:string;name:string;coverage:string}
type Project={id:string;name:string;binding_basis:string;qa_available?:boolean;assessment_handoff_available?:boolean;scheme_comparison_available?:boolean;sources:Source[];subjects:Subject[]}
type Record={evidence_id:string;source_id:string;source_version:string;file_name:string;excerpt:string;page:number|null;heading_path?:string}
export const bodyLink=(s:Source)=>s.primary_version?'/read?'+new URLSearchParams({primary:s.primary_version}):'/read?'+new URLSearchParams({source:s.source_id,version:s.source_version})
export const fileLink=(s:Source)=>s.primary_version?'/api/v2/knowledge/primary-sources/'+encodeURIComponent(s.primary_version):'/api/v2/knowledge/sources/'+encodeURIComponent(s.source_id)+'/file?'+new URLSearchParams({source_version:s.source_version})

export function ProjectRecords(){
  const {id}=useParams();const [params]=useSearchParams();const subject=params.get('subject')||''
  const [projects,setProjects]=useState<Project[]>([]);const [detail,setDetail]=useState<{project:Project;subject:Subject;items:Record[]}|null>(null);const [message,setMessage]=useState('正在读取同版项目资料…')
  useEffect(()=>{const c=new AbortController();setDetail(null);setProjects([]);setMessage('正在读取同版项目资料…')
    const url=id?'/api/v2/knowledge/projects/'+encodeURIComponent(id)+'?'+new URLSearchParams({subject}):'/api/v2/knowledge/projects'
    fetch(url,{signal:c.signal,cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error();return r.json()}).then(p=>{if(c.signal.aborted)return;if(id)setDetail(p);else setProjects(p.items);setMessage('')}).catch(()=>{if(!c.signal.aborted)setMessage('项目资料读取失败，请检查服务。')});return()=>c.abort()
  },[id,subject])
  return <section className="project-records"><header className="page-hero compact"><div><h1>{detail?.project.name||'按项目查阅'}</h1><p>先确定项目，再查具体事项和原文。资料按项目和版本核对；仅作原件阅读与准备的项目单独标明。</p></div><Link to="/framework">通用方法与分类</Link></header>{message&&<p className="empty-runtime">{message}</p>}
    {!id&&<div className="domain-grid">{projects.map(p=><Link className="space-card" key={p.id} to={'/projects/'+p.id}><h2>{p.name}</h2><p>{p.sources.length}份同版资料 · {p.subjects.length}个可查事项</p><p>{p.binding_basis}</p><b>进入项目资料</b></Link>)}</div>}
    {detail&&<><div className="scope-banner"><b>当前项目：{detail.project.name}</b><Link to="/projects">切换项目</Link>{detail.project.scheme_comparison_available&&<Link to={'/projects/'+detail.project.id+'/scheme-comparison'}>方案比选准备</Link>}{detail.project.assessment_handoff_available&&<Link to={'/projects/'+detail.project.id+'/assessment-tasks'}>评估任务准备</Link>}{detail.project.qa_available!==false&&<Link to={'/ai?'+new URLSearchParams({project:detail.project.id,q:detail.subject.name+'有哪些已明确的内容？'})}>在此项目范围内提问</Link>}<Link to={'/search?'+new URLSearchParams({project:detail.project.id,mode:detail.project.qa_available===false?'documents':'content',q:detail.project.qa_available===false?'设计评估':detail.subject.id==='plan'?'设计进度':detail.subject.id==='contract'?'合同':detail.subject.name})}>在此项目内搜索</Link></div>
      <nav className="subject-tabs">{detail.project.subjects.map(s=><Link key={s.id} className={s.id===detail.subject.id?'selected':''} to={'/projects/'+id+'?subject='+s.id}>{s.name}</Link>)}</nav>
      <article className="panel"><h2>{detail.subject.name}</h2><p>{detail.subject.coverage}</p><div className="source-links">{detail.project.sources.map(s=><div key={s.source_id}><b>{s.file_name}</b><small>{s.role}</small><Link to={bodyLink(s)}>浏览这份资料正文</Link><a href={fileLink(s)}>打开本版原文件</a></div>)}</div></article>
      <section className="project-evidence"><h2>与当前事项关联的原文</h2><p>保留项目复盘上下文；摘录不等于签署合同或正式计划台账。</p>{detail.items.length?detail.items.map(r=><article className="panel" key={r.evidence_id}><h3>{r.file_name} · {r.page?`第${r.page}页／段`:r.heading_path||'原文位置'}</h3><ReadableText text={r.excerpt}/><Link to={'/sources?'+new URLSearchParams({source_id:r.source_id,source_version:r.source_version,evidence_id:r.evidence_id})}>核对本条原文位置</Link></article>):<p className="empty-runtime">{detail.project.qa_available===false?'本项目当前提供原文、附图与准备底稿，请从上方正文入口进入；该来源尚未加入自动问答。':'该事项尚未关联到可读段落；请查看上方原资料，不能据此认定资料不存在。'}</p>}</section>
    </>}
  </section>
}
