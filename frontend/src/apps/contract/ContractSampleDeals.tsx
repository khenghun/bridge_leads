import { useEffect, useMemo, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { ContractResponse } from '../../api/contractTypes'
import { SEAT_NAME, leaderSeat } from '../../lib/bridge'
import DealDiagram from '../../components/DealDiagram'
import { rankContracts } from './ranking'

type Bucket = 'makes' | 'fails'

interface Props {
  result: ContractResponse
  mode: Mode
  benchmark: string
}

/** Example layouts for one contract, split into the deals it makes and the
 * deals it goes down on — the sanity check behind the make %. */
export default function ContractSampleDeals({ result, mode, benchmark }: Props) {
  const [key, setKey] = useState<string | null>(null)
  const [bucket, setBucket] = useState<Bucket>('fails')
  const [limit, setLimit] = useState(6)

  const rows = useMemo(
    () => rankContracts(result, benchmark, mode), [result, benchmark, mode],
  )
  useEffect(() => { setKey(rows[0]?.best.key ?? null) }, [result])

  const candidate = result.candidates.find((c) => c.key === (key ?? rows[0]?.best.key))
  if (!candidate) return null

  const col = result.deals.candidates.indexOf(candidate.key)
  const deals = result.deals.records
    .map((rec, index) => ({ index, tricks: rec.tricks[col], score: rec.scores[col] }))
    .filter((d) => (bucket === 'makes'
      ? d.tricks >= candidate.tricks_needed
      : d.tricks < candidate.tricks_needed))
  const shown = deals.slice(0, limit)
  const declarer = candidate.declarer as Seat

  return (
    <section>
      <h2>Sample deals</h2>
      <div className="row">
        <label className="field">
          Contract
          <select value={candidate.key} onChange={(e) => setKey(e.target.value)}>
            {rows.map((r) => (
              <option key={r.best.key} value={r.best.key}>
                {r.best.label} by {SEAT_NAME[r.best.declarer as Seat]}
              </option>
            ))}
          </select>
        </label>
        <div className="seg">
          <button className={bucket === 'makes' ? 'on' : ''} onClick={() => setBucket('makes')}>
            Makes ({Math.round(candidate.make_rate * result.num_deals)})
          </button>
          <button className={bucket === 'fails' ? 'on' : ''} onClick={() => setBucket('fails')}>
            Fails ({result.num_deals - Math.round(candidate.make_rate * result.num_deals)})
          </button>
        </div>
      </div>

      {deals.length === 0 ? (
        <p className="caption">
          {candidate.label} never {bucket === 'fails' ? 'failed' : 'made'} in these{' '}
          {result.num_deals} deals.
        </p>
      ) : (
        <>
          <label className="inline-field">
            Max deals to show{' '}
            <input type="number" inputMode="numeric" min={1} max={deals.length} value={limit}
              onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))} />
          </label>
          <p className="caption">
            Showing {shown.length}{shown.length < deals.length ? ` of ${deals.length}` : ''} deal(s).
            Your hand ({SEAT_NAME[result.seat]}) is the same in every one.
          </p>
          <div className="deal-grid">
            {shown.map((d) => (
              <div key={d.index}>
                <DealDiagram
                  layout={result.deals.records[d.index].layout}
                  leader={leaderSeat(declarer)}
                  declarer={declarer}
                  level={candidate.level}
                  strain={candidate.strain}
                  declTricks={d.tricks}
                />
                <p className="caption tiny">
                  {d.tricks} tricks · {d.score >= 0 ? '+' : ''}{d.score}
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
