// Shared fetch helpers. URLs are relative: the Vite dev server proxies /api to
// :8000 and in production nginx serves both from one origin.

/** Extract FastAPI's `detail` (string or validation array) into a message. */
export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? JSON.stringify(d)).join('; ')
  } catch {
    /* fall through to statusText */
  }
  return res.statusText || `HTTP ${res.status}`
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<T>
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<T>
}
