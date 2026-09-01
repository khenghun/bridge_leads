/**
 * Pure helpers behind "Analyze N/S / E/W / the whole table" (play v1.1).
 *
 * A pair is always graded as a pair. The declaring side is ONE grade — of
 * declarer, whose decisions already include the cards played from dummy
 * (dummy makes no decisions). The defending side is one grade PER defender,
 * because each defender saw a different hand hidden. The API is untouched:
 * `/api/play/analyze` still grades one seat per request; this module decides
 * which requests to make, what each may carry, and how to read the set of
 * results back as pairs.
 */
import type { Constraints, Seat, Suit } from '../../api/types'
import type { AnalyzeResponse, AnalyzeSummary, Decision, PlayRole } from '../../api/playTypes'
import type { SeatConstraint } from '../../components/ConstraintsEditor'
import {
  RANKS, SEATS, SUITS, SUIT_SYMBOL, dummySeat, handHcp, handSuitLength,
  holdingsToCards, leaderSeat, partnerSeat,
} from '../../lib/bridge'

export type Pair = 'NS' | 'EW'
export type AnalysisAction = Pair | 'table'

export const PAIR_SEATS: Record<Pair, Seat[]> = { NS: ['N', 'S'], EW: ['E', 'W'] }
export const PAIR_LABEL: Record<Pair, string> = { NS: 'N/S', EW: 'E/W' }

export function pairOf(seat: Seat): Pair {
  return seat === 'N' || seat === 'S' ? 'NS' : 'EW'
}

export function otherPair(pair: Pair): Pair {
  return pair === 'NS' ? 'EW' : 'NS'
}

export function pairRole(pair: Pair, declarer: Seat): PlayRole {
  return pairOf(declarer) === pair ? 'declarer' : 'defender'
}

/** The pairs an action covers, in the order they are graded: the declaring
 * side first for the whole table, because it is one request and lands first. */
export function pairsFor(action: AnalysisAction, declarer: Seat): Pair[] {
  if (action !== 'table') return [action]
  const declaring = pairOf(declarer)
  return [declaring, otherPair(declaring)]
}

/** The seats one pair is graded through. Declaring: declarer alone (dummy's
 * cards are declarer's decisions). Defending: the opening leader, then the
 * other defender. */
export function seatsOfPair(pair: Pair, declarer: Seat): Seat[] {
  if (pairRole(pair, declarer) === 'declarer') return [declarer]
  const leader = leaderSeat(declarer)
  return [leader, partnerSeat(leader)]
}

/** Every seat an action grades, in request order. */
export function seatsToGrade(action: AnalysisAction, declarer: Seat): Seat[] {
  return pairsFor(action, declarer).flatMap((p) => seatsOfPair(p, declarer))
}

/** The hands a graded seat can see in the steady state — and therefore may
 * not constrain (the API rejects that with a 422). Declarer: declarer and
 * dummy. A defender: itself and dummy. */
export function visibleTo(seat: Seat, declarer: Seat): Seat[] {
  const dummy = dummySeat(declarer)
  return seat === declarer ? [declarer, dummy] : [seat, dummy]
}

/** The seats whose hands are hidden from a graded seat — the ones a request
 * for that seat may constrain. */
export function hiddenFrom(seat: Seat, declarer: Seat): Seat[] {
  const visible = visibleTo(seat, declarer)
  return SEATS.filter((s) => !visible.includes(s))
}

/** The seats the editor offers: everyone but dummy, which every graded view
 * can see and so no request could ever carry a constraint on. */
export function constrainableSeats(declarer: Seat): Seat[] {
  const dummy = dummySeat(declarer)
  return SEATS.filter((s) => s !== dummy)
}

/** Editor state → the API constraints dict for ONE request: only the entries
 * for `hidden` seats. Constraints are "what the auction revealed about each
 * hand" — public information, entered once per seat — and each request takes
 * the slice its graded seat could not see for itself. */
export function constraintsForView(
  state: Record<Seat, SeatConstraint>, hidden: Seat[],
): Constraints {
  const out: Constraints = { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} }
  for (const seat of hidden) {
    const c = state[seat]
    if (!c) continue
    if (c.hcp[0] !== 0 || c.hcp[1] !== 40) out.hcp[seat] = c.hcp
    const lengths: Record<string, [number, number]> = {}
    for (const s of SUITS) {
      const [lo, hi] = c.suits[s]
      if (lo !== 0 || hi !== 13) lengths[s] = [lo, hi]
    }
    if (Object.keys(lengths).length) out.suit_length[seat] = lengths
    if (c.shape.trim()) out.shapes[seat] = c.shape
    const quality = Object.entries(c.quality).filter(([, level]) => level)
    if (quality.length) out.quality[seat] = Object.fromEntries(quality)
    const cards = holdingsToCards(c.cards)
    if (cards.length) out.fixed_cards[seat] = cards
  }
  return out
}

/** Suit quality as the engine defines it: good = 2 of AKQ or 3 of AKQJT. */
export function holdingIsGood(holding: string): boolean {
  const top3 = [...holding].filter((r) => 'AKQ'.includes(r)).length
  const top5 = [...holding].filter((r) => 'AKQJT'.includes(r)).length
  return top3 >= 2 || top5 >= 3
}

/** Why a seat's constraints rule out the hand that seat ACTUALLY held.
 *
 * The play solver knows the whole deal, so a constraint the real hand fails
 * makes every sampled layout wrong by construction — the truth is excluded
 * from the sample. Returns one reason per failing constraint (empty = fine).
 * Pinned cards are reported separately by `pinnedCardsNotHeld`, because they
 * block the request; these only warn. Shape text is not evaluated here. */
export function constraintsExcludeHand(c: SeatConstraint, pbn: string): string[] {
  const reasons: string[] = []
  const hcp = handHcp(pbn)
  if (hcp < c.hcp[0] || hcp > c.hcp[1]) {
    reasons.push(`held ${hcp} HCP, outside ${c.hcp[0]}–${c.hcp[1]}`)
  }
  for (const s of SUITS) {
    const [lo, hi] = c.suits[s]
    const n = handSuitLength(pbn, s)
    if (n < lo || n > hi) reasons.push(`held ${n} ${SUIT_SYMBOL[s]}, outside ${lo}–${hi}`)
  }
  for (const [suit, level] of Object.entries(c.quality)) {
    if (!level) continue
    const holding = pbn.split('.')[SUITS.indexOf(suit as Suit)] ?? ''
    const good = holdingIsGood(holding)
    if ((level === 'good') !== good) {
      reasons.push(`${SUIT_SYMBOL[suit as Suit]} ${holding || '—'} is not a ${level} suit`)
    }
  }
  return reasons
}

/** Pinned cards this seat did not actually hold — always an error in the
 * play solver, never a matter of opinion. */
export function pinnedCardsNotHeld(c: SeatConstraint, pbn: string): string[] {
  const held = new Set<string>()
  pbn.split('.').forEach((holding, i) => {
    for (const r of holding) held.add(SUITS[i] + r)
  })
  return holdingsToCards(c.cards)
    .filter((card) => RANKS.includes(card[1]) && !held.has(card))
    .map((card) => `${SUIT_SYMBOL[card[0] as Suit]}${card[1]}`)
}

/** Every graded decision across all results indexed by the card played —
 * cards are unique in a deal, so seats never collide. */
export function mergeDecisions(results: Partial<Record<Seat, AnalyzeResponse>>): Decision[] {
  return SEATS.flatMap((s) => results[s]?.decisions ?? [])
}

export interface Swing {
  seat: Seat
  role: PlayRole
  decision: Decision
  /** Tricks given up: −diff, so ≥ 0. */
  loss: number
}

/** Every decision that cost tricks, across every graded seat, worst first —
 * the whole-table "whose fault was it" list. Ties break by trick, then seat
 * order, so the list is stable between renders. */
export function rankSwings(results: Partial<Record<Seat, AnalyzeResponse>>): Swing[] {
  const swings: Swing[] = []
  for (const seat of SEATS) {
    const r = results[seat]
    if (!r) continue
    for (const d of r.decisions) {
      if (d.forced || d.diff == null) continue
      const loss = -d.diff
      if (loss < 0.005) continue
      swings.push({ seat, role: r.role, decision: d, loss })
    }
  }
  return swings.sort((a, b) =>
    b.loss - a.loss
    || a.decision.trick - b.decision.trick
    || SEATS.indexOf(a.seat) - SEATS.indexOf(b.seat))
}

export interface PairSummary extends AnalyzeSummary {
  /** Seats whose results are in — the summary covers only these. */
  seats: Seat[]
}

/** Roll the per-seat summaries of a pair into one. Null until at least one
 * of the pair's seats has a result. */
export function pairSummary(
  results: Partial<Record<Seat, AnalyzeResponse>>, seats: Seat[],
): PairSummary | null {
  const have = seats.filter((s) => results[s])
  if (!have.length) return null
  const sum: PairSummary = {
    seats: have, decisions: 0, graded: 0, optimal: 0, good: 0, suboptimal: 0,
    total_trick_loss: 0, avg_trick_loss: 0,
  }
  for (const s of have) {
    const x = results[s]!.summary
    sum.decisions += x.decisions
    sum.graded += x.graded
    sum.optimal += x.optimal
    sum.good += x.good
    sum.suboptimal += x.suboptimal
    sum.total_trick_loss += x.total_trick_loss
  }
  sum.avg_trick_loss = sum.graded ? sum.total_trick_loss / sum.graded : 0
  return sum
}
