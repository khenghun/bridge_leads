import { describe, expect, it } from 'vitest'
import type { CandidateResult, ContractResponse } from '../../api/contractTypes'
import { benchmarkOptions, rankContracts } from './ranking'

function candidate(over: Partial<CandidateResult> & { key: string }): CandidateResult {
  return {
    label: over.key, level: 4, strain: 'S', declarer: 'S', kind: 'game',
    tricks_needed: 10, make_rate: 1, mean_tricks: 10, mean_score: 420,
    fail_mean_score: null, seat_delta: 0, ...over,
  } as CandidateResult
}

/** Two contracts (4♠ and 3NT), each playable by either seat, over four deals.
 * 4♠ by North is a trick better than by South; 3NT trails both. */
function response(): ContractResponse {
  const candidates = [
    candidate({ key: '4S-S', label: '4♠', declarer: 'S', mean_tricks: 10.0, seat_delta: -0.5 }),
    candidate({ key: '4S-N', label: '4♠', declarer: 'N', mean_tricks: 10.5, seat_delta: 0.5 }),
    candidate({ key: '3N-S', label: '3NT', strain: 'N', level: 3, tricks_needed: 9, declarer: 'S', kind: 'game', mean_score: 400 }),
    candidate({ key: '3N-N', label: '3NT', strain: 'N', level: 3, tricks_needed: 9, declarer: 'N', kind: 'game', mean_score: 395 }),
    candidate({ key: '1S-S', label: '♠ partscore', level: 1, tricks_needed: 7, kind: 'part', mean_score: 170 }),
    candidate({ key: '1S-N', label: '♠ partscore', level: 1, tricks_needed: 7, declarer: 'N', kind: 'part', mean_score: 170 }),
  ]
  const scores = [
    // 4S-S, 4S-N, 3N-S, 3N-N, 1S-S, 1S-N
    [420, 450, 400, 400, 170, 170],
    [420, 450, 400, 400, 170, 170],
    [-50, 420, 400, 400, 170, 170],
    [420, 420, -50, -50, 170, 170],
  ]
  return {
    num_deals: 4, seat: 'S', partner: 'N', vul: 'none',
    candidates,
    default_benchmark: '4S-S',
    opponents: { opps_game_rate: 0, par_competitive_rate: 0 },
    deals: {
      candidates: candidates.map((c) => c.key),
      records: scores.map((s) => ({ layout: {}, tricks: [10, 10, 9, 9, 10, 10], scores: s })),
    },
  }
}

describe('rankContracts', () => {
  it('collapses each contract to its better declarer', () => {
    const rows = rankContracts(response(), '4S-S', 'imps')
    // one row per contract (4♠, 3NT, ♠ partscore), not one per seat
    expect(rows).toHaveLength(3)
    expect(rows.map((r) => r.best.label)).toContain('4♠')
    const spades = rows.find((r) => r.best.label === '4♠')!
    expect(spades.best.declarer).toBe('N')     // the seat that scores better
    expect(spades.alt.declarer).toBe('S')
    expect(spades.seatMatters).toBe(true)      // 0.5 tricks apart
  })

  it('ranks best-first and marks the benchmark', () => {
    const rows = rankContracts(response(), '4S-S', 'imps')
    expect(rows[0].best.key).toBe('4S-N')
    expect(rows[0].score).toBeGreaterThan(0)
    expect(rows.map((r) => r.score)).toEqual([...rows.map((r) => r.score)].sort((a, b) => b - a))
    const benchRow = rankContracts(response(), '1S-S', 'imps').find((r) => r.isBenchmark)
    expect(benchRow?.best.key).toBe('1S-S')
    expect(benchRow?.score).toBe(0)
  })

  it('can rank on matchpoints instead, where only frequency counts', () => {
    const rows = rankContracts(response(), '4S-S', 'matchpoints')
    const spades = rows.find((r) => r.best.label === '4♠')!
    // 4♠ by N outscores the benchmark (4♠ by S) on three deals, ties the last:
    // 100 * (3 + 0.5) / 4
    expect(spades.metric.mpPct).toBeCloseTo(87.5)
  })

  it('flags an edge that rests on very few deals', () => {
    const res = response()
    // 3NT gains hugely on one deal only and matches the benchmark on the rest.
    res.deals.records.forEach((r, i) => { r.scores[2] = i === 0 ? 1500 : r.scores[0] })
    const row = rankContracts(res, '4S-S', 'imps').find((r) => r.best.key === '3N-S')!
    expect(row.metric.imps).toBeGreaterThan(0)
    expect(row.thinEdge).toBe(true)
  })

  it('does not flag a near-tie, where the badge would be noise', () => {
    const rows = rankContracts(response(), '3N-S', 'imps')
    const partscore = rows.find((r) => r.best.kind === 'part')!
    expect(partscore.thinEdge).toBe(false)
  })
})

describe('benchmarkOptions', () => {
  it('offers one entry per contract, highest expected score first', () => {
    const options = benchmarkOptions(response())
    expect(options).toHaveLength(3)
    expect(options.map((c) => c.label)).toEqual(['4♠', '3NT', '♠ partscore'])
    expect(new Set(options.map((c) => `${c.level}${c.strain}`)).size).toBe(3)
  })
})
