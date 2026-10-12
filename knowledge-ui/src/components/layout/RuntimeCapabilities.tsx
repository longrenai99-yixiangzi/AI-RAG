import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type RuntimeInfo = { service_kind: string; display_name: string; release_name: string; release_status?: string; package_manifest_sha256?: string; candidate_hash?: string; features: Record<string, boolean> }
type RuntimeState = { runtime: RuntimeInfo | null; loading: boolean; error: string }
const Context = createContext<RuntimeState>({ runtime: null, loading: true, error: '' })

export function RuntimeCapabilitiesProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<RuntimeState>({ runtime: null, loading: true, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v2/runtime-capabilities', { cache: 'no-store', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(); return response.json() as Promise<RuntimeInfo> })
      .then(runtime => { if (!runtime.features || !runtime.display_name) throw new Error(); setState({ runtime, loading: false, error: '' }) })
      .catch(() => { if (!controller.signal.aborted) setState({ runtime: null, loading: false, error: '当前可用功能信息读取失败，请刷新页面或检查服务。' }) })
    return () => controller.abort()
  }, [])
  return <Context.Provider value={state}>{children}</Context.Provider>
}

export const useRuntimeCapabilities = () => useContext(Context)

export function RuntimeFeature({ feature, title, children }: { feature: string; title: string; children: ReactNode }) {
  const { runtime, loading, error } = useRuntimeCapabilities()
  if (loading) return <p className="empty-runtime">正在核对当前版本可用功能…</p>
  if (error) return <p className="runtime-error">{error}</p>
  if (!runtime?.features[feature]) return <section className="panel"><h1>{title}</h1><p>当前版本尚未提供这项功能。请通过 Codex 完成受控处理。</p><p>当前页面：{runtime?.display_name}</p></section>
  return <>{children}</>
}
