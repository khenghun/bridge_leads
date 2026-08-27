// BBO LIN parser — ported from bridge_ai/src/utils/linParser.js and typed.
//
// LIN is parsed in the browser ONLY: the play API takes structured state (four
// hands, the contract, the play so far), never a LIN string, so there is
// exactly one LIN grammar in the system and no drift between two parsers.
// `toAnalyzeRequest` below is the bridge between the two representations.

import type { Constraints, Seat, Suit } from '../api/types'
import type { AnalyzeRequest, PlayMethod } from '../api/playTypes'

/** Clockwise around the table: N -> E -> S -> W -> N. */
export const CLOCKWISE: Seat[] = ['N', 'E', 'S', 'W']

/** Dealer encoding per the BBO LIN standard. */
const DEALER_MAP: Record<string, Seat> = { 1: 'S', 2: 'W', 3: 'N', 4: 'E' }

/** BBO always lists hands in this fixed order, whoever dealt. */
const BBO_HAND_ORDER: Seat[] = ['S', 'W', 'N', 'E']

export type SuitName = 'spades' | 'hearts' | 'diamonds' | 'clubs'
export const SUIT_NAMES: SuitName[] = ['spades', 'hearts', 'diamonds', 'clubs']
/** Suit name -> the letter used everywhere else (endplay cards, PBN order). */
export const SUIT_OF: Record<SuitName, Suit> = {
  spades: 'S', hearts: 'H', diamonds: 'D', clubs: 'C',
}
const NAME_OF_SUIT: Record<Suit, SuitName> = {
  S: 'spades', H: 'hearts', D: 'diamonds', C: 'clubs',
}

/** A hand as sorted rank strings per suit, e.g. { spades: ['A','K','3'], ... }. */
export type Hand = Record<SuitName, string[]>

const RANK_VALUE: Record<string, number> = {
  A: 14, K: 13, Q: 12, J: 11, T: 10,
  9: 9, 8: 8, 7: 7, 6: 6, 5: 5, 4: 4, 3: 3, 2: 2,
}
const ALL_RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

export interface CardPlay {
  player: Seat
  suit: Suit
  rank: string
}

export interface Trick {
  leader: Seat
  cards: CardPlay[]
  /** null while the trick is still incomplete. */
  winner: Seat | null
}

export interface Bid {
  /** Raw LIN token, uppercased and stripped of the '!' alert marker: 'P',
   * 'D', 'R', '1C', '3N', ... */
  bid: string
  player: Seat
  /** Explanation text from a following `an|` field, '' when unalerted. */
  alert: string
}

export type Vulnerability = 'none' | 'NS' | 'EW' | 'both'
/** 0 = undoubled, 1 = doubled, 2 = redoubled. */
export type Doubled = 0 | 1 | 2

export interface LinContract {
  level: number
  /** 'S' | 'H' | 'D' | 'C' | 'NT'. */
  suit: string
  doubled: Doubled
}

export interface GameState {
  board: string
  dealer: Seat
  vulnerability: Vulnerability
  hands: Record<Seat, Hand | null>
  auction: Bid[]
  contract: LinContract | null
  declarer: Seat | null
  tricks: Trick[]
  play: CardPlay[]
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function sortRanks(ranks: string[]): string[] {
  return [...ranks].sort((a, b) => (RANK_VALUE[b] ?? 0) - (RANK_VALUE[a] ?? 0))
}

export function emptyHand(): Hand {
  return { spades: [], hearts: [], diamonds: [], clubs: [] }
}

/** Normalise a LIN rank token: '10' -> 'T', lower case -> upper. */
export function normRank(rank: string): string {
  const r = rank.trim().toUpperCase()
  return r === '10' ? 'T' : r
}

/** Parse a LIN hand string ('SAKT3HQ72DAK52C8') into per-suit rank arrays. */
export function parseHandString(str: string): Hand {
  const hand = emptyHand()
  let current: SuitName | null = null
  for (const raw of str.toUpperCase()) {
    if (raw === 'S' || raw === 'H' || raw === 'D' || raw === 'C') {
      current = NAME_OF_SUIT[raw as Suit]
    } else if (current && RANK_VALUE[raw] !== undefined) {
      hand[current].push(raw)
    }
    // Anything else ('-', void markers, stray digits) is skipped.
  }
  for (const name of SUIT_NAMES) hand[name] = sortRanks(hand[name])
  return hand
}

/** The 52 - 39 cards the three named hands do not hold. */
function deriveHand(known: Partial<Record<Seat, Hand>>): Hand {
  const used: Record<SuitName, Set<string>> = {
    spades: new Set(), hearts: new Set(), diamonds: new Set(), clubs: new Set(),
  }
  for (const hand of Object.values(known)) {
    if (!hand) continue
    for (const name of SUIT_NAMES) for (const rank of hand[name]) used[name].add(rank)
  }
  const derived = emptyHand()
  for (const name of SUIT_NAMES) {
    derived[name] = sortRanks(ALL_RANKS.filter((r) => !used[name].has(r)))
  }
  return derived
}

/** A hand as a PBN string, 'spades.hearts.diamonds.clubs' high-to-low. */
export function handToPbn(hand: Hand | null): string {
  if (!hand) return '...'
  return SUIT_NAMES.map((name) => sortRanks(hand[name]).join('')).join('.')
}

/** Total cards held - 13 for a well-formed hand. */
export function handSize(hand: Hand | null): number {
  if (!hand) return 0
  return SUIT_NAMES.reduce((n, name) => n + hand[name].length, 0)
}

/** A card in endplay form: 'SA', 'HK', 'DT', 'C2'. */
export function cardCode(card: CardPlay): string {
  return card.suit + normRank(card.rank)
}

interface Field { key: string; value: string }

/** Split a LIN string into its ordered `key|value|` fields. */
export function extractFields(text: string): Field[] {
  const fields: Field[] = []
  const re = /([a-zA-Z]{1,3})\|([^|]*)\|/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    fields.push({ key: m[1].toLowerCase(), value: m[2] })
  }
  return fields
}

const PASSES = new Set(['P', 'PASS', '-'])
const DOUBLES = new Set(['D', 'X', 'DBL'])
const REDOUBLES = new Set(['R', 'XX', 'RDBL'])

/** Uppercase a LIN bid token and drop the '!' alert marker BBO appends. */
export function normBid(bid: string): string {
  return (bid || '').replace(/!/g, '').trim().toUpperCase()
}

/** A pass, double or redouble - i.e. not a bid that names a strain. */
export function isCall(bid: string): boolean {
  const b = normBid(bid)
  return PASSES.has(b) || DOUBLES.has(b) || REDOUBLES.has(b)
}

/** The final contract: the last real bid, plus any double standing over it. */
export function determineContract(bids: string[]): LinContract | null {
  let last: { level: number; suit: string } | null = null
  let doubled: Doubled = 0
  for (const raw of bids) {
    const b = normBid(raw)
    if (!b || PASSES.has(b)) continue
    if (DOUBLES.has(b)) { doubled = 1; continue }
    if (REDOUBLES.has(b)) { doubled = 2; continue }
    const level = parseInt(b[0], 10)
    if (Number.isNaN(level)) continue
    let suit = b.slice(1)
    if (suit === 'N') suit = 'NT'
    last = { level, suit }
    // A new bid wipes any double standing over the previous one.
    doubled = 0
  }
  return last ? { ...last, doubled } : null
}

/** Winner of a (possibly partial) trick. Trump beats the led suit; within a
 * suit the top rank wins; a discard in a third suit never wins. */
export function trickWinner(cards: CardPlay[], trumpSuit: Suit | null): Seat | null {
  if (!cards.length) return null
  const led = cards[0].suit
  let winnerIdx = 0
  let winnerRank = RANK_VALUE[normRank(cards[0].rank)] ?? 0
  let winnerIsTrump = !!(trumpSuit && cards[0].suit === trumpSuit)

  for (let i = 1; i < cards.length; i++) {
    const card = cards[i]
    const isTrump = !!(trumpSuit && card.suit === trumpSuit)
    const rank = RANK_VALUE[normRank(card.rank)] ?? 0
    if (isTrump && !winnerIsTrump) {
      winnerIdx = i; winnerRank = rank; winnerIsTrump = true
    } else if (isTrump && winnerIsTrump) {
      if (rank > winnerRank) { winnerIdx = i; winnerRank = rank }
    } else if (!isTrump && !winnerIsTrump && card.suit === led) {
      if (rank > winnerRank) { winnerIdx = i; winnerRank = rank }
    }
  }
  return cards[winnerIdx].player
}

/** Declarer = the first player of the winning side to have bid the final
 * strain, at any level. (So partner, not the player who bid it last, declares
 * when partner introduced the suit.) */
export function determineDeclarer(auction: Bid[], contract: LinContract | null): Seat | null {
  if (!contract) return null

  let finalBidder: Seat | null = null
  for (const { bid, player } of auction) {
    if (normBid(bid) && !isCall(bid)) finalBidder = player
  }
  if (!finalBidder) return null

  const winningSide: Seat[] = finalBidder === 'N' || finalBidder === 'S' ? ['N', 'S'] : ['E', 'W']
  for (const { bid, player } of auction) {
    if (!winningSide.includes(player)) continue
    const b = normBid(bid)
    if (!b || isCall(b)) continue
    if (Number.isNaN(parseInt(b[0], 10))) continue
    let denom = b.slice(1)
    if (denom === 'N') denom = 'NT'
    if (denom === contract.suit) return player
  }
  return finalBidder
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/** Parse raw LIN text into a GameState. Never throws on junk: unparseable
 * sections come back empty (no contract, no hands) so the UI can say so. */
export function parseLIN(input: string): GameState {
  let text = input ?? ''
  // BBO links carry the LIN percent-encoded; a stray '%' that is not an escape
  // must not lose the whole file, hence the try.
  if (text.includes('%')) {
    try { text = decodeURIComponent(text.replace(/\+/g, ' ')) } catch { /* keep raw */ }
  }

  const fields = extractFields(text)

  const board = fields.find((f) => f.key === 'ah')?.value ?? ''

  let vulnerability: Vulnerability = 'none'
  const sv = fields.find((f) => f.key === 'sv')?.value.toLowerCase()
  if (sv === 'n') vulnerability = 'NS'
  else if (sv === 'e') vulnerability = 'EW'
  else if (sv === 'b') vulnerability = 'both'

  let dealer: Seat = 'N'
  let hands: Record<Seat, Hand | null> = { N: null, E: null, S: null, W: null }

  const md = fields.find((f) => f.key === 'md')?.value
  if (md) {
    dealer = DEALER_MAP[md[0]] ?? 'N'
    // A trailing comma ('...,hand3,|') is the common BBO 3-hand export - the
    // empty element it leaves behind must not be read as a fourth hand.
    const handStrings = md.slice(1).split(',').filter((s) => s.length > 0)
    const known: Partial<Record<Seat, Hand>> = {}
    for (let i = 0; i < handStrings.length && i < 4; i++) {
      known[BBO_HAND_ORDER[i]] = parseHandString(handStrings[i])
    }
    const missing = BBO_HAND_ORDER.find((p) => !known[p])
    if (missing) known[missing] = deriveHand(known)
    hands = { N: known.N ?? null, E: known.E ?? null, S: known.S ?? null, W: known.W ?? null }
  }

  // Bids, each paired with an immediately-following `an|` alert explanation.
  const bidTokens: Array<{ bid: string; alert: string }> = []
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].key !== 'mb') continue
    const alert = fields[i + 1]?.key === 'an' ? fields[i + 1].value : ''
    bidTokens.push({ bid: normBid(fields[i].value), alert })
  }

  const dealerIdx = CLOCKWISE.indexOf(dealer)
  const auction: Bid[] = bidTokens.map((item, i) => ({
    bid: item.bid,
    player: CLOCKWISE[(dealerIdx + i) % 4],
    alert: item.alert,
  }))

  const contract = determineContract(bidTokens.map((b) => b.bid))
  const declarer = determineDeclarer(auction, contract)

  const tricks: Trick[] = []
  const play: CardPlay[] = []
  const pcValues = fields.filter((f) => f.key === 'pc').map((f) => f.value.trim())

  if (pcValues.length && declarer && contract) {
    const trumpSuit = contract.suit === 'NT' ? null : (contract.suit as Suit)
    // Opening leader is LHO of declarer; thereafter the trick winner leads.
    let current: Trick = {
      leader: CLOCKWISE[(CLOCKWISE.indexOf(declarer) + 1) % 4], cards: [], winner: null,
    }
    for (const token of pcValues) {
      if (!token || token.length < 2) continue
      const suit = token[0].toUpperCase() as Suit
      const rank = normRank(token.slice(1))
      if (!'SHDC'.includes(suit) || RANK_VALUE[rank] === undefined) continue

      const player = CLOCKWISE[(CLOCKWISE.indexOf(current.leader) + current.cards.length) % 4]
      const card: CardPlay = { player, suit, rank }
      current.cards.push(card)
      play.push(card)

      if (current.cards.length === 4) {
        current.winner = trickWinner(current.cards, trumpSuit)
        tricks.push(current)
        current = { leader: current.winner as Seat, cards: [], winner: null }
      }
    }
    if (current.cards.length) tricks.push(current)
  }

  return { board, dealer, vulnerability, hands, auction, contract, declarer, tricks, play }
}

// ---------------------------------------------------------------------------
// GameState -> API request
// ---------------------------------------------------------------------------

/** LIN vulnerability wording -> the API's enum (app/common/schemas.py Vul). */
export function vulCode(v: Vulnerability): string {
  return v === 'NS' ? 'ns' : v === 'EW' ? 'ew' : v === 'both' ? 'both' : 'none'
}

/** LIN's doubled counter -> the API's `penalty` enum. */
export function penaltyCode(doubled: Doubled): string {
  return doubled === 1 ? 'doubled' : doubled === 2 ? 'redoubled' : 'none'
}

/** 'NT' -> the API's single-letter strain 'N'; suits pass through. */
export function strainCode(suit: string): string {
  return suit === 'NT' ? 'N' : suit
}

export interface AnalyzeOptions {
  method: PlayMethod
  numDeals: number
  constraints: Constraints
  /** Grade only the first N cards of the recorded play (default: all of it). */
  playLength?: number
}

/** True when the parse produced everything the API needs. */
export function isAnalyzable(game: GameState): boolean {
  return !!game.contract && !!game.declarer
    && CLOCKWISE.every((seat) => handSize(game.hands[seat]) === 13)
}

/** Build the POST /api/play/analyze body from a parsed hand.
 *
 * Throws when the LIN did not yield a contract, a declarer, or four complete
 * hands - the API requires all 52 cards, and a half-parsed file is a user
 * error worth naming rather than a 422 to decode. */
export function toAnalyzeRequest(
  game: GameState, seat: Seat, options: AnalyzeOptions,
): AnalyzeRequest {
  if (!game.contract) throw new Error('This LIN has no contract — the auction did not parse.')
  if (!game.declarer) throw new Error('This LIN has no declarer — the auction did not parse.')
  const short = CLOCKWISE.filter((s) => handSize(game.hands[s]) !== 13)
  if (short.length) {
    throw new Error(`Incomplete deal: ${short.join(', ')} did not parse to 13 cards.`)
  }

  const cards = game.play.slice(0, options.playLength ?? game.play.length)
  return {
    hands: {
      N: handToPbn(game.hands.N), E: handToPbn(game.hands.E),
      S: handToPbn(game.hands.S), W: handToPbn(game.hands.W),
    },
    level: game.contract.level,
    strain: strainCode(game.contract.suit),
    declarer: game.declarer,
    vul: vulCode(game.vulnerability),
    penalty: penaltyCode(game.contract.doubled),
    play: cards.map(cardCode),
    seat,
    method: options.method,
    num_deals: options.numDeals,
    constraints: options.constraints,
  }
}
