export type AssistedEvent = { type: string; msg?: string; stage?: string; sources?: unknown[]; result?: unknown }

export async function sendAssistedQuery(payload: object, signal: AbortSignal, onEvent: (event: AssistedEvent) => void) {
  const response = await fetch('/api/v2/assisted/query', { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(error.detail || `问答接口返回 ${response.status}`)
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('候选接口未返回分阶段响应，未改用旧接口。')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', received = false
  try {
    while (true) {
      const part = await reader.read()
      buffer += decoder.decode(part.value, { stream: !part.done })
      let boundary: RegExpExecArray | null
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index)
        buffer = buffer.slice(boundary.index + boundary[0].length)
        const data = frame.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
        if (data) {
          const event = JSON.parse(data) as AssistedEvent
          if (typeof event.type !== 'string') throw new Error('候选响应事件格式无效。')
          if (event.type === 'result') {
            const result = event.result as { answer?: unknown; citations?: unknown }
            if (!result || typeof result.answer !== 'string' || !Array.isArray(result.citations)) throw new Error('候选回答格式无效，未作为完成结果显示。')
            received = true
          }
          onEvent(event)
        }
      }
      if (part.done) break
    }
    if (!received) throw new Error('响应中断，未收到完成结果；已保存的问题可重新查阅。')
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
