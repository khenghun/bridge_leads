// Share links: the request that produced a result (plus view state), encoded
// in the URL hash as `#<tool>?s=<base64url JSON>`. Opening one restores the
// setup and auto-runs — seed=0 determinism means the recipient recomputes the
// identical result, which is what lets a link replace server-side storage.
//
// The decoded payload is untrusted input to the FORM layer, not to the API:
// decode defensively (never throw), clamp ranges, and let the backend's 422s
// stay the backstop.

import type { Constraints, Mode, Seat } from '../api/types'
import type { SimulateRequest } from '../api/leadTypes'
import type { ContractRequest } from '../api/contractTypes'

export const SHARE_VERSION = 1

export interface LeadView { mode?: Mode }
export interface ContractView { mode?: Mode; benchmark?: string }

export type SharePayload =
  | { v: typeof SHARE_VERSION; tool: 'lead'; request: SimulateRequest; view?: LeadView }
  | { v: typeof SHARE_VERSION; tool: 'contract'; request: ContractRequest; view?: ContractView }

// --- base64url over UTF-8 (shape text may contain arbitrary characters) ---

function toBase64Url(s: string): string {
  const bytes = new TextEncoder().encode(s)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromBase64Url(s: string): string | null {
  try {
    const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/'))
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)))
  } catch {
    return null
  }
}

// --- constraints: drop empty parts on encode, restore defaults on decode ---

function compactConstraints(c: Constraints): Partial<Constraints> {
  const out: Partial<Constraints> = {}
  if (Object.keys(c.hcp ?? {}).length) out.hcp = c.hcp
  if (Object.keys(c.suit_length ?? {}).length) out.suit_length = c.suit_length
  if (Object.keys(c.shapes ?? {}).length) out.shapes = c.shapes
  if (Object.keys(c.quality ?? {}).length) out.quality = c.quality
  if (Object.keys(c.fixed_cards ?? {}).length) out.fixed_cards = c.fixed_cards
  return out
}

function expandConstraints(x: unknown): Constraints {
  const c = (typeof x === 'object' && x !== null ? x : {}) as Partial<Constraints>
  return {
    hcp: c.hcp ?? {},
    suit_length: c.suit_length ?? {},
    shapes: c.shapes ?? {},
    quality: c.quality ?? {},
    fixed_cards: c.fixed_cards ?? {},
  }
}

// --- validation ---

const SEATS_OK = new Set(['N', 'E', 'S', 'W'])
const STRAINS_OK = new Set(['N', 'S', 'H', 'D', 'C'])
const MODES_OK = new Set(['matchpoints', 'imps'])

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, Math.round(n)))
}

function asRecord(x: unknown): Record<string, unknown> | null {
  return typeof x === 'object' && x !== null && !Array.isArray(x)
    ? (x as Record<string, unknown>) : null
}

function validLeadRequest(x: unknown): SimulateRequest | null {
  const r = asRecord(x)
  if (!r) return null
  const { leader_hand, level, strain, declarer, vul, penalty, num_simulations } = r
  if (typeof leader_hand !== 'string') return null
  if (typeof level !== 'number' || level < 1 || level > 7) return null
  if (typeof strain !== 'string' || !STRAINS_OK.has(strain)) return null
  if (typeof declarer !== 'string' || !SEATS_OK.has(declarer)) return null
  if (typeof vul !== 'string' || typeof penalty !== 'string') return null
  if (typeof num_simulations !== 'number') return null
  return {
    leader_hand,
    level: Math.round(level),
    strain,
    declarer,
    vul,
    penalty,
    num_simulations: clamp(num_simulations, 100, 1000),
    constraints: expandConstraints(r.constraints),
  }
}

function validContractRequest(x: unknown): ContractRequest | null {
  const r = asRecord(x)
  if (!r) return null
  const { hand, seat, vul, num_deals, strains } = r
  if (typeof hand !== 'string') return null
  if (typeof seat !== 'string' || !SEATS_OK.has(seat)) return null
  if (typeof vul !== 'string') return null
  if (typeof num_deals !== 'number') return null
  if (!Array.isArray(strains)) return null
  const okStrains = [...new Set(strains.filter(
    (s): s is string => typeof s === 'string' && STRAINS_OK.has(s)))]
  if (!okStrains.length) return null
  return {
    hand,
    seat: seat as Seat,
    vul,
    num_deals: clamp(num_deals, 50, 500),
    strains: okStrains,
    constraints: expandConstraints(r.constraints),
  }
}

// --- public API ---

export function encodeShare(payload: SharePayload): string {
  const compact = {
    ...payload,
    request: { ...payload.request, constraints: compactConstraints(payload.request.constraints) },
    ...(payload.view && Object.keys(payload.view).length ? { view: payload.view } : { view: undefined }),
  }
  return toBase64Url(JSON.stringify(compact))
}

/** Decode a share blob. Returns null on anything malformed — a bad link must
 * degrade to the plain app, never crash or silently prefill nonsense. */
export function decodeShare(blob: string): SharePayload | null {
  const json = fromBase64Url(blob)
  if (json === null) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(json)
  } catch {
    return null
  }
  const p = asRecord(parsed)
  if (!p || p.v !== SHARE_VERSION) return null
  const viewRec = asRecord(p.view) ?? {}
  const mode = typeof viewRec.mode === 'string' && MODES_OK.has(viewRec.mode)
    ? (viewRec.mode as Mode) : undefined
  if (p.tool === 'lead') {
    const request = validLeadRequest(p.request)
    if (!request) return null
    return { v: SHARE_VERSION, tool: 'lead', request, view: { mode } }
  }
  if (p.tool === 'contract') {
    const request = validContractRequest(p.request)
    if (!request) return null
    const benchmark = typeof viewRec.benchmark === 'string' ? viewRec.benchmark : undefined
    return { v: SHARE_VERSION, tool: 'contract', request, view: { mode, benchmark } }
  }
  return null
}

/** Full URL for a payload, anchored at the current app location. */
export function buildShareUrl(payload: SharePayload): string {
  const { origin, pathname } = window.location
  return `${origin}${pathname}#${payload.tool}?s=${encodeShare(payload)}`
}

/** Split a location hash into its tab and (undecoded) share blob. */
export function parseHash(hash: string): { tab: string; blob: string | null } {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  const q = raw.indexOf('?')
  const tab = q < 0 ? raw : raw.slice(0, q)
  const params = q < 0 ? null : new URLSearchParams(raw.slice(q + 1))
  return { tab, blob: params?.get('s') ?? null }
}

// --- last setup: the same payload, persisted locally instead of in a URL ---

const SETUP_KEY_PREFIX = 'bridge.lastSetup.'

/** Persist the setup that was just simulated (one slot per tool). Best-effort:
 * localStorage can be unavailable (private mode, quotas) and losing the slot
 * must never break a simulation. */
export function saveLastSetup(payload: SharePayload): void {
  try {
    window.localStorage.setItem(SETUP_KEY_PREFIX + payload.tool, encodeShare(payload))
  } catch {
    /* best-effort */
  }
}

/** The last setup simulated on this device for a tool, if any survives the
 * same defensive decode a share link gets. */
export function loadLastSetup(tool: 'lead'): Extract<SharePayload, { tool: 'lead' }> | null
export function loadLastSetup(tool: 'contract'): Extract<SharePayload, { tool: 'contract' }> | null
export function loadLastSetup(tool: SharePayload['tool']): SharePayload | null {
  try {
    const blob = window.localStorage.getItem(SETUP_KEY_PREFIX + tool)
    if (!blob) return null
    const payload = decodeShare(blob)
    return payload?.tool === tool ? payload : null
  } catch {
    return null
  }
}
