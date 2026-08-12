import { describe, expect, it, vi } from 'vitest'
import type { SimulateRequest } from '../api/leadTypes'
import type { ContractRequest } from '../api/contractTypes'
import {
  decodeShare, encodeShare, loadLastSetup, parseHash, saveLastSetup,
  SHARE_VERSION,
} from './share'

const LEAD_REQ: SimulateRequest = {
  leader_hand: 'Q85.K4.AQT976.T3',
  level: 3,
  strain: 'N',
  declarer: 'S',
  vul: 'none',
  penalty: 'none',
  num_simulations: 300,
  constraints: {
    hcp: { S: [15, 17] },
    suit_length: { N: { H: [4, 13] } },
    shapes: { N: '(4-4)-x-x or 5-3-3-2' },
    quality: { E: { D: 'good' } },
    fixed_cards: { N: ['HA', 'HK'] },
  },
}

const CONTRACT_REQ: ContractRequest = {
  hand: 'A743.987.A42.AQ6',
  seat: 'S',
  vul: 'ns',
  num_deals: 150,
  strains: ['N', 'S', 'H'],
  constraints: { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} },
}

describe('share codec', () => {
  it('round-trips a lead payload, constraints included', () => {
    const blob = encodeShare({ v: SHARE_VERSION, tool: 'lead', request: LEAD_REQ, view: { mode: 'imps' } })
    const back = decodeShare(blob)
    expect(back).not.toBeNull()
    expect(back!.tool).toBe('lead')
    expect(back!.request).toEqual(LEAD_REQ)
    expect(back!.view?.mode).toBe('imps')
  })

  it('round-trips a contract payload and restores empty constraints', () => {
    const blob = encodeShare({
      v: SHARE_VERSION, tool: 'contract', request: CONTRACT_REQ,
      view: { mode: 'matchpoints', benchmark: '4S-S' },
    })
    const back = decodeShare(blob)
    expect(back).not.toBeNull()
    expect(back!.request).toEqual(CONTRACT_REQ)
    expect(back!.tool === 'contract' && back!.view?.benchmark).toBe('4S-S')
  })

  it('produces URL-safe blobs', () => {
    const blob = encodeShare({ v: SHARE_VERSION, tool: 'lead', request: LEAD_REQ })
    expect(blob).toMatch(/^[A-Za-z0-9_-]+$/)
  })

  it('rejects garbage without throwing', () => {
    expect(decodeShare('%%%not-base64%%%')).toBeNull()
    expect(decodeShare('')).toBeNull()
    expect(decodeShare(btoa('not json'))).toBeNull()
    expect(decodeShare(btoa(JSON.stringify({ hello: 'world' })))).toBeNull()
  })

  it('rejects a wrong version and a wrong tool', () => {
    const wrongV = btoa(JSON.stringify({ v: 99, tool: 'lead', request: LEAD_REQ }))
    expect(decodeShare(wrongV)).toBeNull()
    const wrongTool = btoa(JSON.stringify({ v: 1, tool: 'poker', request: LEAD_REQ }))
    expect(decodeShare(wrongTool)).toBeNull()
  })

  it('rejects requests with missing or invalid fields', () => {
    const noHand = { ...LEAD_REQ, leader_hand: undefined }
    expect(decodeShare(btoa(JSON.stringify({ v: 1, tool: 'lead', request: noHand })))).toBeNull()
    const badLevel = { ...LEAD_REQ, level: 9 }
    expect(decodeShare(btoa(JSON.stringify({ v: 1, tool: 'lead', request: badLevel })))).toBeNull()
    const noStrains = { ...CONTRACT_REQ, strains: [] }
    expect(decodeShare(btoa(JSON.stringify({ v: 1, tool: 'contract', request: noStrains })))).toBeNull()
  })

  it('clamps out-of-range deal counts instead of rejecting', () => {
    const big = { ...LEAD_REQ, num_simulations: 99999 }
    const back = decodeShare(btoa(JSON.stringify({ v: 1, tool: 'lead', request: big })))
    expect(back!.request.num_simulations).toBe(1000)
  })

  it('drops an invalid view mode but keeps the payload', () => {
    const blob = btoa(JSON.stringify({ v: 1, tool: 'lead', request: LEAD_REQ, view: { mode: 'chaos' } }))
    const back = decodeShare(blob)
    expect(back).not.toBeNull()
    expect(back!.view?.mode).toBeUndefined()
  })
})

describe('last setup storage', () => {
  const store = new Map<string, string>()
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v) },
    },
  })

  it('round-trips a setup per tool and ignores the other slot', () => {
    saveLastSetup({ v: SHARE_VERSION, tool: 'lead', request: LEAD_REQ })
    expect(loadLastSetup('lead')?.request).toEqual(LEAD_REQ)
    expect(loadLastSetup('contract')).toBeNull()
  })

  it('survives a corrupted slot', () => {
    store.set('bridge.lastSetup.lead', '!!corrupted!!')
    expect(loadLastSetup('lead')).toBeNull()
  })
})

describe('parseHash', () => {
  it('splits tab and blob', () => {
    expect(parseHash('#lead?s=abc')).toEqual({ tab: 'lead', blob: 'abc' })
    expect(parseHash('#contract')).toEqual({ tab: 'contract', blob: null })
    expect(parseHash('')).toEqual({ tab: '', blob: null })
    expect(parseHash('#lead?x=1')).toEqual({ tab: 'lead', blob: null })
  })
})
