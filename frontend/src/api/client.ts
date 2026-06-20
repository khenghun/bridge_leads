import type {
  Auction, ShapeValidation, SimulateRequest, SimulateResponse,
} from './types'

/** Extract FastAPI's `detail` (string or validation array) into a message. */
async function errorMessage(res: Response): Promise<string> {
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

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<T>
}

export function simulate(req: SimulateRequest): Promise<SimulateResponse> {
  return postJson<SimulateResponse>('/api/simulate', req)
}

export function validateShape(text: string): Promise<ShapeValidation> {
  return postJson<ShapeValidation>('/api/validate/shape', { text })
}

export async function fetchAuctions(): Promise<Auction[]> {
  const res = await fetch('/api/auctions')
  if (!res.ok) throw new Error(await errorMessage(res))
  const body = (await res.json()) as { auctions: Auction[] }
  return body.auctions
}
