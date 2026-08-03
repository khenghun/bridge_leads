import { getJson, postJson } from './http'
import type { ShapeValidation } from './types'
import type { Auction, SimulateRequest, SimulateResponse } from './leadTypes'

export function simulate(req: SimulateRequest): Promise<SimulateResponse> {
  return postJson<SimulateResponse>('/api/simulate', req)
}

/** Shape-text validation — shared by both tools' constraint editors. */
export function validateShape(text: string): Promise<ShapeValidation> {
  return postJson<ShapeValidation>('/api/validate/shape', { text })
}

export async function fetchAuctions(): Promise<Auction[]> {
  const body = await getJson<{ auctions: Auction[] }>('/api/auctions')
  return body.auctions
}
