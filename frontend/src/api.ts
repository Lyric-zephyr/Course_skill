export type Settings = { subject: string; ai: string; run_mode: string; model: string; mode: string; chapter: string; output_format: string; pdf_engine: string }
export type Options = { subjects: string[]; providers: Record<string, string[]>; modules: string[]; subject_modules: Record<string, string[]>; batch_counts: Record<string, Record<string, number>>; defaults: Settings; api_defaults: Record<string, string>; configured: Record<string, boolean>; cli_models: string[] }
export type Usage = { input: number; output: number; calls: number }
export type Artifact = { id: string; name: string; kind: string; chapter: string; usage?: Usage | null }
export type Question = { chapter: string; count: number }
export type Job = { id: string; kind: string; status: string; percent: number; stage: string; successes: number; failures: number; modules: Record<string, string>; logs: string[]; artifacts: Artifact[]; question?: Question | null; sequence: number }
export const terminal = (job: Job | null) => !job || ['succeeded', 'partial', 'failed'].includes(job.status)
export async function api<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  let response: Response | undefined
  // 只重试读取请求；生成、配置等操作不自动重发，避免创建重复任务。
  const attempts = body === undefined ? 3 : 1
  for (let attempt = 0; attempt < attempts; attempt++) {
    const controller = new AbortController()
    const timeout = body === undefined ? window.setTimeout(() => controller.abort(), 10000) : undefined
    try {
      response = await fetch(`/api/${path}`, { signal: controller.signal, ...(body === undefined ? {} : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) })
      break
    } catch {
      if (attempt === attempts - 1) throw new Error('无法连接本机服务。请保持 main.py 运行，并使用它自动打开的新页面；使用代理时请允许 127.0.0.1 直连。')
      await new Promise(resolve => window.setTimeout(resolve, 500 * (attempt + 1)))
    } finally { if (timeout !== undefined) window.clearTimeout(timeout) }
  }
  if (!response) throw new Error('本机服务没有响应，请重新运行 main.py。')
  if (response.status === 401) throw new Error('页面会话已失效，请使用 main.py 启动时自动打开的新页面。')
  const result = await response.json().catch(() => { throw new Error('本机服务返回异常，请检查运行 main.py 的终端输出。') })
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请求无效，请检查输入')
  return result
}
