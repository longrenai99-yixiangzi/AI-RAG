import type { ReactNode } from 'react'

function clean(text: string) {
  return text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, label) => label || target).replace(/\*\*/g, '')
}

// Render the text/table syntax in our source records; never interpret source HTML.
export function ReadableText({ text }: { text: string }) {
  const lines=text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,'').split(/\r?\n/)
  const nodes: ReactNode[]=[]
  for(let i=0;i<lines.length;i++) {
    const line=lines[i].trim()
    if(!line)continue
    if(line.startsWith('|')&&/^\|?\s*:?-{3}/.test((lines[i+1]||'').trim())) {
      const cells=(s:string)=>s.trim().replace(/^\||\|$/g,'').split('|').map(c=>clean(c).replace(/<br\s*\/?>/gi,'\n'))
      const header=cells(line);const rows:string[][]=[];i+=2
      while(i<lines.length&&lines[i].trim().startsWith('|'))rows.push(cells(lines[i++]))
      i--
      nodes.push(<div className="readable-table" key={nodes.length}><table><thead><tr>{header.map((c,j)=><th key={j}>{c}</th>)}</tr></thead><tbody>{rows.map((r,j)=><tr key={j}>{r.map((c,k)=><td key={k} style={{whiteSpace:'pre-wrap'}}>{c}</td>)}</tr>)}</tbody></table></div>)
    } else if(/^#{1,6}\s/.test(line)) {
      nodes.push(<h3 key={nodes.length}>{clean(line.replace(/^#{1,6}\s+/,''))}</h3>)
    } else {
      const parts=line.split(/(?=\s[一二三四五六七八九十]是)/)
      nodes.push(<div key={nodes.length}>{parts.map((p,j)=><p key={j}>{clean(p.replace(/^[-*>]\s*/,''))}</p>)}</div>)
    }
  }
  return <div className="readable-text">{nodes}</div>
}
