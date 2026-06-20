// Mirrors backend/app/schemas.py.

export type Mode = 'matchpoints' | 'imps'
export type Seat = 'N' | 'E' | 'S' | 'W'
export type Suit = 'S' | 'H' | 'D' | 'C'

export interface LeadResult {
  card: string
  defense_tricks: number
  declarer_tricks: number
  defeat_rate: number
  matchpoints: number
  imps: number
}

export interface SampleDeal {
  layout: Record<string, string> // {seat: 'S.H.D.C'}
  declarer_tricks: number
  defense_tricks: number
}

export interface SimulateResponse {
  num_simulations: number
  leads: LeadResult[]
  best_mp: string | null
  best_imp: string | null
  samples: Record<string, SampleDeal[]>
  leader: Seat
  meta: { level: number; strain: string; declarer: string }
}

export interface Auction {
  name: string
  contract: string
  declarer: Seat
  hcp: Record<string, [number, number]>
  shapes_text: Record<string, string>
  note: string
}

export interface Constraints {
  hcp: Record<string, [number, number]>
  suit_length: Record<string, Record<string, [number, number]>>
  shapes: Record<string, string>
}

export interface SimulateRequest {
  leader_hand: string
  level: number
  strain: string
  declarer: string
  vul: string
  penalty: string
  num_simulations: number
  constraints: Constraints
}

export interface ShapeValidation {
  ok: boolean
  terms_count: number
  warnings: string[]
}
