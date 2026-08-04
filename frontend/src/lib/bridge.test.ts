import { describe, expect, it } from 'vitest'
import type { CandidateMatrix, Seat } from '../api/types'
import type { DealsMatrix } from '../api/leadTypes'
import {
  cardLabel, compareCandidates, compareLeads, fixedCardIssues, holdingError,
  holdingsToCards, holdingsToPbn, imps, leaderSeat, parseContract, parsePbn,
  randomHand, rankVsBenchmark, sortHolding, type Holdings,
} from './bridge'

describe('parseContract', () => {
  it('parses NT and suit contracts', () => {
    expect(parseContract('3NT')).toEqual({ level: 3, strain: 'N' })
    expect(parseContract('4h')).toEqual({ level: 4, strain: 'H' })
    expect(parseContract(' 7 C ')).toEqual({ level: 7, strain: 'C' })
  })
  it('rejects invalid contracts', () => {
    expect(parseContract('')).toBeNull()
    expect(parseContract('8NT')).toBeNull()
    expect(parseContract('3X')).toBeNull()
    expect(parseContract('H')).toBeNull()
  })
})

describe('leaderSeat', () => {
  it('is LHO of declarer', () => {
    expect(leaderSeat('S')).toBe('W')
    expect(leaderSeat('N')).toBe('E')
    expect(leaderSeat('W')).toBe('N')
  })
})

describe('holdingError', () => {
  it('flags bad ranks and duplicates', () => {
    expect(holdingError('AKQ')).toBeNull()
    expect(holdingError('AK1')).toContain('invalid')
    expect(holdingError('AA')).toContain('duplicate')
  })
})

describe('parsePbn', () => {
  it('splits a valid PBN hand', () => {
    expect(parsePbn('T.KT932.Q2.T9843').holdings).toEqual({
      S: 'T', H: 'KT932', D: 'Q2', C: 'T9843',
    })
  })
  it('converts 10 to T and reports errors', () => {
    expect(parsePbn('10.KT932.Q2.T9843').holdings?.S).toBe('T')
    expect(parsePbn('A.B.C').error).toBeTruthy()  // wrong group count
    expect(parsePbn('AX.K.Q.J').error).toContain('invalid')
  })
})

describe('sortHolding', () => {
  it('sorts high-to-low', () => {
    expect(sortHolding('2AKQ')).toBe('AKQ2')
  })
})

describe('randomHand', () => {
  it('always deals exactly 13 valid cards', () => {
    for (let i = 0; i < 50; i++) {
      const h = randomHand()
      const total = holdingsToPbn(h).replace(/\./g, '').length
      expect(total).toBe(13)
      for (const s of ['S', 'H', 'D', 'C'] as const) {
        expect(holdingError(h[s])).toBeNull()
      }
    }
  })
})

describe('imps', () => {
  it('matches the standard IMP scale at the boundaries', () => {
    expect(imps(0)).toBe(0)
    expect(imps(19)).toBe(0)
    expect(imps(20)).toBe(1)
    expect(imps(49)).toBe(1)
    expect(imps(50)).toBe(2)
    expect(imps(-50)).toBe(-2)
    expect(imps(4000)).toBe(24)
    expect(imps(10000)).toBe(24)
  })
})

describe('compareLeads', () => {
  const matrix: DealsMatrix = {
    cards: ['♥Q', '♠4'],
    records: [
      // ♥Q sets the contract, ♠4 lets it make: win, big swing
      { layout: {}, tricks: [8, 9], scores: [50, -400] },
      // identical results: draw
      { layout: {}, tricks: [9, 9], scores: [-400, -400] },
      // ♥Q concedes an overtrick: lose, small swing
      { layout: {}, tricks: [10, 9], scores: [-430, -400] },
      // both set it, ♥Q by more: win
      { layout: {}, tricks: [7, 8], scores: [100, 50] },
    ],
  }

  it('classifies each deal and totals win/draw/lose', () => {
    const { rows, summary } = compareLeads(matrix, '♥Q', '♠4')
    expect(rows.map((r) => r.outcome)).toEqual(['win', 'draw', 'lose', 'win'])
    expect(rows[0]).toMatchObject({ index: 0, tricksA: 8, tricksB: 9 })
    expect(summary).toMatchObject({ n: 4, win: 2, draw: 1, lose: 1 })
    // head-to-head MP% = 100 * (2 + 0.5) / 4
    expect(summary.mpPct).toBeCloseTo(62.5)
    // swings: imps(450)=10, imps(0)=0, imps(-30)=-1, imps(50)=2 -> avg 11/4
    expect(rows.map((r) => r.impSwing)).toEqual([10, 0, -1, 2])
    expect(summary.avgImpSwing).toBeCloseTo(11 / 4)
  })

  it('is antisymmetric when the leads are swapped', () => {
    const fwd = compareLeads(matrix, '♥Q', '♠4').summary
    const rev = compareLeads(matrix, '♠4', '♥Q').summary
    expect(rev.win).toBe(fwd.lose)
    expect(rev.lose).toBe(fwd.win)
    expect(rev.draw).toBe(fwd.draw)
    expect(rev.avgImpSwing).toBeCloseTo(-fwd.avgImpSwing)
  })

  it('returns an empty result for an unknown card', () => {
    const { rows, summary } = compareLeads(matrix, '♥Q', '♦2')
    expect(rows).toEqual([])
    expect(summary.n).toBe(0)
  })

  it('is the same comparison as compareCandidates over the same columns', () => {
    const generic = compareCandidates(
      { candidates: matrix.cards, records: matrix.records }, '♥Q', '♠4',
    )
    expect(generic).toEqual(compareLeads(matrix, '♥Q', '♠4'))
  })
})

describe('rankVsBenchmark', () => {
  // Three contracts over four deals, scored from our (declaring) side.
  const matrix: CandidateMatrix = {
    candidates: ['4S-S', '3N-S', '6S-S'],
    records: [
      // everything makes; the slam is worth a lot more
      { layout: {}, tricks: [12, 12, 12], scores: [480, 490, 980] },
      { layout: {}, tricks: [12, 12, 12], scores: [480, 490, 980] },
      // twelve tricks are not there: the slam goes down, the games are fine
      { layout: {}, tricks: [10, 9, 10], scores: [420, 400, -100] },
      { layout: {}, tricks: [10, 9, 10], scores: [420, 400, -100] },
    ],
  }

  it('scores every candidate against the benchmark, which reads zero', () => {
    const m = rankVsBenchmark(matrix, '4S-S')
    expect(m['4S-S']).toMatchObject({ imps: 0, mpPct: 50, win: 0, lose: 0, draw: 4 })
    // 3NT: +10 twice (imps(10)=0), -20 twice (imps(-20)=-1) -> wins 2, loses 2
    expect(m['3N-S']).toMatchObject({ win: 2, lose: 2, draw: 0, mpPct: 50 })
    expect(m['3N-S'].imps).toBeCloseTo((0 + 0 - 1 - 1) / 4)
    // 6S: imps(500)=11 twice, imps(-520)=-11 twice -> nets out to zero IMPs
    expect(m['6S-S'].imps).toBeCloseTo(0)
    expect(m['6S-S'].mpPct).toBeCloseTo(50)
  })

  it('reports how concentrated a positive edge is', () => {
    const m = rankVsBenchmark(matrix, '3N-S')
    // 4S beats 3NT on the two deals where the slam fails, by the same amount
    expect(m['4S-S'].win).toBe(2)
    expect(m['4S-S'].edgeConcentration).toBeLessThan(1)
    // the benchmark itself has no gains at all
    expect(m['3N-S'].edgeConcentration).toBe(0)
  })

  it('returns nothing for an unknown benchmark', () => {
    expect(rankVsBenchmark(matrix, '7C-N')).toEqual({})
  })
})

describe('pinned cards', () => {
  const cards = (h: Partial<Holdings>): Holdings => ({ S: '', H: '', D: '', C: '', ...h })
  const seats: Seat[] = ['N', 'E', 'W']
  const state = (bySeat: Partial<Record<Seat, Partial<Holdings>>>) =>
    Object.fromEntries(
      (['N', 'E', 'S', 'W'] as Seat[]).map((s) => [s, { cards: cards(bySeat[s] ?? {}) }]),
    ) as Record<Seat, { cards: Holdings }>

  it('flattens per-suit holdings into endplay cards', () => {
    expect(holdingsToCards(cards({ H: 'AK', C: 'T' }))).toEqual(['HA', 'HK', 'CT'])
    expect(holdingsToCards(cards({}))).toEqual([])
  })

  it('labels a card with its suit symbol', () => {
    expect(cardLabel('HA')).toBe('♥A')
    expect(cardLabel('DT')).toBe('♦T')
  })

  it('accepts a clean set of pinned cards', () => {
    expect(fixedCardIssues(seats, state({ N: { H: 'AK' }, E: { S: 'Q' } }), ['CA'])).toEqual({})
  })

  it('flags a card that is already in our own hand', () => {
    const issues = fixedCardIssues(seats, state({ N: { H: 'AK' } }), ['HK'])
    expect(issues.N).toContain('♥K is already in your own hand')
    expect(issues.E).toBeUndefined()
  })

  it('flags the same card given to two seats', () => {
    const issues = fixedCardIssues(seats, state({ N: { D: 'A' }, E: { D: 'A' } }), [])
    // The first seat to claim it keeps it; the clash is reported on the second.
    expect(issues.N).toBeUndefined()
    expect(issues.E).toContain('♦A is also given to North')
  })

  it('flags invalid and duplicate ranks', () => {
    const issues = fixedCardIssues(seats, state({ N: { H: 'AX' }, E: { S: 'QQ' } }), [])
    expect(issues.N).toContain('♥ invalid: X')
    expect(issues.E).toContain('♠ duplicate: Q')
  })

  it('flags more than thirteen pinned cards', () => {
    const issues = fixedCardIssues(
      seats, state({ N: { S: 'AKQJT98765432', H: 'A' } }), [])
    expect(issues.N).toContain('14 cards pinned')
  })

  it('ignores seats the current tool cannot constrain', () => {
    // S is our own seat here, so its entry is never inspected.
    expect(fixedCardIssues(seats, state({ S: { H: 'AX' } }), [])).toEqual({})
  })
})
