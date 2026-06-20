// Pure bridge helpers ported from the old Streamlit app.py.

import type { Seat, Suit } from '../api/types'

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
