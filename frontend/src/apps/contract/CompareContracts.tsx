import { useEffect, useMemo, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { CandidateResult, ContractResponse } from '../../api/contractTypes'
import {
  SEAT_NAME, SUIT_COLOR, compareCandidates, criterionActive, dealMatches,
  defaultCriterion, describeCriterion, leaderSeat,
  type CompareOutcome, type DealCriterion,
} from '../../lib/bridge'
import DealDiagram from '../../components/DealDiagram'
import DealFilterBar from '../../components/DealFilterBar'
import { contractFilterSeats } from './ContractSampleDeals'
import { rankContracts } from './ranking'

interface Props {
  result: ContractResponse
  mode: Mode
  benchmark: string
}

type Bucket = 'all' | CompareOutcome

function Label({ c }: { c: CandidateResult }) {
  const color = c.strain === 'N' ? undefined : SUIT_COLOR[c.strain as 'S' | 'H' | 'D' | 'C']
  return <b style={{ color }}>{c.label} by {c.declarer}</b>
}

/** Head-to-head comparison of two contracts across every simulated deal:
 * win/draw/lose counts, the mode's summary stat, and deal diagrams filtered by
 * outcome. Pure client-side over the `deals` matrix — no refetch. */
export default function CompareContracts({ result, mode, benchmark }: Props) {
  const [open, setOpen] = useState(false)
  const [a, setA] = useState<string | null>(null)
  const [b, setB] = useState<string | null>(null)
  const [bucket, setBucket] = useState<Bucket>('all')
  const [limit, setLimit] = useState(8)
  const [criterion, setCriterion] = useState<DealCriterion>(
    () => defaultCriterion(result.partner))

  const rows = useMemo(
    () => rankContracts(result, benchmark, mode), [result, benchmark, mode],
  )
  const byKey = useMemo(
    () => new Map(result.candidates.map((c) => [c.key, c])), [result],
  )

  // On a new run, compare the top contract with the benchmark it beat.
  useEffect(() => {
    setA(rows[0]?.best.key ?? null)
    setB(rows.find((r) => r.best.key !== rows[0]?.best.key)?.best.key ?? null)
    setBucket('all')
    setCriterion(defaultCriterion(result.partner))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  if (result.deals.candidates.length < 2) return null

  const options = rows.map((r) => r.best)

  const pick = (row: 'a' | 'b') => (key: string) => {
    if (row === 'a') {
      if (key === b) setB(a)
      setA(key)
    } else {
      if (key === a) setA(b)
      setB(key)
    }
  }

  const chipRow = (label: string, chosen: string | null, onPick: (key: string) => void) => (
    <div className="chips">
      <span className="caption" style={{ width: '5rem' }}>{label}</span>
      {options.map((c) => {
        const color = c.strain === 'N' ? undefined : SUIT_COLOR[c.strain as 'S' | 'H' | 'D' | 'C']
        const selected = c.key === chosen
        return (
          <button
            key={c.key}
            className={`chip${selected ? ' chip-selected' : ''}`}
            style={{ color, borderColor: selected && color ? color : undefined }}
            onClick={() => onPick(c.key)}
          >
            {c.label}
          </button>
        )
      })}
    </div>
  )

  const body = () => {
    if (!a || !b || a === b) return null
    const ca = byKey.get(a)
    const cb = byKey.get(b)
    if (!ca || !cb) return null
    const { rows: deals, summary } = compareCandidates(result.deals, a, b)
    if (summary.n === 0) return null

    const inBucket = bucket === 'all' ? deals : deals.filter((r) => r.outcome === bucket)
    const active = criterionActive(criterion)
    const filtered = active
      ? inBucket.filter((r) => dealMatches(result.deals.records[r.index].layout, criterion))
      : inBucket
    const shown = filtered.slice(0, limit)
    const stat = mode === 'imps'
      ? <>avg <b>{summary.avgImpSwing >= 0 ? '+' : ''}{summary.avgImpSwing.toFixed(3)} IMPs</b> per deal for <Label c={ca} /></>
      : <>head-to-head <b>{summary.mpPct.toFixed(2)} MP%</b> for <Label c={ca} /></>

    const buckets: [Bucket, string, number][] = [
      ['all', 'All', summary.n],
      ['win', 'Better', summary.win],
      ['draw', 'Same', summary.draw],
      ['lose', 'Worse', summary.lose],
    ]

    return (
      <>
        <div className="banner banner-info">
          <Label c={ca} /> vs <Label c={cb} /> over {summary.n} deals:{' '}
          <b>{summary.win}</b> better / <b>{summary.draw}</b> same / <b>{summary.lose}</b> worse
          {' — '}{stat}
        </div>
        <div className="seg">
          {buckets.map(([key, label, count]) => (
            <button key={key} className={bucket === key ? 'on' : ''} onClick={() => setBucket(key)}>
              {label} ({count})
            </button>
          ))}
        </div>
        <DealFilterBar seats={contractFilterSeats(result.seat)}
          criterion={criterion} setCriterion={setCriterion} />
        {filtered.length === 0 ? (
          <p className="caption">
            {active ? 'No deal in this bucket matches the filter.' : 'No deal in this bucket.'}
          </p>
        ) : (
          <>
            <label className="inline-field">
              Max deals to show{' '}
              <input
                type="number" inputMode="numeric" min={1} max={filtered.length} value={limit}
                onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
              />
            </label>
            <p className="caption">
              Showing {shown.length}{shown.length < filtered.length ? ` of ${filtered.length}` : ''} deal(s)
              {active && <>
                {' '}— <b>filtered</b> ({SEAT_NAME[criterion.seat as Seat]}{' '}
                {describeCriterion(criterion)}; {filtered.length} of {inBucket.length} in this
                bucket, counts above stay full-run)
              </>},
              with the tricks <Label c={ca} /> takes.
            </p>
            <div className="deal-grid">
              {shown.map((r) => (
                <div key={r.index}>
                  <DealDiagram
                    layout={result.deals.records[r.index].layout}
                    leader={leaderSeat(ca.declarer as Seat)}
                    declarer={ca.declarer as Seat}
                    level={ca.level}
                    strain={ca.strain}
                    declTricks={r.tricksA}
                  />
                  <p className="caption tiny">
                    {r.tricksA} tricks in {ca.label} by {SEAT_NAME[ca.declarer as Seat]}
                    {' vs '}{r.tricksB} in {cb.label} by {SEAT_NAME[cb.declarer as Seat]}
                    {mode === 'imps' && r.impSwing !== 0 && (
                      <> · {r.impSwing > 0 ? '+' : ''}{r.impSwing} IMPs</>
                    )}
                  </p>
                </div>
              ))}
            </div>
          </>
        )}
      </>
    )
  }

  return (
    <section>
      <h2>
        Compare two contracts{' '}
        <button className="btn btn-small" onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Compare'}
        </button>
      </h2>
      {open && (
        <>
          <p className="caption">Pick two contracts to compare deal-by-deal:</p>
          {chipRow('Contract A', a, pick('a'))}
          {chipRow('Contract B', b, pick('b'))}
          {body()}
        </>
      )}
    </section>
  )
}
