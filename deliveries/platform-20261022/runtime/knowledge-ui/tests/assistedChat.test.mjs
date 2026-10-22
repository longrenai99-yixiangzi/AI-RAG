import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/assistedChat.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const { sendAssistedQuery } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

async function withResponse(response, action) {
  const original = globalThis.fetch
  globalThis.fetch = async () => response
  try { await action() } finally { globalThis.fetch = original }
}

test('split UTF8 and CRLF frames retain stages and result', async () => {
  const bytes = new TextEncoder().encode('data: {"type":"status","msg":"正在查阅"}\r\n\r\ndata: {"type":"result","result":{"answer":"原文条件仍保留","citations":[]}}\n\n')
  const stream = new ReadableStream({ start(controller) { for (let i=0;i<bytes.length;i+=3) controller.enqueue(bytes.slice(i,i+3));controller.close() } })
  await withResponse(new Response(stream, { headers: { 'Content-Type':'text/event-stream' } }), async () => {
    const events=[];await sendAssistedQuery({},new AbortController().signal,e=>events.push(e))
    assert.equal(events[0].msg,'正在查阅');assert.equal(events[1].result.answer,'原文条件仍保留')
  })
})

test('interrupted result is not reported as complete', async () => {
  await withResponse(new Response('data: {"type":"status","msg":"正在查阅"}\n\n', { headers: { 'Content-Type':'text/event-stream' } }), async () => {
    await assert.rejects(sendAssistedQuery({},new AbortController().signal,()=>{}),/未收到完成结果/)
  })
})

test('malformed completion and missing route never fall back to old answers', async () => {
  await withResponse(new Response('data: {"type":"result","result":{}}\n\n', { headers: { 'Content-Type':'text/event-stream' } }), async () => {
    await assert.rejects(sendAssistedQuery({},new AbortController().signal,()=>{}),/回答格式无效/)
  })
  await withResponse(new Response('{"detail":"候选接口未部署"}', { status:404,headers:{'Content-Type':'application/json'} }), async () => {
    await assert.rejects(sendAssistedQuery({},new AbortController().signal,()=>{}),/候选接口未部署/)
  })
})
