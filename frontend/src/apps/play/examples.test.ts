import { describe, expect, it } from 'vitest'
import { CLOCKWISE, handSize, isAnalyzable, parseLIN } from '../../lib/lin'
import { EXAMPLES } from './examples'

describe('built-in example hands', () => {
  it('has unique ids and keeps Board 17 · 1NT by West first (the run-apps fixture)', () => {
    expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length)
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(5)
    const first = parseLIN(EXAMPLES[0].lin)
    expect(first.board).toBe('Board 17')
    expect(first.contract).toMatchObject({ level: 1, suit: 'NT' })
    expect(first.declarer).toBe('W')
  })

  it.each(EXAMPLES.map((e) => [e.id, e] as const))('%s parses to a complete, gradable hand', (_id, ex) => {
    const g = parseLIN(ex.lin)
    for (const s of CLOCKWISE) expect(handSize(g.hands[s]), `${s} hand`).toBe(13)
    expect(g.contract, 'contract').not.toBeNull()
    expect(g.declarer, 'declarer').not.toBeNull()
    expect(g.play.length, 'cards played').toBeGreaterThan(0)
    expect(isAnalyzable(g)).toBe(true)
    // Every card in the play must come from the hand that played it — a
    // mis-transcribed example would 422 on the server instead of grading.
    for (const c of g.play) {
      const hand = g.hands[c.player]!
      const suitName = ({ S: 'spades', H: 'hearts', D: 'diamonds', C: 'clubs' } as const)[c.suit]
      expect(hand[suitName], `${c.player} played ${c.suit}${c.rank}`).toContain(c.rank)
    }
  })

  it('never carries player names — the pn field is the four seats', () => {
    for (const ex of EXAMPLES) {
      expect(ex.lin).toMatch(/^pn\|South,West,North,East\|/)
      expect(ex.lin).not.toMatch(/\n/)
    }
  })

  it('titles and blurbs are filled in', () => {
    for (const ex of EXAMPLES) {
      expect(ex.title.length).toBeGreaterThan(8)
      expect(ex.blurb.length).toBeGreaterThan(30)
    }
  })
})
