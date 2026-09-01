import { describe, expect, it } from 'vitest'
import type { Seat } from '../../api/types'
import type { AnalyzeResponse, Decision } from '../../api/playTypes'
import { defaultSeatConstraint, type SeatConstraint } from '../../components/ConstraintsEditor'
import {
  constrainableSeats, constraintsExcludeHand, constraintsForView, hiddenFrom,
  holdingIsGood, mergeDecisions, pairSummary, pairsFor, pinnedCardsNotHeld,
  rankSwings, seatsOfPair, seatsToGrade, visibleTo,
} from './analysis'

const SEATS: Seat[] = ['N', 'E', 'S', 'W']

// ── which seats get graded ──────────────────────────────────────────────────

describe('seatsToGrade', () => {
  it('grades the declaring pair through declarer alone, for every declarer', () => {
    expect(seatsToGrade('EW', 'W')).toEqual(['W'])
    expect(seatsToGrade('EW', 'E')).toEqual(['E'])
    expect(seatsToGrade('NS', 'N')).toEqual(['N'])
    expect(seatsToGrade('NS', 'S')).toEqual(['S'])
  })

  it('grades the defending pair as two seats, opening leader first', () => {
    expect(seatsToGrade('NS', 'W')).toEqual(['N', 'S'])   // N leads against W
    expect(seatsToGrade('NS', 'E')).toEqual(['S', 'N'])   // S leads against E
    expect(seatsToGrade('EW', 'N')).toEqual(['E', 'W'])
    expect(seatsToGrade('EW', 'S')).toEqual(['W', 'E'])
  })

  it('grades the whole table as declarer then both defenders — three requests', () => {
    expect(seatsToGrade('table', 'W')).toEqual(['W', 'N', 'S'])
    expect(seatsToGrade('table', 'S')).toEqual(['S', 'W', 'E'])
    for (const d of SEATS) {
      const seats = seatsToGrade('table', d)
      expect(seats).toHaveLength(3)
      expect(new Set(seats).size).toBe(3)
      expect(seats).not.toContain(SEATS[(SEATS.indexOf(d) + 2) % 4]) // never dummy
    }
  })

  it('orders the whole table declaring pair first', () => {
    expect(pairsFor('table', 'W')).toEqual(['EW', 'NS'])
    expect(pairsFor('table', 'N')).toEqual(['NS', 'EW'])
    expect(pairsFor('NS', 'W')).toEqual(['NS'])
    expect(seatsOfPair('NS', 'W')).toEqual(['N', 'S'])
  })
})

// ── visibility and constraints ──────────────────────────────────────────────

describe('visibility', () => {
  it('declarer sees dummy; a defender sees itself and dummy', () => {
    expect(visibleTo('W', 'W')).toEqual(['W', 'E'])
    expect(hiddenFrom('W', 'W')).toEqual(['N', 'S'])
    expect(visibleTo('N', 'W')).toEqual(['N', 'E'])
    expect(hiddenFrom('N', 'W')).toEqual(['S', 'W'])
  })

  it('the editor offers everyone but dummy', () => {
    expect(constrainableSeats('W')).toEqual(['N', 'S', 'W'])
    expect(constrainableSeats('N')).toEqual(['N', 'E', 'W'])
  })
})

function state(overrides: Partial<Record<Seat, Partial<SeatConstraint>>>): Record<Seat, SeatConstraint> {
  const out = {} as Record<Seat, SeatConstraint>
  for (const s of SEATS) out[s] = { ...defaultSeatConstraint(), ...(overrides[s] ?? {}) }
  return out
}

describe('constraintsForView', () => {
  const st = state({
    N: { hcp: [12, 40] },
    E: { hcp: [0, 7], cards: { S: 'A', H: '', D: '', C: '' } },
    S: { suits: { S: [0, 13], H: [5, 13], D: [0, 13], C: [0, 13] }, shape: '(54xx)' },
    W: { quality: { H: 'good' } },
  })

  it('carries only the hidden seats, and only the non-default fields', () => {
    const c = constraintsForView(st, ['N', 'S'])
    expect(c.hcp).toEqual({ N: [12, 40] })
    expect(c.suit_length).toEqual({ S: { H: [5, 13] } })
    expect(c.shapes).toEqual({ S: '(54xx)' })
    expect(c.quality).toEqual({})
    expect(c.fixed_cards).toEqual({})
  })

  it('the same state sliced for a different view carries the other seats', () => {
    const c = constraintsForView(st, ['E', 'W'])
    expect(c.hcp).toEqual({ E: [0, 7] })
    expect(c.fixed_cards).toEqual({ E: ['SA'] })
    expect(c.quality).toEqual({ W: { H: 'good' } })
    expect(c.suit_length).toEqual({})
  })

  it('is empty for an untouched editor', () => {
    const c = constraintsForView(state({}), ['N', 'S'])
    expect(c).toEqual({ hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} })
  })
})

// ── the real deal is known ──────────────────────────────────────────────────

// West's hand from Board 17 (the built-in example): 10 HCP, 3-3-4-3.
const WEST = 'A54.Q94.T963.AT2'

describe('constraintsExcludeHand', () => {
  it('is quiet when the real hand fits', () => {
    expect(constraintsExcludeHand(defaultSeatConstraint(), WEST)).toEqual([])
    const c = { ...defaultSeatConstraint(), hcp: [8, 12] as [number, number] }
    expect(constraintsExcludeHand(c, WEST)).toEqual([])
  })

  it('names an HCP band the real hand is outside', () => {
    const c = { ...defaultSeatConstraint(), hcp: [12, 40] as [number, number] }
    expect(constraintsExcludeHand(c, WEST)).toEqual(['held 10 HCP, outside 12–40'])
  })

  it('names a suit length the real hand is outside', () => {
    const c = defaultSeatConstraint()
    c.suits.H = [4, 13]
    expect(constraintsExcludeHand(c, WEST)).toEqual(['held 3 ♥, outside 4–13'])
  })

  it('checks suit quality the way the engine defines it', () => {
    expect(holdingIsGood('AK2')).toBe(true)
    expect(holdingIsGood('KQ')).toBe(true)
    expect(holdingIsGood('QJT4')).toBe(true)
    expect(holdingIsGood('A54')).toBe(false)
    expect(holdingIsGood('KJ9')).toBe(false)
    const good = { ...defaultSeatConstraint(), quality: { S: 'good' as const } }
    expect(constraintsExcludeHand(good, WEST)).toEqual(['♠ A54 is not a good suit'])
    const poor = { ...defaultSeatConstraint(), quality: { S: 'poor' as const } }
    expect(constraintsExcludeHand(poor, WEST)).toEqual([])
  })

  it('reports every failing constraint, not just the first', () => {
    const c = { ...defaultSeatConstraint(), hcp: [15, 17] as [number, number] }
    c.suits.D = [0, 3]
    expect(constraintsExcludeHand(c, WEST)).toHaveLength(2)
  })
})

describe('pinnedCardsNotHeld', () => {
  it('lists pinned cards the seat did not hold, in symbol form', () => {
    const c = { ...defaultSeatConstraint(), cards: { S: 'A', H: 'AK', D: '', C: '' } }
    expect(pinnedCardsNotHeld(c, WEST)).toEqual(['♥A', '♥K'])
  })
  it('is empty when every pinned card is really there', () => {
    const c = { ...defaultSeatConstraint(), cards: { S: 'A5', H: 'Q', D: 'T', C: 'A' } }
    expect(pinnedCardsNotHeld(c, WEST)).toEqual([])
  })
})

// ── reading the results back as pairs ───────────────────────────────────────

let nextIndex = 0
function decision(over: Partial<Decision>): Decision {
  const index = over.index ?? nextIndex++
  return {
    index, trick: Math.floor(index / 4) + 1, position: index % 4, hand: 'W', card: `C${index + 2}`,
    forced: false, actual_tricks: 7, best_tricks: 7, diff: 0, status: 'optimal',
    actual_score: 90, best_score: 90, score_diff: 0, imp_diff: 0,
    options: [], best_cards: [], ...over,
  }
}

function response(seat: Seat, role: 'declarer' | 'defender', decisions: Decision[]): AnalyzeResponse {
  const graded = decisions.filter((d) => !d.forced)
  const loss = graded.reduce((s, d) => s - (d.diff ?? 0), 0)
  const impLoss = graded.reduce((s, d) => s - (d.imp_diff ?? 0), 0)
  return {
    seat, role, visible: [seat], tricks_needed: 7, decisions, method: 'single_dummy', num_deals: 20,
    summary: {
      decisions: decisions.length, graded: graded.length,
      optimal: graded.filter((d) => d.status === 'optimal').length,
      good: graded.filter((d) => d.status === 'good').length,
      suboptimal: graded.filter((d) => d.status === 'suboptimal').length,
      total_trick_loss: loss, avg_trick_loss: graded.length ? loss / graded.length : 0,
      total_score_loss: 0, total_imp_loss: impLoss,
    },
  }
}

describe('rankSwings', () => {
  const west = response('W', 'declarer', [
    decision({ index: 1, card: 'SJ', diff: -0.4, status: 'suboptimal' }),
    decision({ index: 5, card: 'S4', diff: 0, status: 'optimal' }),
    decision({ index: 9, card: 'C4', diff: -0.1, status: 'good' }),
    decision({ index: 13, card: 'D5', forced: true, diff: null, actual_tricks: null, best_tricks: null, status: 'forced' }),
  ])
  const north = response('N', 'defender', [
    decision({ index: 2, card: 'SK', hand: 'N', diff: -1.2, status: 'suboptimal' }),
    decision({ index: 6, card: 'S2', hand: 'N', diff: -0.4, status: 'suboptimal' }),
  ])

  it('lists every decision that cost tricks, worst first, across seats', () => {
    const swings = rankSwings({ W: west, N: north })
    expect(swings.map((s) => [s.seat, s.decision.card, s.loss])).toEqual([
      ['N', 'SK', 1.2],
      ['W', 'SJ', 0.4],   // tie with N S2 at 0.4 → earlier trick first
      ['N', 'S2', 0.4],
      ['W', 'C4', 0.1],
    ])
    expect(swings[0].role).toBe('defender')
  })

  it('skips optimal and forced decisions', () => {
    const cards = rankSwings({ W: west }).map((s) => s.decision.card)
    expect(cards).not.toContain('S4')
    expect(cards).not.toContain('D5')
  })

  it('is empty with no results', () => {
    expect(rankSwings({})).toEqual([])
  })

  it('ranks by IMPs given up before tricks — a game let through beats an overtrick', () => {
    const w = response('W', 'declarer', [
      decision({ index: 1, card: 'SJ', diff: -1.0, imp_diff: -0.2, status: 'suboptimal' }),   // an overtrick
      decision({ index: 5, card: 'S4', diff: -0.6, imp_diff: -6.5, status: 'suboptimal' }),   // the game
    ])
    const swings = rankSwings({ W: w })
    expect(swings.map((s) => [s.decision.card, s.imps])).toEqual([['S4', 6.5], ['SJ', 0.2]])
  })
})

describe('pairSummary', () => {
  const n = response('N', 'defender', [
    decision({ diff: -0.5, status: 'suboptimal' }), decision({ diff: 0 }),
    decision({ forced: true, diff: null, status: 'forced' }),
  ])
  const s = response('S', 'defender', [decision({ diff: -0.2, status: 'good' }), decision({ diff: 0 })])

  it('is null until one of the pair has a result', () => {
    expect(pairSummary({}, ['N', 'S'])).toBeNull()
  })

  it('rolls both seats up, and says which seats it covers', () => {
    const sum = pairSummary({ N: n, S: s }, ['N', 'S'])!
    expect(sum.seats).toEqual(['N', 'S'])
    expect(sum.decisions).toBe(5)
    expect(sum.graded).toBe(4)
    expect(sum.optimal).toBe(2)
    expect(sum.good).toBe(1)
    expect(sum.suboptimal).toBe(1)
    expect(sum.total_trick_loss).toBeCloseTo(0.7)
    expect(sum.avg_trick_loss).toBeCloseTo(0.175)
    expect(sum.total_imp_loss).toBe(0)
  })

  it('covers a partial pair while the second seat is still solving', () => {
    const sum = pairSummary({ N: n }, ['N', 'S'])!
    expect(sum.seats).toEqual(['N'])
    expect(sum.graded).toBe(2)
  })
})

describe('mergeDecisions', () => {
  it('concatenates every seat’s decisions for the table tooltips', () => {
    const w = response('W', 'declarer', [decision({ card: 'SJ' })])
    const n = response('N', 'defender', [decision({ card: 'SK', hand: 'N' })])
    expect(mergeDecisions({ W: w, N: n }).map((d) => d.card)).toEqual(['SK', 'SJ'])
  })
})
