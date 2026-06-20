import { describe, expect, it } from 'vitest'
import {
  holdingError, holdingsToPbn, leaderSeat, parseContract, parsePbn, randomHand, sortHolding,
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
