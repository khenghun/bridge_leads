// Mirrors backend/app/contract/schemas.py.

import type { Constraints, DealRecord, Seat } from './types'

/** part = the 1-level partscore (every partscore level scores the same),
 * game = 3NT/4M/5m, slam = 6, grand = 7. */
export type ContractKind = 'part' | 'game' | 'slam' | 'grand'

export interface CandidateResult {
  key: string // '4S-S'
  label: string // '4♠' | '♠ partscore'
  level: number
  strain: string
  declarer: Seat
  kind: ContractKind
  tricks_needed: number
  make_rate: number
  mean_tricks: number
  mean_score: number
  fail_mean_score: number | null // null when it never failed
  seat_delta: number // mean tricks, this declarer minus partner
}

export interface OpponentStats {
  opps_game_rate: number
  par_competitive_rate: number | null // null when strains were excluded
}

export interface ContractDealsMatrix {
  candidates: string[] // candidate keys, fixed order
  records: DealRecord[] // one per simulated deal, in generation order
}

export interface ContractResponse {
  num_deals: number
  seat: Seat
  partner: Seat
  vul: string
  candidates: CandidateResult[]
  default_benchmark: string | null
  opponents: OpponentStats
  deals: ContractDealsMatrix
}

export interface ContractRequest {
  hand: string
  seat: Seat
  vul: string
  num_deals: number
  strains: string[]
  constraints: Constraints
}
