import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReadableText } from '../components/ReadableText'
import './TaskbookDraft.css'

type Fields={id:string;label:string}[]
type Topic={topic_id:string;subject:string;source_item_id:string;quote:string;baseline_reference:string;candidate_reference:string;condition:string}
type Case={project_id:string;project:string;source:{source_version:string;observation_date:string};topics:Topic[];separate_checks:{item_id:string;quote:string}[];common_fields:Fields;option_fields:Fields;scope_note:string}
type Inputs=Record<string,string>
type Result={documents:Record<string,string>;download_base64:string;draft:{project:string;topic:Topic;gaps:string[];cost_comparison:{summary:string};time_comparison:{summary:string}}}

export function SchemeComparison(){
  const {id}=useParams();const [data,setData]=useState<Case|null>(null);const [topicId,setTopicId]=useState('')
  const [common,setCommon]=useState<Inputs>({});const [options,setOptions]=useState<Inputs[]>([{},{}]);const [result,setResult]=useState<Result|null>(null)
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState('正在核对项目比选议题…');const [storage,setStorage]=useState('');const [canSave,setCanSave]=useState(false);const seq=useRef(0)
  const key=(p:Case,t:string)=>'scheme_comparison_v1_'+p.project_id+'_'+p.source.source_version+'_'+t
  function loadTopic(p:Case,t:string){seq.current++;setResult(null);setTopicId(t);setBusy(false);setMessage('');let a:Inputs={};let b:Inputs[]=[{},{}];let allowed=true;let note=''
    try{const raw=localStorage.getItem(key(p,t));if(raw){const saved=JSON.parse(raw);const valid=(v:unknown,fields:Fields)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.entries(v).every(([k,value])=>fields.some(f=>f.id===k)&&typeof value==='string'&&value.length<=2000)
      if(saved.project_id!==p.project_id||saved.source_version!==p.source.source_version||saved.topic_id!==t||!valid(saved.common,p.common_fields)||!Array.isArray(saved.options)||saved.options.length!==2||saved.options.some((v:unknown)=>!valid(v,p.option_fields)))throw new Error()
      a=saved.common;b=saved.options;note='已恢复本项目、本版资料和本议题的草稿。'}}catch{allowed=false;note='本机暂存无法读取，已停止覆盖旧记录；请生成后下载保存。'}
    setCommon(a);setOptions(b);setCanSave(allowed);setStorage(note)
  }
  useEffect(()=>{const c=new AbortController();seq.current++;setData(null);setCanSave(false);setResult(null);setBusy(false);setMessage('正在核对项目比选议题…')
    fetch('/api/v2/scheme-comparison/projects/'+encodeURIComponent(id||''),{signal:c.signal,cache:'no-store'}).then(async r=>{const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==='string'?p.detail:'比选议题读取失败');return p as Case}).then(p=>{if(!c.signal.aborted){setData(p);loadTopic(p,p.topics[0]?.topic_id||'')}}).catch(e=>{if(!c.signal.aborted)setMessage(e instanceof Error?e.message:'读取失败，请重试。')});return()=>{c.abort();seq.current++}
  },[id])
  useEffect(()=>{if(!data||!topicId||!canSave)return;try{localStorage.setItem(key(data,topicId),JSON.stringify({project_id:data.project_id,source_version:data.source.source_version,topic_id:topicId,common,options}));setStorage('编辑已暂存本机浏览器，仍建议下载另存。')}catch{setStorage('本机暂存失败，请在生成后下载，避免刷新丢失。')}},[data,topicId,common,options,canSave])
  function invalidate(){seq.current++;setResult(null);setMessage('')}
  const topic=data?.topics.find(t=>t.topic_id===topicId)
  async function generate(){if(!data||!topic)return;const ticket=++seq.current;setBusy(true);setResult(null);setMessage('正在按原文和本次填写整理比选准备稿…')
    try{const r=await fetch('/api/v2/scheme-comparison/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:data.project_id,source_version:data.source.source_version,topic_id:topicId,common,options})});const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==='string'?p.detail:'填写内容不正确，请核对后重试。');if(ticket===seq.current){setResult(p);setMessage('准备稿已生成，缺项已列明；未自动选定方案。')}}
    catch(e){if(ticket===seq.current)setMessage(e instanceof Error?e.message:'生成失败，请重试。')}finally{if(ticket===seq.current)setBusy(false)}
  }
  function download(){if(!result)return;const bytes=Uint8Array.from(atob(result.download_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));const a=document.createElement('a');a.href=url;a.download=(result.draft.project+'_'+result.draft.topic.subject+'_比选准备.zip').replace(/[\\/:*?"<>|]/g,'_');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="taskbook-workbench"><header className="page-hero compact"><div><h1>方案比选准备</h1><p>先明确同一比较对象，再分别记录技术、成本、施工用时、运维和风险。没资料也可以先生成缺项表，不自动选定方案。</p></div><Link to={'/projects/'+id}>项目资料</Link><Link to={'/projects/'+id+'/assessment-tasks'}>缺项与任务准备</Link></header><p role="status">{message}</p>
    {data&&topic&&<><article className="panel"><h2>{data.project}</h2><p>原报告资料截至{data.source.observation_date}。{data.scope_note}</p><label>选择准备议题<select value={topicId} disabled={busy} onChange={e=>loadTopic(data,e.target.value)}>{data.topics.map(t=><option key={t.topic_id} value={t.topic_id}>{t.subject}</option>)}</select></label><p><b>原报告记载：</b>{topic.quote}</p><p><b>保留原文条件：</b>{topic.condition}</p><p>基准参考：{topic.baseline_reference||'原报告未给出基准方案，按缺项保留。'}；候选参考：{topic.candidate_reference}</p><p>以上只是原报告参考，尚未填成本、施工用时，也不认定本次实际采用。</p><Link to={'/read?primary='+data.source.source_version}>核对原报告</Link><p role="status">{storage}</p></article>
      <article className="panel"><h2>1. 有资料时再填写比较口径</h2><p>可以先留空直接生成。费用要比较同一范围、数量、价格时点及税费；施工用时要比较相同前置条件与工作范围。</p><details><summary>补充本次比较范围和条件</summary>{data.common_fields.map(f=><label key={f.id}>{f.label}<textarea rows={2} maxLength={2000} disabled={busy} value={common[f.id]||''} onChange={e=>{invalidate();setCommon(prev=>({...prev,[f.id]:e.target.value}))}} placeholder="有资料再填，未知先保留缺项"/></label>)}</details></article>
      <article className="panel"><h2>2. 两方案分别填写</h2><p>原报告未写的方案、价格和施工用时不会猜填。成本只填金额，单位另选；施工用时填写该方案需要的天数，不填写节省天数。</p><details><summary>按需补充两方案资料</summary>{options.map((option,index)=><div key={index}><h3>方案{index===0?'A':'B'}</h3>{data.option_fields.map(f=><label key={f.id}>{f.label}{f.id==='cost_unit'||f.id==='constraint_status'?<select disabled={busy} value={option[f.id]||(f.id==='constraint_status'?'待核对':'')} onChange={e=>{invalidate();setOptions(prev=>prev.map((v,i)=>i===index?{...v,[f.id]:e.target.value}:v))}}>{(f.id==='cost_unit'?['','元','万元']:['待核对','满足','不满足']).map(v=><option key={v} value={v}>{v||'单位待补'}</option>)}</select>:<textarea rows={2} maxLength={2000} disabled={busy} value={option[f.id]||''} onChange={e=>{invalidate();setOptions(prev=>prev.map((v,i)=>i===index?{...v,[f.id]:e.target.value}:v))}} placeholder="有资料再填，未知先保留缺项"/>}</label>)}</div>)}</details></article>
      <article className="panel"><h2>3. 生成、核对并下载</h2><button className="primary-button" disabled={busy} onClick={generate}>{busy?'正在生成…':'生成比选准备与缺项表'}</button><p>数字和比较口径齐全时，只计算已填成本或施工用时差额；不自动排名、审批或发布知识。</p>{result&&<><p>本次仍有{result.draft.gaps.length}项输入缺项。</p><p>{result.draft.cost_comparison.summary}</p><p>{result.draft.time_comparison.summary}</p><button className="primary-button" onClick={download}>下载比选准备、对照表与来源材料</button>{Object.entries(result.documents).map(([name,text])=><details key={name}><summary>{name.replace('.md','')}</summary><ReadableText text={text}/></details>)}</>}</article>
      <article className="panel"><details><summary>另列的技术核对事项（{data.separate_checks.length}条）</summary><p>这些事项尚不构成同一对象下的两套可选方案，先保留原文和资料核对；不强行组成比选，也不要求先考证旧报告才能整理。</p>{data.separate_checks.map(i=><p key={i.item_id}>{i.quote}</p>)}</details></article>
    </>}
  </section>
}
