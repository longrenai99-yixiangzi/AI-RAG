export async function platformApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), path === 'query' || path.startsWith('generation/') || path.startsWith('backups') ? 180000 : 12000)
  try {
    const response = await fetch(`/api/platform/${path}`, { method, cache: 'no-store', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-Platform-Request': '1' }, ...(body ? { body: JSON.stringify(body) } : {}) })
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('当前服务尚未接入该平台功能，请检查当前入口。')
    const result = await response.json()
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '填写内容不完整或格式错误，请检查表单。')
    return result
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('等待超时。问题可能仍在处理，可刷新历史记录查看；未自动重新发送。')
    throw error
  } finally { clearTimeout(timer) }
}
