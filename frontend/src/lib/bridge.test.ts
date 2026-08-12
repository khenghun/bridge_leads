import { describe, expect, it } from 'vitest'
import type { CandidateMatrix, Seat } from '../api/types'
import type { DealsMatrix } from '../api/leadTypes'
import {
  benchmarkMetricDiffs, cardLabel, compareCandidates, compareLeads,
  criterionActive, dealMatches, defaultCriterion, describeCriterion,
  describeSeatConstraints, fixedCardIssues, groupEquivalentLeads, handHcp,
  handSuitLength, holdingError, holdingsToCards, holdingsToPbn, imps,
  leadGroupIndex, leadMetricDiffs, leaderSeat, pairedMarginStats,
  parseContract, parsePbn, randomHand, rankVsBenchmark, sortHolding,
  type Holdings,
} from './bridge'
import type { Constraints } from '../api/types'

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

describe('groupEquivalentLeads', () => {
  // ♦T and ♦9 identical on every deal (touching); ♦2 differs on deal 3; the ♠5
  // vector matches ♦T exactly but is another suit; ♥K is a singleton column.
  const matrix: DealsMatrix = {
    cards: ['♦9', '♦T', '♦2', '♠5', '♥K'],
    records: [
      { layout: {}, tricks: [9, 9, 9, 9, 8], scores: [0, 0, 0, 0, 0] },
      { layout: {}, tricks: [8, 8, 8, 8, 8], scores: [0, 0, 0, 0, 0] },
      { layout: {}, tricks: [9, 9, 10, 9, 9], scores: [0, 0, 0, 0, 0] },
    ],
  }
  const groups = groupEquivalentLeads(matrix)
  const byLabel = Object.fromEntries(groups.map((g) => [g.label, g]))

  it('groups same-suit cards with identical trick vectors, highest first', () => {
    expect(byLabel['♦T9']).toMatchObject({ card: '♦T', cards: ['♦T', '♦9'] })
  })
  it('does not group a near-miss vector or a cross-suit coincidence', () => {
    expect(groups).toHaveLength(4)
    expect(byLabel['♦2']).toBeTruthy()
    expect(byLabel['♠5']).toBeTruthy()
    expect(byLabel['♥K']).toBeTruthy()
  })
  it('covers every card exactly once', () => {
    const all = groups.flatMap((g) => g.cards).sort()
    expect(all).toEqual([...matrix.cards].sort())
  })
  it('indexes every member card to its group', () => {
    const index = leadGroupIndex(groups)
    expect(index.get('♦9')?.card).toBe('♦T')
    expect(index.get('♦T')?.label).toBe('♦T9')
    expect(index.get('♥K')?.label).toBe('♥K')
  })
})

describe('pairedMarginStats', () => {
  it('computes mean and standard error of paired differences', () => {
    const s = pairedMarginStats([2, 0, 4, 2])
    expect(s.margin).toBeCloseTo(2)
    // sd = sqrt(((0)^2 + (-2)^2 + (2)^2 + 0^2)/3) = sqrt(8/3); sem = sd/2
    expect(s.sem).toBeCloseTo(Math.sqrt(8 / 3) / 2)
    expect(s.tooClose).toBe(false) // 2 > 2*0.816
  })
  it('flags a margin within 2 SEM as too close', () => {
    const s = pairedMarginStats([1, -1, 1, -1, 1, -1, 1, 1])
    expect(s.margin).toBeCloseTo(0.25)
    expect(s.tooClose).toBe(true)
  })
  it('never calls identical-on-every-deal too close (sem 0)', () => {
    const s = pairedMarginStats([0, 0, 0, 0])
    expect(s.sem).toBe(0)
    expect(s.tooClose).toBe(false)
    expect(pairedMarginStats([3, 3, 3]).tooClose).toBe(false)
  })
  it('handles empty and single-deal inputs', () => {
    expect(pairedMarginStats([]).tooClose).toBe(false)
    expect(pairedMarginStats([5]).tooClose).toBe(false)
  })
})

describe('leadMetricDiffs', () => {
  const matrix: DealsMatrix = {
    cards: ['♥Q', '♠4', '♦2'],
    records: [
      { layout: {}, tricks: [8, 9, 9], scores: [50, -400, -400] },
      { layout: {}, tricks: [9, 9, 9], scores: [-400, -400, -400] },
    ],
  }
  it('MP diffs mirror the backend aggregate per deal', () => {
    // Deal 1: ♥Q beats both others -> 100; ♠4 ties ♦2 -> 25. Diff = 75.
    // Deal 2: all tie -> 50 each. Diff = 0.
    expect(leadMetricDiffs(matrix, '♥Q', '♠4', 'matchpoints')).toEqual([75, 0])
  })
  it('IMP diffs use the per-deal datum like the backend', () => {
    // Deal 1 datum = -250: imps(300)=7, imps(-150)=-4 -> diff 11. Deal 2: 0.
    expect(leadMetricDiffs(matrix, '♥Q', '♠4', 'imps')).toEqual([11, 0])
  })
  it('mean of diffs equals the difference of the aggregate metrics', () => {
    const diffs = leadMetricDiffs(matrix, '♥Q', '♠4', 'matchpoints')
    const mean = diffs.reduce((s, d) => s + d, 0) / diffs.length
    // aggregate MP%: ♥Q = (100+50)/2 = 75, ♠4 = (25+50)/2 = 37.5
    expect(mean).toBeCloseTo(75 - 37.5)
  })
  it('returns empty for an unknown card', () => {
    expect(leadMetricDiffs(matrix, '♥Q', '♣9', 'imps')).toEqual([])
  })
})

describe('benchmarkMetricDiffs', () => {
  const matrix: CandidateMatrix = {
    candidates: ['4S-S', '6S-S'],
    records: [
      { layout: {}, tricks: [10, 10], scores: [420, -50] },
      { layout: {}, tricks: [12, 12], scores: [480, 980] },
    ],
  }
  it('measures both candidates against the benchmark zero point', () => {
    // vs benchmark 4S-S: 6S contributes imps(-470)=-10 then imps(500)=11.
    expect(benchmarkMetricDiffs(matrix, '6S-S', '4S-S', '4S-S', 'imps')).toEqual([-10, 11])
    // MP: lose -> 0-50, win -> 100-50.
    expect(benchmarkMetricDiffs(matrix, '6S-S', '4S-S', '4S-S', 'matchpoints')).toEqual([-50, 50])
  })
})

describe('deal filter helpers', () => {
  const hand = 'AK8.Q95.J982.Q43' // 4+3+2+1+2 = 12 HCP
  it('computes HCP and suit lengths from a PBN hand', () => {
    expect(handHcp(hand)).toBe(12)
    expect(handHcp('T98.765.432.5432')).toBe(0)
    expect(handSuitLength(hand, 'S')).toBe(3)
    expect(handSuitLength(hand, 'D')).toBe(4)
  })
  it('is inactive at its defaults and active once narrowed', () => {
    const c = defaultCriterion('N')
    expect(criterionActive(c)).toBe(false)
    expect(criterionActive({ ...c, hcp: [10, 40] })).toBe(true)
    // A length window without a suit selected filters nothing.
    expect(criterionActive({ ...c, len: [4, 13] })).toBe(false)
    expect(criterionActive({ ...c, suit: 'H', len: [4, 13] })).toBe(true)
  })
  it('matches on HCP and suit length, and exclude inverts', () => {
    const layout = { N: hand, E: 'T98.765.432.5432' }
    const c = { ...defaultCriterion('N'), hcp: [10, 14] as [number, number] }
    expect(dealMatches(layout, c)).toBe(true)
    expect(dealMatches(layout, { ...c, seat: 'E' })).toBe(false)
    expect(dealMatches(layout, { ...c, exclude: true })).toBe(false)
    const withSuit = { ...c, suit: 'D' as const, len: [4, 13] as [number, number] }
    expect(dealMatches(layout, withSuit)).toBe(true)
    expect(dealMatches(layout, { ...withSuit, len: [5, 13] })).toBe(false)
  })
  it('describes an active criterion readably', () => {
    const c = { ...defaultCriterion('N'), hcp: [10, 14] as [number, number] }
    expect(describeCriterion(c)).toBe('10–14 HCP')
    expect(describeCriterion({ ...c, exclude: true })).toBe('not 10–14 HCP')
    expect(describeCriterion({ ...c, suit: 'S', len: [4, 13] })).toBe('10–14 HCP, 4–13 ♠')
  })
})

describe('describeSeatConstraints', () => {
  it('renders each constraint kind readably', () => {
    const c: Constraints = {
      hcp: { N: [10, 14] },
      suit_length: { N: { S: [4, 13], H: [0, 3], D: [2, 2], C: [1, 5] } },
      shapes: { N: '(5-5)-3-x' },
      quality: { N: { H: 'good' } },
      fixed_cards: { N: ['HA', 'HK'] },
    }
    expect(describeSeatConstraints(c, 'N')).toEqual([
      '10–14 HCP', '♠ 4+', '♥ ≤3', '♦ 2', '♣ 1–5',
      'shape: (5-5)-3-x', 'good ♥', 'holds ♥A ♥K',
    ])
  })
  it('returns an empty list for an unconstrained seat', () => {
    const c: Constraints = { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} }
    expect(describeSeatConstraints(c, 'E')).toEqual([])
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
