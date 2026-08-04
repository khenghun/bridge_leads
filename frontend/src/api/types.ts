// Shared vocabulary — mirrors backend/app/common/schemas.py.
// Per-tool payloads live in ./leadTypes.ts and ./contractTypes.ts.

export type Mode = 'matchpoints' | 'imps'
export type Seat = 'N' | 'E' | 'S' | 'W'
export type Suit = 'S' | 'H' | 'D' | 'C'
/** Suit quality: 'good' = 2 of AKQ or 3 of AKQJT; 'poor' = worse than that. */
export type Quality = 'good' | 'poor'

export interface DealRecord {
  layout: Record<string, string> // {seat: 'S.H.D.C'}
  tricks: number[] // declarer tricks per candidate, aligned to the matrix's list
  scores: number[] // score per candidate, in the tool's perspective, aligned
}

/** Per-deal matrix, generic over what a "candidate" is: opening leads in the
 * lead tool ('♥Q'), contract keys in the contract tool ('4S-S'). */
export interface CandidateMatrix {
  candidates: string[]
  records: DealRecord[]
}

export interface Constraints {
  hcp: Record<string, [number, number]>
  suit_length: Record<string, Record<string, [number, number]>>
  shapes: Record<string, string>
  /** At most one entry in total — the backend rejects more with a 422. */
  quality: Record<string, Record<string, Quality>>
  /** Cards pinned into an unseen hand, endplay form ('HA', 'DT'). A card may
   * appear once across the whole table and never in your own hand. */
  fixed_cards: Record<string, string[]>
}

export interface ShapeValidation {
  ok: boolean
  terms_count: number
  warnings: string[]
}
