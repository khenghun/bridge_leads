// Pure bridge helpers ported from the old Streamlit app.py.

import type {
  CandidateMatrix, Constraints, DealRecord, Mode, Quality, Seat, Suit,
} from '../api/types'
import type { DealsMatrix } from '../api/leadTypes'

export const SEATS: Seat[] = ['N', 'E', 'S', 'W']
export const SEAT_NAME: Record<Seat, string> = {
  N: 'North', E: 'East', S: 'South', W: 'West',
}
export const SUITS: Suit[] = ['S', 'H', 'D', 'C']
export const SUIT_SYMBOL: Record<Suit, string> = { S: '♠', H: '♥', D: '♦', C: '♣' }

// Four-colour suit scheme (easier to tell apart than the two-colour default).
export const SUIT_COLOR: Record<Suit, string> = {
  S: '#2563eb', H: '#e74c3c', D: '#e8820c', C: '#27ae60',
}
// The simulator returns cards already as '♥Q'; map the leading symbol -> colour/letter.
export const SYMBOL_COLOR: Record<string, string> = Object.fromEntries(
  SUITS.map((s) => [SUIT_SYMBOL[s], SUIT_COLOR[s]]),
)
export const SYMBOL_LETTER: Record<string, Suit> = Object.fromEntries(
  SUITS.map((s) => [SUIT_SYMBOL[s], s]),
) as Record<string, Suit>

// Suit quality (see backend/engine/suit_quality.py — keep the wording in sync).
export const QUALITY_HINT =
  'Suit quality — good: 2 of AKQ, or 3 of AKQJT (the suit a preempt or overcall'
  + ' promises). poor: anything worse. Only one suit in the whole table can be'
  + ' graded, since it comes from the one player who described a suit.'

/** Set the one table-wide suit-quality constraint, clearing any previous one.
 *
 * The engine accepts exactly one across all seats (it models the single player
 * who described a suit in the auction), so the selects behave as one radio
 * group rather than as independent per-suit fields. Passing '' clears it. */
export function applyQuality<T extends { quality: Partial<Record<Suit, Quality>> }>(
  prev: Record<Seat, T>, seat: Seat, suit: Suit, level: Quality | '',
): Record<Seat, T> {
  const next = { ...prev }
  for (const s of SEATS) next[s] = { ...prev[s], quality: {} }
  if (level) next[seat] = { ...next[seat], quality: { [suit]: level } }
  return next
}

export const RANKS = 'AKQJT98765432'
const RANK_ORDER: Record<string, number> = Object.fromEntries(
  RANKS.split('').map((r, i) => [r, i]),
)

export const ERR_RED = '#e74c3c'
export const OK_GREEN = '#27ae60'

/** Opening leader is LHO of declarer. */
export function leaderSeat(declarer: Seat): Seat {
  return SEATS[(SEATS.indexOf(declarer) + 1) % 4]
}
export function dummySeat(declarer: Seat): Seat {
  return SEATS[(SEATS.indexOf(declarer) + 2) % 4]
}
export function partnerSeat(seat: Seat): Seat {
  return SEATS[(SEATS.indexOf(seat) + 2) % 4]
}

export interface ParsedContract {
  level: number
  strain: string // 'N' | 'S' | 'H' | 'D' | 'C'
}

/** Parse '3NT' / '4H' -> {level, strain}. Returns null if invalid. */
export function parseContract(text: string): ParsedContract | null {
  const t = (text || '').trim().toUpperCase().replace(/\s/g, '')
  if (t.length < 2 || !'1234567'.includes(t[0])) return null
  const level = parseInt(t[0], 10)
  const denom = t.slice(1)
  if (denom === 'NT' || denom === 'N') return { level, strain: 'N' }
  if ('SHDC'.includes(denom) && denom.length === 1) return { level, strain: denom }
  return null
}

export function strainLabel(strain: string): string {
  return strain === 'N' ? 'NT' : SUIT_SYMBOL[strain as Suit]
}

/** Validate one suit holding string; returns an error message or null. */
export function holdingError(val: string): string | null {
  const bad = [...val].filter((c) => !RANKS.includes(c))
  if (bad.length) return `invalid: ${[...new Set(bad)].join(' ')}`
  if (new Set(val).size !== val.length) {
    const seen = new Set<string>()
    const dups = [...val].filter((c) => (seen.has(c) ? true : (seen.add(c), false)))
    return `duplicate: ${[...new Set(dups)].join(' ')}`
  }
  return null
}

/** Normalise a raw suit input: uppercase, '10' -> 'T', strip spaces. */
export function normHolding(raw: string): string {
  return (raw || '').trim().toUpperCase().replace(/10/g, 'T').replace(/\s/g, '')
}

export type Holdings = Record<Suit, string>

/** Parse a pasted PBN hand (spades.hearts.diamonds.clubs) into per-suit strings. */
export function parsePbn(raw: string): { holdings?: Holdings; error?: string } {
  const text = (raw || '').trim().toUpperCase().replace(/10/g, 'T').replace(/\s/g, '')
  if (!text) return {}
  const parts = text.split('.')
  if (parts.length !== 4) {
    return { error: 'PBN needs 4 suits separated by dots: spades.hearts.diamonds.clubs' }
  }
  for (const holding of parts) {
    const bad = [...holding].filter((c) => !RANKS.includes(c))
    if (bad.length) return { error: `invalid rank(s): ${[...new Set(bad)].join(' ')}` }
    if (new Set(holding).size !== holding.length) return { error: 'duplicate rank within a suit' }
  }
  const holdings = {} as Holdings
  SUITS.forEach((s, i) => { holdings[s] = parts[i] })
  return { holdings }
}

/** Sort a suit's ranks high-to-low. */
export function sortHolding(chars: string): string {
  return [...chars].sort((a, b) => (RANK_ORDER[a] ?? 99) - (RANK_ORDER[b] ?? 99)).join('')
}

/** Deal a random 13-card hand into per-suit holdings (hand entry only, no solving). */
export function randomHand(rng: () => number = Math.random): Holdings {
  const deck: string[] = []
  for (const s of SUITS) for (const r of RANKS) deck.push(s + r)
  // Fisher–Yates partial shuffle for the first 13.
  for (let i = 0; i < 13; i++) {
    const j = i + Math.floor(rng() * (deck.length - i))
    ;[deck[i], deck[j]] = [deck[j], deck[i]]
  }
  const hand = deck.slice(0, 13)
  const holdings = { S: '', H: '', D: '', C: '' } as Holdings
  for (const s of SUITS) {
    holdings[s] = sortHolding(hand.filter((c) => c[0] === s).map((c) => c[1]).join(''))
  }
  return holdings
}

/** Join per-suit holdings into a PBN string 'S.H.D.C'. */
export function holdingsToPbn(h: Holdings): string {
  return SUITS.map((s) => h[s]).join('.')
}

// ---------------------------------------------------------------------------
// Pinned cards ("East holds ♥AK")
// ---------------------------------------------------------------------------

/** Flatten per-suit holdings into endplay cards: {H: 'AK'} -> ['HA', 'HK']. */
export function holdingsToCards(h: Holdings): string[] {
  return SUITS.flatMap((s) => [...(h[s] || '')].map((r) => s + r))
}

/** 'HA' -> '♥A', for messages the user reads. */
export function cardLabel(card: string): string {
  return (SUIT_SYMBOL[card[0] as Suit] ?? card[0]) + card.slice(1)
}

/** Inverse of holdingsToCards: ['HA','HK','DT'] -> {H:'AK', D:'T', ...}. */
export function cardsToHoldings(cards: string[]): Holdings {
  const holdings: Holdings = { S: '', H: '', D: '', C: '' }
  for (const card of cards) {
    const suit = card[0] as Suit
    if (holdings[suit] !== undefined) holdings[suit] += card.slice(1)
  }
  for (const s of SUITS) holdings[s] = sortHolding(holdings[s])
  return holdings
}

export const FIXED_CARDS_HINT =
  'Cards you know this hand holds — the one thing HCP, length and quality'
  + ' cannot say. Type ranks per suit, e.g. AK in ♥ pins ♥A and ♥K.'

/** Validate the pinned-card entries across every constrainable seat.
 *
 * Returns one message per offending seat (absent = fine). The rules mirror
 * `app/common/constraints.build_fixed_cards` + `engine.sampling.
 * resolve_fixed_cards`, checked here so the user sees the problem while typing
 * instead of as a 422 after pressing Simulate. `ownCards` is the hand the
 * current tool already knows in full — the leader's, or your own. */
export function fixedCardIssues(
  seats: Seat[],
  constraints: Record<Seat, { cards: Holdings }>,
  ownCards: string[],
): Partial<Record<Seat, string>> {
  const issues: Partial<Record<Seat, string>> = {}
  const own = new Set(ownCards)
  const owner: Record<string, Seat> = {}

  for (const seat of seats) {
    const holdings = constraints[seat]?.cards
    if (!holdings) continue
    const problems: string[] = []
    let count = 0
    for (const s of SUITS) {
      const holding = holdings[s] || ''
      count += holding.length
      const err = holdingError(holding)
      if (err) { problems.push(`${SUIT_SYMBOL[s]} ${err}`); continue }
      for (const r of holding) {
        const card = s + r
        if (own.has(card)) problems.push(`${cardLabel(card)} is already in your own hand`)
        else if (owner[card]) problems.push(`${cardLabel(card)} is also given to ${SEAT_NAME[owner[card]]}`)
        else owner[card] = seat
      }
    }
    if (count > 13) problems.push(`${count} cards pinned, but a hand holds 13`)
    if (problems.length) issues[seat] = [...new Set(problems)].join('; ')
  }
  return issues
}

// Standard IMP scale, ported from backend/engine/scoring.py (keep identical).
const IMP_THRESHOLDS = [
  20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600, 750, 900,
  1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000,
]

/** Convert a raw score difference (points) to IMPs on the standard scale. */
export function imps(diff: number): number {
  const sign = diff >= 0 ? 1 : -1
  const abs = Math.abs(diff)
  let awarded = 0
  for (let i = 0; i < IMP_THRESHOLDS.length; i++) {
    if (abs < IMP_THRESHOLDS[i]) break
    awarded = i + 1
  }
  return sign * awarded
}

export type CompareOutcome = 'win' | 'draw' | 'lose'

export interface DealComparison {
  index: number // into deals.records
  outcome: CompareOutcome // for candidate A vs candidate B on this deal
  impSwing: number // imps(scoreA - scoreB), signed for A
  tricksA: number // declarer tricks under A
  tricksB: number
}

export interface CompareSummary {
  n: number
  win: number
  draw: number
  lose: number
  avgImpSwing: number // mean IMP swing per deal, signed for A
  mpPct: number // head-to-head MP% for A = 100 * (win + draw/2) / n
}

/** Compare two candidates deal-by-deal from a per-deal matrix — opening leads
 * in the lead tool, contracts in the contract tool.
 *
 * Win/draw/lose comes from the scores, which are always in the asking tool's
 * own perspective, so the counts are the same in both scoring modes. */
export function compareCandidates(
  deals: CandidateMatrix, a: string, b: string,
): { rows: DealComparison[]; summary: CompareSummary } {
  const ia = deals.candidates.indexOf(a)
  const ib = deals.candidates.indexOf(b)
  if (ia < 0 || ib < 0) {
    return { rows: [], summary: { n: 0, win: 0, draw: 0, lose: 0, avgImpSwing: 0, mpPct: 0 } }
  }
  const rows = deals.records.map((r, index): DealComparison => {
    const scoreA = r.scores[ia]
    const scoreB = r.scores[ib]
    return {
      index,
      outcome: scoreA > scoreB ? 'win' : scoreA === scoreB ? 'draw' : 'lose',
      impSwing: imps(scoreA - scoreB),
      tricksA: r.tricks[ia],
      tricksB: r.tricks[ib],
    }
  })
  const n = rows.length
  const win = rows.filter((r) => r.outcome === 'win').length
  const draw = rows.filter((r) => r.outcome === 'draw').length
  const lose = n - win - draw
  const avgImpSwing = n ? rows.reduce((sum, r) => sum + r.impSwing, 0) / n : 0
  const mpPct = n ? (100 * (win + draw / 2)) / n : 0
  return { rows, summary: { n, win, draw, lose, avgImpSwing, mpPct } }
}

/** Compare two opening leads. The lead response calls its column list `cards`;
 * everything below is the shared implementation. */
export function compareLeads(
  deals: DealsMatrix, cardA: string, cardB: string,
): { rows: DealComparison[]; summary: CompareSummary } {
  return compareCandidates(
    { candidates: deals.cards, records: deals.records }, cardA, cardB,
  )
}

// ---------------------------------------------------------------------------
// Equivalent-lead grouping
// ---------------------------------------------------------------------------

export interface LeadGroup {
  /** Highest member ('♦T') — the key for samples / matrix / metric lookups. */
  card: string
  /** Every member, ranks high-to-low, e.g. ['♦T', '♦9']. */
  cards: string[]
  /** What the UI shows: '♦T9' (singletons stay '♦T'). */
  label: string
}

/** Group candidate leads that are equivalent on the evidence: same suit and
 * identical declarer tricks on every simulated deal. Double-dummy solving is
 * deterministic, so equal trick vectors mean no sampled deal distinguishes the
 * cards — the classic touching-card case (♦T9 from T97x). Every per-deal and
 * aggregate number is identical across a group's members by construction.
 * Cross-suit coincidences are deliberately left ungrouped: this is a display
 * grouping of interchangeable cards, not a claim about the whole deal space. */
export function groupEquivalentLeads(deals: DealsMatrix): LeadGroup[] {
  const byKey = new Map<string, string[]>()
  deals.cards.forEach((card, i) => {
    const key = card[0] + '|' + deals.records.map((r) => r.tricks[i]).join(',')
    const members = byKey.get(key)
    if (members) members.push(card)
    else byKey.set(key, [card])
  })
  return [...byKey.values()].map((members) => {
    const cards = [...members].sort(
      (a, b) => (RANK_ORDER[a.slice(1)] ?? 99) - (RANK_ORDER[b.slice(1)] ?? 99))
    return {
      card: cards[0],
      cards,
      label: cards[0][0] + cards.map((c) => c.slice(1)).join(''),
    }
  })
}

/** Map every member card to its group, for label/representative lookups. */
export function leadGroupIndex(groups: LeadGroup[]): Map<string, LeadGroup> {
  const index = new Map<string, LeadGroup>()
  for (const g of groups) for (const c of g.cards) index.set(c, g)
  return index
}

// ---------------------------------------------------------------------------
// Sampling error on a margin ("too close to call")
// ---------------------------------------------------------------------------

export interface MarginStats {
  n: number
  /** Mean per-deal difference — equals the difference of the two displayed
   * aggregate metrics by construction. */
  margin: number
  /** Standard error of that mean (sd/√n). Double-dummy solving is
   * deterministic, so deal sampling is the only noise source, and pairing per
   * deal removes the variance both candidates share. */
  sem: number
  /** True when the margin is within sampling noise (|margin| < 2·sem). */
  tooClose: boolean
}

/** Paired mean ± standard error over per-deal metric differences. */
export function pairedMarginStats(diffs: number[]): MarginStats {
  const n = diffs.length
  if (n === 0) return { n, margin: 0, sem: 0, tooClose: false }
  const margin = diffs.reduce((s, d) => s + d, 0) / n
  const variance = n > 1
    ? diffs.reduce((s, d) => s + (d - margin) ** 2, 0) / (n - 1)
    : 0
  const sem = Math.sqrt(variance / n)
  return { n, margin, sem, tooClose: n > 1 && Math.abs(margin) < 2 * sem }
}

/** Per-deal metric-contribution differences between two candidate leads, in
 * the active mode's units. Replicates the per-deal terms of the backend's
 * `scoring.aggregate` (MP: head-to-head % against the other candidates;
 * IMPs: vs the per-deal datum), so the mean of these diffs is exactly the
 * difference of the two table columns. */
export function leadMetricDiffs(
  deals: DealsMatrix, cardA: string, cardB: string, mode: Mode,
): number[] {
  const ia = deals.cards.indexOf(cardA)
  const ib = deals.cards.indexOf(cardB)
  const k = deals.cards.length
  if (ia < 0 || ib < 0 || k < 2) return []
  if (mode === 'matchpoints') {
    const mp = (r: DealRecord, i: number) => {
      let won = 0
      for (let j = 0; j < k; j++) {
        if (j === i) continue
        if (r.scores[i] > r.scores[j]) won += 1
        else if (r.scores[i] === r.scores[j]) won += 0.5
      }
      return (100 * won) / (k - 1)
    }
    return deals.records.map((r) => mp(r, ia) - mp(r, ib))
  }
  return deals.records.map((r) => {
    const datum = r.scores.reduce((s, v) => s + v, 0) / k
    return imps(r.scores[ia] - datum) - imps(r.scores[ib] - datum)
  })
}

/** Per-deal metric-contribution differences between two contract candidates,
 * both measured against the benchmark (the zero point of the displayed
 * ranking). Passing the benchmark itself as `keyB` compares A against
 * standing pat. Mirrors the per-deal terms of `rankVsBenchmark`. */
export function benchmarkMetricDiffs(
  deals: CandidateMatrix, keyA: string, keyB: string, benchmarkKey: string, mode: Mode,
): number[] {
  const ia = deals.candidates.indexOf(keyA)
  const ib = deals.candidates.indexOf(keyB)
  const ibench = deals.candidates.indexOf(benchmarkKey)
  if (ia < 0 || ib < 0 || ibench < 0) return []
  const contrib = (r: DealRecord, i: number) => {
    if (mode === 'matchpoints') {
      const a = r.scores[i]
      const b = r.scores[ibench]
      return a > b ? 100 : a === b ? 50 : 0
    }
    return imps(r.scores[i] - r.scores[ibench])
  }
  return deals.records.map((r) => contrib(r, ia) - contrib(r, ib))
}

// ---------------------------------------------------------------------------
// Deal filter (browse-only) — filter browsable deals by a hand feature
// ---------------------------------------------------------------------------

const HCP_POINTS: Record<string, number> = { A: 4, K: 3, Q: 2, J: 1 }

/** High-card points of a PBN hand string ('AK8.Q95.J982.Q43'). */
export function handHcp(pbn: string): number {
  return [...pbn].reduce((sum, ch) => sum + (HCP_POINTS[ch] ?? 0), 0)
}

/** Length of one suit in a PBN hand string. */
export function handSuitLength(pbn: string, suit: Suit): number {
  return pbn.split('.')[SUITS.indexOf(suit)]?.length ?? 0
}

/** One browse-filter criterion: a seat, an HCP window, and optionally one
 * suit-length window; `exclude` inverts the match. Filtering only narrows
 * which deals are *browsed* — rankings and aggregates always stay full-run. */
export interface DealCriterion {
  seat: string
  exclude: boolean
  hcp: [number, number]
  /** '' = no suit-length test. */
  suit: Suit | ''
  len: [number, number]
}

export function defaultCriterion(seat: string): DealCriterion {
  return { seat, exclude: false, hcp: [0, 40], suit: '', len: [0, 13] }
}

/** A criterion at its defaults filters nothing — treat it as off. */
export function criterionActive(c: DealCriterion): boolean {
  return c.hcp[0] > 0 || c.hcp[1] < 40
    || (c.suit !== '' && (c.len[0] > 0 || c.len[1] < 13))
}

/** Does this deal's layout satisfy the criterion? */
export function dealMatches(layout: Record<string, string>, c: DealCriterion): boolean {
  const hand = layout[c.seat]
  if (!hand) return true // defensive: an unknown seat filters nothing
  const hcp = handHcp(hand)
  let match = hcp >= c.hcp[0] && hcp <= c.hcp[1]
  if (match && c.suit !== '') {
    const len = handSuitLength(hand, c.suit)
    match = len >= c.len[0] && len <= c.len[1]
  }
  return c.exclude ? !match : match
}

/** Short readable form of an active criterion, for the "showing N of M" line. */
export function describeCriterion(c: DealCriterion): string {
  const parts: string[] = []
  if (c.hcp[0] > 0 || c.hcp[1] < 40) parts.push(`${c.hcp[0]}–${c.hcp[1]} HCP`)
  if (c.suit !== '' && (c.len[0] > 0 || c.len[1] < 13)) {
    parts.push(`${c.len[0]}–${c.len[1]} ${SUIT_SYMBOL[c.suit]}`)
  }
  return `${c.exclude ? 'not ' : ''}${parts.join(', ')}`
}

// ---------------------------------------------------------------------------
// Scenario recap — the constraints echoed back as readable lines
// ---------------------------------------------------------------------------

/** Human-readable one-liners for one seat of a constraints dict, e.g.
 * ['10–14 HCP', '♠ 4+', 'shape: (5-5)', 'good ♥', 'holds ♥A ♥K'].
 * Empty array = nothing constrained ("any hand"). */
export function describeSeatConstraints(c: Constraints, seat: string): string[] {
  const lines: string[] = []
  const hcp = c.hcp?.[seat]
  if (hcp) lines.push(`${hcp[0]}–${hcp[1]} HCP`)
  for (const s of SUITS) {
    const range = c.suit_length?.[seat]?.[s]
    if (!range) continue
    const [lo, hi] = range
    const text = hi >= 13 ? `${lo}+` : lo <= 0 ? `≤${hi}` : lo === hi ? `${lo}` : `${lo}–${hi}`
    lines.push(`${SUIT_SYMBOL[s]} ${text}`)
  }
  if (c.shapes?.[seat]) lines.push(`shape: ${c.shapes[seat]}`)
  for (const [s, level] of Object.entries(c.quality?.[seat] ?? {})) {
    lines.push(`${level} ${SUIT_SYMBOL[s as Suit]}`)
  }
  const cards = c.fixed_cards?.[seat]
  if (cards?.length) lines.push(`holds ${cards.map(cardLabel).join(' ')}`)
  return lines
}

// ---------------------------------------------------------------------------
// Contract calculator
// ---------------------------------------------------------------------------

/** The level at which each strain earns the game bonus (mirrors
 * backend/engine/contract/candidates.py). */
export const GAME_LEVEL: Record<string, number> = { N: 3, S: 4, H: 4, D: 5, C: 5 }

export interface BenchmarkMetric {
  key: string
  /** Mean IMPs vs the benchmark contract, per deal. */
  imps: number
  /** Head-to-head matchpoints vs the benchmark: (win + ½·draw) / n, as a %. */
  mpPct: number
  win: number
  draw: number
  lose: number
  /** Share of the positive IMP total contributed by the best 15% of deals —
   * high means the edge rests on a handful of lucky layouts. */
  edgeConcentration: number
}

/** Score every candidate against one benchmark contract.
 *
 * Both bridge scoring modes are pairwise-vs-the-contract-you'd-otherwise-be-in:
 * at IMPs you care how big the swing is, at matchpoints only how often you win.
 * Ranking against a fixed benchmark (rather than against the whole candidate
 * list) is also what keeps a 30%-to-make grand slam from looking good just
 * because it wins outright on the deals where it happens to come home. */
export function rankVsBenchmark(
  deals: CandidateMatrix, benchmarkKey: string,
): Record<string, BenchmarkMetric> {
  const ib = deals.candidates.indexOf(benchmarkKey)
  const out: Record<string, BenchmarkMetric> = {}
  if (ib < 0) return out
  const n = deals.records.length

  deals.candidates.forEach((key, i) => {
    let total = 0
    let win = 0
    let draw = 0
    const gains: number[] = []
    for (const r of deals.records) {
      const swing = imps(r.scores[i] - r.scores[ib])
      total += swing
      if (r.scores[i] > r.scores[ib]) win += 1
      else if (r.scores[i] === r.scores[ib]) draw += 1
      if (swing > 0) gains.push(swing)
    }
    // How top-heavy the upside is: share of all IMPs gained that comes from the
    // best 15% of deals (1.0 = every gain sits in that tail).
    gains.sort((a, b) => b - a)
    const gained = gains.reduce((sum, g) => sum + g, 0)
    const tailCount = Math.max(1, Math.round(n * 0.15))
    const tail = gains.slice(0, tailCount).reduce((sum, g) => sum + g, 0)
    out[key] = {
      key,
      imps: n ? total / n : 0,
      mpPct: n ? (100 * (win + draw / 2)) / n : 0,
      win,
      draw,
      lose: n - win - draw,
      edgeConcentration: gained > 0 ? tail / gained : 0,
    }
  })
  return out
}
