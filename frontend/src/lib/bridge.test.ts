import { describe, expect, it } from 'vitest'
import type { DealsMatrix } from '../api/types'
import {
  compareLeads, holdingError, holdingsToPbn, imps, leaderSeat, parseContract, parsePbn,
  randomHand, sortHolding,
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
})
