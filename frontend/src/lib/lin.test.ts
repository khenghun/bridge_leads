import { describe, expect, it } from 'vitest'
import {
  CLOCKWISE, cardCode, determineContract, handSize, handToPbn, isAnalyzable,
  parseLIN, toAnalyzeRequest, trickWinner, type CardPlay,
} from './lin'
import type { Constraints, Seat } from '../api/types'

// The three grammar fixtures from bridge_ai/solver/test_parse_lin.py — Board 17,
// 1NT by West. Same deal three ways: all four hands explicit, three hands with
// BBO's trailing comma, three hands clean.
const MD_4 = 'md|3SKT3HJT7D87CKQ843,SA54HQ94DT963CAT2,S9872HK85DAJ542C5,SQJ6HA632DKQCJ976|'
const MD_3_TRAILING = 'md|3SKT3HJT7D87CKQ843,SA54HQ94DT963CAT2,S9872HK85DAJ542C5,|'
const MD_3_CLEAN = 'md|3SKT3HJT7D87CKQ843,SA54HQ94DT963CAT2,S9872HK85DAJ542C5|'

const AUCTION = 'mb|p|mb|1C|mb|p|mb|1N|mb|p|mb|p|mb|p|pg||'
const HEAD = 'pn|South,West,North,East|st||'
const TAIL = 'rh||ah|Board 17|sv|o|'

function lin(md: string, auction = AUCTION, play = 'pc|S9|pc|SJ|pc|SK|pc|S5|pg||') {
  return HEAD + md + TAIL + auction + play
}

const LIN_4HANDS = lin(MD_4)
const LIN_3HANDS_TRAILING = lin(MD_3_TRAILING)
const LIN_3HANDS_CLEAN = lin(MD_3_CLEAN)

/** The example shipped with the app — the same board with nine tricks played. */
const FULL_PLAY = (
  'pc|S9|pc|SJ|pc|SK|pc|S5|pg||'
  + 'pc|ST|pc|S4|pc|S2|pc|SQ|pg||'
  + 'pc|C6|pc|C4|pc|CT|pc|C5|pg||'
  + 'pc|D3|pc|D5|pc|DQ|pc|D7|pg||'
)
const LIN_FULL = lin(MD_4, AUCTION, FULL_PLAY)

function noConstraints(): Constraints {
  return { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} }
}

function card(player: Seat, code: string): CardPlay {
  return { player, suit: code[0] as CardPlay['suit'], rank: code.slice(1) }
}

describe('parseLIN — hands', () => {
  for (const [name, text] of [
    ['4 explicit hands', LIN_4HANDS],
    ['3 hands with a trailing comma', LIN_3HANDS_TRAILING],
    ['3 hands, no trailing comma', LIN_3HANDS_CLEAN],
  ] as const) {
    it(`${name}: all four seats parse to 13 cards, 52 distinct`, () => {
      const game = parseLIN(text)
      const seen = new Set<string>()
      for (const seat of CLOCKWISE) {
        const hand = game.hands[seat]
        expect(hand, `${seat} missing`).not.toBeNull()
        expect(handSize(hand), `${seat} card count`).toBe(13)
        for (const c of handToPbn(hand).split('.').flatMap((s, i) => (
          [...s].map((r) => 'SHDC'[i] + r)))) seen.add(c)
      }
      expect(seen.size).toBe(52)
    })
  }

  it('derives the missing East identically to the explicit 4-hand form', () => {
    const explicit = parseLIN(LIN_4HANDS)
    for (const text of [LIN_3HANDS_TRAILING, LIN_3HANDS_CLEAN]) {
      expect(handToPbn(parseLIN(text).hands.E)).toBe(handToPbn(explicit.hands.E))
    }
  })

  it('places the BBO hand order S, W, N, E', () => {
    const game = parseLIN(LIN_4HANDS)
    expect(handToPbn(game.hands.S)).toBe('KT3.JT7.87.KQ843')
    expect(handToPbn(game.hands.W)).toBe('A54.Q94.T963.AT2')
    expect(handToPbn(game.hands.N)).toBe('9872.K85.AJ542.5')
    expect(handToPbn(game.hands.E)).toBe('QJ6.A632.KQ.J976')
  })
})

describe('parseLIN — board, dealer, vulnerability', () => {
  it('reads the board name and dealer digit', () => {
    const game = parseLIN(LIN_4HANDS)
    expect(game.board).toBe('Board 17')
    expect(game.dealer).toBe('N') // digit 3
  })

  it('maps every dealer digit through S, W, N, E', () => {
    for (const [digit, seat] of [['1', 'S'], ['2', 'W'], ['3', 'N'], ['4', 'E']] as const) {
      expect(parseLIN(lin(`md|${digit}${MD_4.slice(4)}`)).dealer).toBe(seat)
    }
  })

  it('maps sv|o/n/e/b to the four vulnerabilities', () => {
    const cases = [['o', 'none'], ['n', 'NS'], ['e', 'EW'], ['b', 'both']] as const
    for (const [code, expected] of cases) {
      const text = LIN_4HANDS.replace('sv|o|', `sv|${code}|`)
      expect(parseLIN(text).vulnerability).toBe(expected)
    }
  })
})

describe('parseLIN — auction', () => {
  it('assigns bids clockwise from the dealer', () => {
    const game = parseLIN(LIN_4HANDS)
    expect(game.auction.map((b) => `${b.player}:${b.bid}`)).toEqual([
      'N:P', 'E:1C', 'S:P', 'W:1N', 'N:P', 'E:P', 'S:P',
    ])
  })

  it('strips the ! alert marker and keeps the an| explanation', () => {
    const game = parseLIN(lin(MD_4, 'mb|p|mb|1C!|an|could be short|mb|p|mb|1N|mb|p|mb|p|mb|p|'))
    expect(game.auction[1].bid).toBe('1C')
    expect(game.auction[1].alert).toBe('could be short')
    expect(game.contract).toEqual({ level: 1, suit: 'NT', doubled: 0 })
  })

  it('reads the final contract and its declarer', () => {
    const game = parseLIN(LIN_4HANDS)
    expect(game.contract).toEqual({ level: 1, suit: 'NT', doubled: 0 })
    // East opened 1C, West bid notrump first — so West declares.
    expect(game.declarer).toBe('W')
  })

  it('gives declarer to the partner who bid the strain first', () => {
    // Dealer N: 1S (N) - P (E) - 4S (S) - P - P - P. South bid it last, but
    // North introduced spades, so North declares.
    const game = parseLIN(lin(MD_4, 'mb|1S|mb|p|mb|4S|mb|p|mb|p|mb|p|'))
    expect(game.contract).toEqual({ level: 4, suit: 'S', doubled: 0 })
    expect(game.declarer).toBe('N')
  })

  it('carries a double through to the contract', () => {
    const game = parseLIN(lin(MD_4, 'mb|1S|mb|p|mb|4S|mb|d|mb|p|mb|p|mb|p|'))
    expect(game.contract).toEqual({ level: 4, suit: 'S', doubled: 1 })
    expect(game.declarer).toBe('N')
  })

  it('carries a redouble', () => {
    const game = parseLIN(lin(MD_4, 'mb|1S|mb|p|mb|4S|mb|d|mb|r|mb|p|mb|p|mb|p|'))
    expect(game.contract?.doubled).toBe(2)
  })

  it('a later bid clears a double standing over the previous one', () => {
    expect(determineContract(['1S', 'd', '2H', 'p', 'p', 'p'])).toEqual(
      { level: 2, suit: 'H', doubled: 0 })
  })

  it('returns no contract for an all-pass auction', () => {
    expect(determineContract(['p', 'p', 'p', 'p'])).toBeNull()
    expect(parseLIN(lin(MD_4, 'mb|p|mb|p|mb|p|mb|p|')).declarer).toBeNull()
  })
})

describe('parseLIN — play', () => {
  it('attributes cards to seats and finds the trick winners', () => {
    const game = parseLIN(LIN_FULL)
    // 1NT by West, so North leads.
    expect(game.tricks[0].leader).toBe('N')
    expect(game.tricks[0].cards.map((c) => `${c.player}${cardCode(c)}`)).toEqual([
      'NS9', 'ESJ', 'SSK', 'WS5',
    ])
    expect(game.tricks.map((t) => t.winner)).toEqual(['S', 'E', 'W', 'E'])
    // The winner of each trick leads the next.
    expect(game.tricks.map((t) => t.leader)).toEqual(['N', 'S', 'E', 'W'])
    expect(game.play).toHaveLength(16)
  })

  it('keeps an unfinished last trick with no winner', () => {
    const game = parseLIN(lin(MD_4, AUCTION, FULL_PLAY + 'pc|H2|pc|HT|'))
    const last = game.tricks[game.tricks.length - 1]
    expect(last.cards).toHaveLength(2)
    expect(last.winner).toBeNull()
    expect(game.play).toHaveLength(18)
  })

  it('normalises a 10 written out in full', () => {
    const game = parseLIN(lin(MD_4, AUCTION, 'pc|S9|pc|SJ|pc|SK|pc|S5|pg||pc|S10|'))
    expect(cardCode(game.play[4])).toBe('ST')
  })

  it('produces no play when the auction yielded no declarer', () => {
    const game = parseLIN(lin(MD_4, 'mb|p|mb|p|mb|p|mb|p|', FULL_PLAY))
    expect(game.play).toEqual([])
    expect(game.tricks).toEqual([])
  })
})

describe('trickWinner', () => {
  it('gives the trick to the highest card of the suit led at notrump', () => {
    const cards = [card('N', 'S9'), card('E', 'SJ'), card('S', 'SK'), card('W', 'S5')]
    expect(trickWinner(cards, null)).toBe('S')
  })

  it('ignores a discard in another suit', () => {
    const cards = [card('N', 'S9'), card('E', 'HA'), card('S', 'S3'), card('W', 'DA')]
    expect(trickWinner(cards, null)).toBe('N')
  })

  it('lets a trump beat the led suit', () => {
    const cards = [card('N', 'SA'), card('E', 'H2'), card('S', 'S3'), card('W', 'S4')]
    expect(trickWinner(cards, 'H')).toBe('E')
  })

  it('gives an over-ruff the trick', () => {
    const cards = [card('N', 'SA'), card('E', 'H2'), card('S', 'S3'), card('W', 'H5')]
    expect(trickWinner(cards, 'H')).toBe('W')
  })

  it('scores a trump lead by rank', () => {
    const cards = [card('N', 'H4'), card('E', 'H2'), card('S', 'HK'), card('W', 'H5')]
    expect(trickWinner(cards, 'H')).toBe('S')
  })

  it('handles a partial trick', () => {
    expect(trickWinner([card('N', 'S9'), card('E', 'SJ')], null)).toBe('E')
    expect(trickWinner([], null)).toBeNull()
  })
})

describe('parseLIN — URL-encoded input', () => {
  it('decodes a percent-encoded LIN before parsing', () => {
    const encoded = encodeURIComponent(LIN_FULL)
    expect(encoded).not.toContain('|')
    const game = parseLIN(encoded)
    expect(game.declarer).toBe('W')
    expect(game.board).toBe('Board 17')
    expect(handToPbn(game.hands.N)).toBe('9872.K85.AJ542.5')
    expect(game.play).toHaveLength(16)
  })

  it('survives a stray % that is not an escape', () => {
    const game = parseLIN(`${LIN_4HANDS}nt|100% forcing|`)
    expect(game.declarer).toBe('W')
  })
})

describe('toAnalyzeRequest', () => {
  it('builds the API body from a parsed hand', () => {
    const game = parseLIN(LIN_FULL)
    expect(isAnalyzable(game)).toBe(true)
    const req = toAnalyzeRequest(game, 'W', {
      method: 'single_dummy', numDeals: 20, constraints: noConstraints(),
    })
    expect(req.hands).toEqual({
      N: '9872.K85.AJ542.5',
      E: 'QJ6.A632.KQ.J976',
      S: 'KT3.JT7.87.KQ843',
      W: 'A54.Q94.T963.AT2',
    })
    expect(req.level).toBe(1)
    expect(req.strain).toBe('N')
    expect(req.declarer).toBe('W')
    expect(req.vul).toBe('none')
    expect(req.penalty).toBe('none')
    expect(req.seat).toBe('W')
    expect(req.method).toBe('single_dummy')
    expect(req.num_deals).toBe(20)
    expect(req.play.slice(0, 5)).toEqual(['S9', 'SJ', 'SK', 'S5', 'ST'])
    expect(req.play).toHaveLength(16)
  })

  it('maps vulnerability and penalty to the API enums', () => {
    const text = lin(MD_4, 'mb|1S|mb|p|mb|4S|mb|d|mb|p|mb|p|mb|p|', FULL_PLAY)
      .replace('sv|o|', 'sv|b|')
    const req = toAnalyzeRequest(parseLIN(text), 'N', {
      method: 'double_dummy', numDeals: 20, constraints: noConstraints(),
    })
    expect(req.vul).toBe('both')
    expect(req.penalty).toBe('doubled')
    expect(req.strain).toBe('S')
  })

  it('truncates the play to a requested position', () => {
    const game = parseLIN(LIN_FULL)
    const req = toAnalyzeRequest(game, 'W', {
      method: 'single_dummy', numDeals: 20, constraints: noConstraints(), playLength: 6,
    })
    expect(req.play).toEqual(['S9', 'SJ', 'SK', 'S5', 'ST', 'S4'])
  })

  it('refuses a LIN with no contract', () => {
    const game = parseLIN(lin(MD_4, 'mb|p|mb|p|mb|p|mb|p|'))
    expect(isAnalyzable(game)).toBe(false)
    expect(() => toAnalyzeRequest(game, 'N', {
      method: 'single_dummy', numDeals: 20, constraints: noConstraints(),
    })).toThrow(/no contract/)
  })

  it('refuses an incomplete deal', () => {
    const game = parseLIN(lin('md|3SKT3HJT7D87CKQ843|'))
    expect(isAnalyzable(game)).toBe(false)
    expect(() => toAnalyzeRequest(game, 'N', {
      method: 'single_dummy', numDeals: 20, constraints: noConstraints(),
    })).toThrow(/Incomplete deal/)
  })
})
