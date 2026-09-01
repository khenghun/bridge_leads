// Mirrors backend/app_play/schemas.py — hand-kept in sync, as the other tools do.
//
// The play API is stateless: every request carries the whole deal, the
// contract and the play so far. LIN never leaves the browser (see lib/lin.ts).

import type { Constraints, Seat } from './types'

/** `single_dummy` samples the hands the graded seat could not see and solves
 * every candidate card on each sample; `double_dummy` grades against the
 * actual deal — hindsight, one solve per decision, no sampling. */
export type PlayMethod = 'single_dummy' | 'double_dummy'

export type DecisionStatus = 'optimal' | 'good' | 'suboptimal' | 'forced'

/** The role the graded seat plays. Dummy is not gradable (the backend 422s). */
export type PlayRole = 'declarer' | 'defender'

/** Expert opponents (v1.3): sampled layouts must also be consistent with the
 * opponents' earlier plays having been best plays *given what they could
 * see* — judged by a Monte-Carlo from each opponent's own view. Mirrors the
 * engine's `ExpertSettings`; the backend fills defaults when omitted. */
export interface ExpertOptions {
  /** Inner sample cap as a fraction of `num_deals` (floor 8). */
  inner_ratio: number
  /** tol₀: how much better an alternative must be shown to be, in tricks. */
  tolerance: number
  /** z: standard errors of evidence a rejection needs. */
  confidence: number
  /** Outer layouts examined per consistent layout wanted before giving up. */
  budget: number
  /** Judge every opponent decision, not only the ones that lost a
   * double-dummy trick on the layout — slower, catches a play that worked on
   * the actual hand but was wrong single-dummy. */
  strict: boolean
  /** Recursion depth; 1 is the design, 2 exists as a knob. */
  depth: number
}

/** What the expert filter did for one decision. */
export interface ExpertStats {
  /** Layouts examined (accepted + rejected). */
  sampled: number
  /** Layouts the decision was graded on. */
  consistent: number
  /** Layouts that went through the double-dummy trace (0 in strict mode). */
  traced: number
  /** Inner judgements run; `memo_hits` were answered from the memo. */
  judged: number
  memo_hits: number
  /** The filter rejects a play shown at least this many tricks worse. */
  threshold: number
  /** Observed sd of the paired difference, when any judgement ran. */
  sigma: number | null
  /** `filtered` normally; `none` when nothing survived (graded on the
   * unfiltered sample — the opponents may have erred); `trivial` when there
   * was nothing to judge yet (the opening lead). */
  inference: 'filtered' | 'none' | 'trivial'
}

/** The state every play request carries. */
export interface PlayState {
  /** All four hands as PBN 'spades.hearts.diamonds.clubs' — 52 distinct cards. */
  hands: Record<Seat, string>
  level: number
  /** 'N' for notrump, else 'S' | 'H' | 'D' | 'C'. */
  strain: string
  declarer: Seat
  /** 'none' | 'ns' | 'ew' | 'both'. */
  vul: string
  /** 'none' | 'doubled' | 'redoubled'. */
  penalty: string
  /** Cards in endplay form ('HK', 'DT'), from the opening lead, in order. */
  play: string[]
  method: PlayMethod
  /** 5–200; ignored for double_dummy. */
  num_deals: number
  /** Only the seats the graded player cannot see may be constrained. */
  constraints: Constraints
  /** Expert opponents (v1.3). Off by default; `expert` and
   * `expert_constraints` are read only when on. */
  expert_opponents?: boolean
  expert?: ExpertOptions | null
  /** The user's constraints on every seat — the auction was public, so an
   * opponent judging their own play knew them too. Unlike `constraints`,
   * the graded seat's own hand may appear here. */
  expert_constraints?: Constraints | null
}

export interface AnalyzeRequest extends PlayState {
  /** Whose decisions to grade. Dummy → 422; for the declarer this includes
   * the cards played from dummy. */
  seat: Seat
  /** Play indices to grade in this call — a chunk of a slow analysis, merged
   * client-side (`mergeChunks`). Omitted = every decision of the seat. */
  decisions?: number[]
}

/** One legal card at a decision point, priced in tricks for the graded side. */
export interface CardOption {
  card: string
  /** Mean tricks for the graded side across the sampled deals. */
  tricks: number
  /** Make rate for a declarer, defeat rate for a defender. */
  success_rate: number
  /** Mean duplicate score for the graded side (contract, vulnerability and
   * doubling applied), in points. */
  score: number
  /** Mean per-deal IMP swing of this card against the trick-best card on the
   * same deal — 0 for the best card, ≤ 0 below it, and occasionally > 0 for
   * a card that scores better than the trick-best one. */
  imps: number
}

export interface Decision {
  /** Index into the request's `play` array. */
  index: number
  /** 1-based trick number. */
  trick: number
  /** 1–4: where in the trick this card fell. */
  position: number
  /** The seat the card came from (dummy's cards appear in declarer's list). */
  hand: Seat
  /** endplay input form ('HK', 'DT') — identical to the request's play[index],
   * so string equality against `options[].card` is safe. Never the lead tool's
   * unicode '♥K'. */
  card: string
  /** Only one legal card: nothing was solved, `options` and `best_cards` are
   * empty and the three trick numbers are null. Counted in summary.decisions
   * but not in summary.graded. */
  forced: boolean
  /** null on a forced decision: nothing was solved, so there is no number. */
  actual_tricks: number | null
  best_tricks: number | null
  /** actual − best, so ≤ 0; the classifier's input. null when forced. */
  diff: number | null
  /** Mean duplicate score (graded side) of the card played / of the best card. */
  actual_score: number | null
  best_score: number | null
  /** Points, actual − best. */
  score_diff: number | null
  /** Mean per-deal IMPs, actual − best (≤ 0). The cost that distinguishes an
   * overtrick from a game. */
  imp_diff: number | null
  status: DecisionStatus
  /** Every legal card, best first. */
  options: CardOption[]
  best_cards: string[]
  /** Present when expert opponents were on and the decision was sampled. */
  expert?: ExpertStats | null
}

export interface AnalyzeSummary {
  /** Every decision, forced ones included. */
  decisions: number
  /** The ones actually solved — `decisions` minus the forced ones. */
  graded: number
  optimal: number
  good: number
  suboptimal: number
  total_trick_loss: number
  /** total_trick_loss / graded. */
  avg_trick_loss: number
  /** Points and IMPs given up across the graded decisions. */
  total_score_loss: number
  total_imp_loss: number
}

export interface AnalyzeResponse {
  seat: Seat
  role: PlayRole
  /** The steady-state pair the graded seat could see — [declarer, dummy] or
   * [defender, dummy]. The other two seats are the sampled (constrainable)
   * ones; a constraint aimed at a visible seat comes back as a 422. */
  visible: Seat[]
  /** For the graded side: level+6 declaring, 14−(level+6) defending. */
  tricks_needed: number
  decisions: Decision[]
  summary: AnalyzeSummary
  method: PlayMethod
  /** Echoed back as 1 for double_dummy, which does no sampling. */
  num_deals: number
  /** The expert settings the grade was made under; null when off. */
  expert?: ExpertOptions | null
}

/** The interactive primitive: grade whoever is on play at this position.
 * Same state as an analyze request, minus `seat` — the play history decides
 * whose turn it is. The UI for playing on from here is deferred; the endpoint
 * exists, and this is the type to build it against. */
export type PositionRequest = PlayState

export interface PositionResponse {
  to_play: Seat
  role: PlayRole
  /** Whose eyes the position was solved through — declarer when dummy is on play. */
  view: Seat
  visible: Seat[]
  /** 1-based trick number, and the index this card would take in `play`. */
  trick: number
  index: number
  forced: boolean
  legal_cards: string[]
  tricks_won: { NS: number; EW: number }
  tricks_needed: number
  options: CardOption[]
  method: PlayMethod
  num_deals: number
  expert?: ExpertStats | null
}
