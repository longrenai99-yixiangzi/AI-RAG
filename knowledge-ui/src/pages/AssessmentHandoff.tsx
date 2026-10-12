import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReadableText } from '../components/ReadableText'
import './TaskbookDraft.css'

type Item={item_id:string;professional:string;quote:string;kind:string;gap_label?:string;gap_type?:string;dimensions:string[];suggested_action:string;anchors:{table:number;row:number}[];taskbook_routes:{label:string}[]}
type Case={project_id:string;project:string;scope_note:string;gap_policy?:{policy:string};source:{file_name:string;source_version:string;observation_date:string};items:Item[];input_fields:{id:string;label:string}[]}
type Notes=Record<string,Record<string,string>>
type Result={documents:Record<string,string>;download_base64:string;source_reader_url:string;draft:{project:string;items:Item[]}}

export function AssessmentHandoff(){
  const {id}=useParams();const [data,setData]=useState<Case|null>(null)
  const [selected,setSelected]=useState<string[]>([]);const [notes,setNotes]=useState<Notes>({});const [professional,setProfessional]=useState('')
  const [result,setResult]=useState<Result|null>(null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('正在核对项目评估资料…')
  const [canSave,setCanSave]=useState(false);const [storageMessage,setStorageMessage]=useState('');const seq=useRef(0)
  useEffect(()=>{
    const controller=new AbortController();seq.current++;setData(null);setResult(null);setSelected([]);setNotes({});setBusy(false);setProfessional('');setCanSave(false);setMessage('正在核对项目评估资料…');setStorageMessage('')
    fetch('/api/v2/assessment-handoff/projects/'+encodeURIComponent(id||''),{signal:controller.signal,cache:'no-store'}).then(async r=>{const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==='string'?p.detail:'项目资料读取失败');return p as Case}).then(p=>{
      if(controller.signal.aborted)return
      let restored:string[]=[];let updates:Notes={};let saveAllowed=true;let warning=''
      try{
        const raw=localStorage.getItem('assessment_handoff_v1_'+p.project_id+'_'+p.source.source_version)
        if(raw){const saved=JSON.parse(raw);const ids=new Set(p.items.map(i=>i.item_id));const fields=new Set(p.input_fields.map(f=>f.id))
          if(saved.project_id!==p.project_id||saved.source_version!==p.source.source_version||!Array.isArray(saved.selected_ids)||saved.selected_ids.some((v:unknown)=>typeof v!=='string'||!ids.has(v))||!saved.updates||typeof saved.updates!=='object'||Array.isArray(saved.updates))throw new Error()
          for(const [key,values] of Object.entries(saved.updates)){if(!ids.has(key)||!values||typeof values!=='object'||Array.isArray(values)||Object.entries(values).some(([f,v])=>!fields.has(f)||typeof v!=='string'||v.length>2000))throw new Error()}
          restored=[...new Set(saved.selected_ids as string[])];updates=saved.updates;warning='已恢复本项目、本版原件的本机草稿。'
        }
      }catch{saveAllowed=false;warning='本机暂存无法读取，已停止覆盖旧记录；请下载本次生成稿保存。'}
      setSelected(restored);setNotes(updates);setData(p);setCanSave(saveAllowed);setStorageMessage(warning);setMessage('')
    }).catch(e=>{if(!controller.signal.aborted)setMessage(e instanceof Error?e.message:'读取失败，请刷新重试。')})
    return()=>{controller.abort();seq.current++}
  },[id])
  useEffect(()=>{if(!data||!canSave)return;try{localStorage.setItem('assessment_handoff_v1_'+data.project_id+'_'+data.source.source_version,JSON.stringify({project_id:data.project_id,source_version:data.source.source_version,selected_ids:selected,updates:notes}));setStorageMessage('编辑内容已暂存本机浏览器；下载包可另行保存。')}catch{setStorageMessage('本机暂存失败，请在生成后下载保存，避免刷新丢失。')}},[data,selected,notes,canSave])
  function invalidate(){seq.current++;setResult(null);setMessage('')}
  function toggle(value:string){invalidate();setSelected(prev=>prev.includes(value)?prev.filter(v=>v!==value):[...prev,value])}
  function update(item:string,field:string,value:string){invalidate();setNotes(prev=>({...prev,[item]:{...prev[item],[field]:value}}))}
  async function generate(){if(!data)return;const ticket=++seq.current;setBusy(true);setResult(null);setMessage('正在整理勾选事项和同版出处…')
    try{const r=await fetch('/api/v2/assessment-handoff/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:data.project_id,source_version:data.source.source_version,selected_ids:selected,updates:Object.fromEntries(selected.filter(s=>notes[s]).map(s=>[s,notes[s]]))})});const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==='string'?p.detail:'填写信息不正确，请核对后重试。');if(ticket===seq.current){setResult(p);setMessage('已生成准备稿，请核对后下载保存。')}}
    catch(e){if(ticket===seq.current)setMessage(e instanceof Error?e.message:'生成失败，请重试。')}
    finally{if(ticket===seq.current)setBusy(false)}
  }
  function download(){if(!result)return;const bytes=Uint8Array.from(atob(result.download_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));const a=document.createElement('a');a.href=url;a.download=(result.draft.project+'_评估任务准备.zip').replace(/[\\/:*?"<>|]/g,'_');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="taskbook-workbench"><header className="page-hero compact"><div><h1>评估任务准备</h1><p>从评估原文整理任务书补充事项与设计计划准备表。缺内容先按缺项登记，无需先考证历史报告正确性；生成不代表审批、派发或完成。</p></div><Link to={'/projects/'+id}>返回项目资料</Link><Link to={'/projects/'+id+'/scheme-comparison'}>方案比选准备</Link></header><p role="status">{message}</p>
    {data&&<><article className="panel"><h2>{data.project}</h2><p>来源：{data.source.file_name} · 资料截至{data.source.observation_date}</p><p>{data.scope_note}</p>{data.gap_policy&&<p><b>本次处理口径：</b>{data.gap_policy.policy} 缺项先列清，再按资源逐步补齐。</p>}<p>本次共{data.items.length}条准备事项，包括{data.items.filter(i=>i.kind==='未评范围待补评').length}个未评范围；这是缺项及技术事项的工作清单，不把报告缺项直接认作实际设计缺陷。</p><Link to={'/read?primary='+data.source.source_version}>核对B版全文与原图</Link><p role="status">{storageMessage}</p></article>
      <article className="panel"><h2>1. 选择要整理的缺项或技术事项</h2><label>按专业查看<select value={professional} onChange={e=>setProfessional(e.target.value)}><option value="">全部专业</option>{[...new Set(data.items.map(i=>i.professional))].map(p=><option key={p}>{p}</option>)}</select></label>{data.gap_policy&&<button disabled={busy} onClick={()=>{invalidate();setSelected(prev=>[...new Set([...prev,...data.items.filter(i=>(!professional||i.professional===professional)&&i.gap_type!=='TECHNICAL_REVIEW').map(i=>i.item_id)])])}}>选取当前范围的缺项</button>}<p>已选{selected.length}条。可以直接生成缺项清单；补充资料、责任人和日期有了再填，不作为登记缺项的前置条件。</p></article>
      {data.items.filter(i=>!professional||i.professional===professional).map(item=><article className="panel" key={item.item_id} style={{overflowWrap:'anywhere'}}><label><input type="checkbox" style={{width:'auto'}} disabled={busy} checked={selected.includes(item.item_id)} onChange={()=>toggle(item.item_id)}/> {item.professional} · {item.gap_label||item.kind}</label><p><b>原报告记载：</b>{item.quote}</p><p>出处：{item.anchors.map(a=>'第'+a.table+'表第'+a.row+'行').join('、')} · {item.dimensions.join('、')}</p><p><b>准备动作：</b>{item.suggested_action}</p><p>建议归入任务书（待核对）：{item.taskbook_routes.map(r=>r.label).join('、')}</p>
        {selected.includes(item.item_id)&&<details><summary>2. 填写本次依据、任务和安排</summary>{data.input_fields.map(f=><label key={f.id}>{f.label}{f.id.endsWith('_date')?<input type="date" disabled={busy} value={notes[item.item_id]?.[f.id]||''} onChange={e=>update(item.item_id,f.id,e.target.value)}/>:<textarea rows={2} maxLength={2000} disabled={busy} value={notes[item.item_id]?.[f.id]||''} onChange={e=>update(item.item_id,f.id,e.target.value)} placeholder="有资料或安排时再填；不填也可先登记缺项"/>}</label>)}</details>}
      </article>)}
      <article className="panel"><h2>3. 生成并下载准备稿</h2><button className="primary-button" disabled={busy||!selected.length} onClick={generate}>{busy?'正在生成…':'生成勾选事项的准备稿'}</button><p>不会自动写入知识库或已批准的任务书、计划；没有补评和复核证据时，不会自动销项。</p>{result&&<><button className="primary-button" onClick={download}>下载任务准备、任务书补充与计划表</button><p>下载包内五份材料使用相同事项编号，可以互相核对。</p>{Object.entries(result.documents).map(([name,text])=><details key={name}><summary>{name.replace('.md','')}</summary><ReadableText text={text}/></details>)}</>}</article>
    </>}
  </section>
}
