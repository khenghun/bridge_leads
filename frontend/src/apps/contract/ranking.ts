// Turning the API response into the ranked table the user reads.
//
// The backend deliberately ships raw per-deal scores instead of a ranking, so
// switching scoring mode or benchmark contract re-ranks instantly here without
// re-simulating — the same division of labour the lead tool's mode toggle uses.

import type { Mode } from '../../api/types'
import type { CandidateResult, ContractResponse } from '../../api/contractTypes'
import { rankVsBenchmark, type BenchmarkMetric } from '../../lib/bridge'

/** Declarer matters when the two seats differ by at least this many mean
 * tricks — worth telling the user which hand should play it. */
export const SEAT_MATTERS_TRICKS = 0.3

/** A positive edge is "thin" when this much of it comes from the best 15% of
 * deals: the contract is not better, it is luckier. Only worth warning about
 * once the edge is big enough to act on — below that the row is a coin-flip
 * anyway and the badge is just noise. */
export const THIN_EDGE_SHARE = 0.6
export const THIN_EDGE_MIN_IMPS = 0.5

export interface RankedContract {
  /** The better of the two declarer rows for this level+strain. */
  best: CandidateResult
  /** The same contract played by partner. */
  alt: CandidateResult
  metric: BenchmarkMetric
  /** Value the table is sorted by, in the active scoring mode. */
  score: number
  isBenchmark: boolean
  seatMatters: boolean
  thinEdge: boolean
}

export function metricValue(m: BenchmarkMetric, mode: Mode): number {
  return mode === 'matchpoints' ? m.mpPct : m.imps
}

/** One row per contract (level+strain), played by whichever seat does better in
 * the active scoring mode, sorted best-first. */
export function rankContracts(
  res: ContractResponse, benchmarkKey: string, mode: Mode,
): RankedContract[] {
  const metrics = rankVsBenchmark(res.deals, benchmarkKey)
  const byContract = new Map<string, CandidateResult[]>()
  for (const c of res.candidates) {
    const id = `${c.level}${c.strain}`
    byContract.set(id, [...(byContract.get(id) ?? []), c])
  }

  const rows: RankedContract[] = []
  for (const seats of byContract.values()) {
    const scored = seats
      .filter((c) => metrics[c.key])
      .sort((a, b) => metricValue(metrics[b.key], mode) - metricValue(metrics[a.key], mode))
    if (!scored.length) continue
    const best = scored[0]
    const alt = scored[scored.length - 1]
    const metric = metrics[best.key]
    rows.push({
      best,
      alt,
      metric,
      score: metricValue(metric, mode),
      isBenchmark: best.key === benchmarkKey,
      seatMatters: Math.abs(best.seat_delta) >= SEAT_MATTERS_TRICKS,
      thinEdge: metric.imps >= THIN_EDGE_MIN_IMPS
        && metric.edgeConcentration >= THIN_EDGE_SHARE,
    })
  }

  // The benchmark itself always scores 0 by construction; ties break towards the
  // contract that makes more often, which is the safer recommendation.
  return rows.sort((a, b) => (b.score - a.score) || (b.best.make_rate - a.best.make_rate))
}

/** Contracts offered as the benchmark: one row per contract (its better seat),
 * highest expected score first — so the default the backend picked is at the
 * top and the realistic alternatives are next to it. */
export function benchmarkOptions(res: ContractResponse): CandidateResult[] {
  const seen = new Set<string>()
  const out: CandidateResult[] = []
  for (const c of [...res.candidates].sort((a, b) => b.mean_score - a.mean_score)) {
    const id = `${c.level}${c.strain}`
    if (seen.has(id)) continue
    seen.add(id)
    out.push(c)
  }
  return out
}
