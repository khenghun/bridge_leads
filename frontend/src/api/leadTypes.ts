// Mirrors backend/app/lead/schemas.py.

import type { Constraints, DealRecord, Seat } from './types'

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

export interface DealsMatrix {
  cards: string[] // candidate leads in symbol form ('♥Q'), fixed order
  records: DealRecord[] // one per simulated deal, in generation order
}

export interface SimulateResponse {
  num_simulations: number
  leads: LeadResult[]
  best_mp: string | null
  best_imp: string | null
  samples: Record<string, SampleDeal[]>
  deals: DealsMatrix
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
