import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ReadableText } from '../components/ReadableText'
import './TaskbookDraft.css'

type Source = {source_id:string;source_version:string;file_name:string;project:string;stage:string}
type Result = {markdown:string;evidence_markdown:string;source_reader_url:string|null;download_base64:string;draft:{project:string;stage:string;missing_current_fields:string[];review_notes:{title:string;reason:string}[]}}

export function TaskbookDraft(){
  const [sources,setSources]=useState<Source[]>([])
  const [fields,setFields]=useState<{id:string;label:string}[]>([])
  const [sourceId,setSourceId]=useState('');const [project,setProject]=useState('');const [stage,setStage]=useState('施工图设计')
  const [inputs,setInputs]=useState<Record<string,string>>({});const [result,setResult]=useState<Result|null>(null)
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState('正在读取可用原件…');const seq=useRef(0)
  useEffect(()=>{const c=new AbortController();fetch('/api/v2/taskbook/sources',{signal:c.signal,cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error('来源读取失败');return r.json()}).then(p=>{if(!c.signal.aborted){setSources(p.items);setFields(p.fields);setMessage('')}}).catch(()=>{if(!c.signal.aborted)setMessage('原件读取失败，请刷新重试。')});return()=>{c.abort();seq.current++}},[])
  const source=sources.find(s=>s.source_id===sourceId)
  function clearResult(){seq.current++;setResult(null);setMessage('')}
  function choose(value:string){clearResult();setSourceId(value);setInputs({});const s=sources.find(s=>s.source_id===value);setProject(s?.project||'');setStage(s?.stage||'施工图设计')}
  async function generate(){
    const ticket=++seq.current;setBusy(true);setMessage('正在按所选资料生成底稿…');setResult(null)
    try{
      const r=await fetch('/api/v2/taskbook/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:project.trim(),stage,source_id:sourceId,source_version:source?.source_version||'',current_inputs:Object.fromEntries(Object.entries(inputs).filter(([,v])=>v.trim()))})})
      const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==='string'?p.detail:'项目或来源填写不正确，请重新核对。')
      if(ticket===seq.current){setResult(p);setMessage('已生成待复核底稿，可下载保存。')}
    }catch(e){if(ticket===seq.current)setMessage(e instanceof Error?e.message:'生成失败，请重试。')}
    finally{if(ticket===seq.current)setBusy(false)}
  }
  function download(){if(!result)return;const bytes=Uint8Array.from(atob(result.download_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));const a=document.createElement('a');a.href=url;a.download=(result.draft.project+'_'+result.draft.stage+'_编制底稿.zip').replace(/[\\/:*?"<>|]/g,'_');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="taskbook-workbench"><header className="page-hero compact"><div><h1>任务书编制</h1><p>先选项目原件，再形成带依据的草稿。旧版内容尚未确认本次沿用，生成不代表审批或下发。</p></div><Link to="/ai">返回问答</Link></header>
    <article className="panel"><h2>1. 选择项目及资料</h2><label>来源任务书<select style={{width:'100%',minWidth:0}} disabled={busy} value={sourceId} onChange={e=>choose(e.target.value)}><option value="">没有现成原件，先搭骨架</option>{sources.map(s=><option key={s.source_id} value={s.source_id}>{s.project} · {s.file_name}</option>)}</select></label>
      <label>本次项目名称<input maxLength={120} disabled={busy} readOnly={!!source} value={project} onChange={e=>{clearResult();setProject(e.target.value)}} placeholder="请选择原件，或填写需要搭骨架的新项目" /></label>
      <label>设计阶段<select disabled={busy} value={stage} onChange={e=>{clearResult();setStage(e.target.value)}}>{['方案设计','初步设计','施工图设计'].map(s=><option key={s}>{s}</option>)}</select></label>
      <p>{source?'已有明文会转写成底稿，不要求重复录入。补充内容与原文并列保留，核准后再整合，不会自动覆盖原要求。':'未选择原件时只生成待补骨架，不会借用其他项目的指标、日期或份数。'}</p>
      <details><summary>2. 本次有变化或补充时再填写</summary>{fields.map(f=><label key={f.id}>{f.label}<textarea maxLength={6000} disabled={busy} value={inputs[f.id]||''} onChange={e=>{clearResult();setInputs({...inputs,[f.id]:e.target.value})}} placeholder="不填则按所选原件整理；补充内容也将标为待审核" /></label>)}</details>
      <button className="primary-button" disabled={busy||!project.trim()} onClick={generate}>{busy?'正在生成…':'生成待复核草稿'}</button><p role="status">{message}</p>
    </article>
    {result&&<article className="panel" style={{overflowWrap:'anywhere'}}><h2>3. 核对并保存底稿</h2><div className="source-links"><button className="primary-button" onClick={download}>下载草稿与依据</button>{result.source_reader_url&&<Link to={result.source_reader_url} target="_blank" rel="noreferrer">核对本版原件（新窗口）</Link>}</div><p>压缩包包含编制草稿、来源核对表和追溯记录。请先下载保存；刷新页面或切换资料后需重新生成。</p>
      <h3>需要确认的内容</h3>{result.draft.review_notes.length?result.draft.review_notes.map((n,i)=><p key={i}><b>{n.title}：</b>{n.reason}</p>):<p>本次尚未加入单独核读的口径提示，仍须逐项核对版本、范围与签批条件。</p>}
      {!!result.draft.missing_current_fields.length&&<p>仍有{result.draft.missing_current_fields.length}类内容缺资料，已在草稿内保留待补。</p>}
      <details open><summary>查看草稿</summary><ReadableText text={result.markdown}/></details><details><summary>查看完整来源核对表</summary><ReadableText text={result.evidence_markdown}/></details>
    </article>}
  </section>
}
