import { useEffect, useMemo, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { SimulateResponse } from '../../api/leadTypes'
import {
  SEAT_NAME, SYMBOL_COLOR, compareLeads, criterionActive, dealMatches,
  defaultCriterion, describeCriterion, dummySeat, groupEquivalentLeads,
  leadGroupIndex, partnerSeat,
  type CompareOutcome, type DealCriterion,
} from '../../lib/bridge'
import DealDiagram from '../../components/DealDiagram'
import DealFilterBar from '../../components/DealFilterBar'

interface Props {
  result: SimulateResponse
  mode: Mode
}

type Bucket = 'all' | CompareOutcome

/** A candidate-lead card rendered in its suit colour. `label` widens it to a
 * group of equivalent leads ('♦T9') while `card` stays the lookup key. */
function Card({ card, label }: { card: string; label?: string }) {
  return <b style={{ color: SYMBOL_COLOR[card[0]] }}>{label ?? card}</b>
}

/** Head-to-head comparison of two candidate leads across every simulated deal:
 * win/draw/lose counts (mode-independent), the mode's summary stat, and the
 * deal diagrams filtered by outcome. One chip per group of equivalent leads —
 * comparing two members of a group would be an all-draw comparison by
 * construction. Pure client-side over the `deals` matrix from the simulate
 * response — no refetch, same pattern as the MP/IMP toggle. */
export default function CompareLeads({ result, mode }: Props) {
  const [open, setOpen] = useState(false)
  const [a, setA] = useState<string | null>(null)
  const [b, setB] = useState<string | null>(null)
  const [bucket, setBucket] = useState<Bucket>('all')
  const [limit, setLimit] = useState(10)
  const [criterion, setCriterion] = useState<DealCriterion>(
    () => defaultCriterion(result.meta.declarer))

  const sortKey = mode === 'matchpoints' ? 'matchpoints' : 'imps'
  const groups = useMemo(() => groupEquivalentLeads(result.deals), [result])
  const byCard = useMemo(() => leadGroupIndex(groups), [groups])
  const labelOf = (card: string) => byCard.get(card)?.label ?? card
  const leads = result.leads.filter((l) => byCard.get(l.card)?.card === l.card)

  // On a new run, default A to the best lead by the active metric and B to the
  // best lead whose aggregate numbers differ (distinct groups can still tie on
  // the rounded aggregates). No reset on a mode flip — win/draw/lose counts are
  // the same in both modes.
  useEffect(() => {
    const order = [...leads].sort((x, y) => y[sortKey] - x[sortKey])
    const top = order[0]
    const rival = order.find(
      (l) => l !== top && (l.imps !== top.imps || l.matchpoints !== top.matchpoints),
    ) ?? order[1]
    setA(top?.card ?? null)
    setB(rival?.card ?? null)
    setBucket('all')
    setCriterion(defaultCriterion(result.meta.declarer))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  if ((result.deals?.cards.length ?? 0) < 2 || groups.length < 2) return null
  // Chips in the same order as the results table: best first by the active metric.
  const cards = [...leads].sort((x, y) => y[sortKey] - x[sortKey]).map((l) => l.card)

  const pick = (row: 'a' | 'b') => (card: string) => {
    if (row === 'a') {
      if (card === b) setB(a) // swap instead of allowing A === B
      setA(card)
    } else {
      if (card === a) setA(b)
      setB(card)
    }
  }

  const chipRow = (label: string, chosen: string | null, onPick: (card: string) => void) => (
    <div className="chips">
      <span className="caption" style={{ width: '3.5rem' }}>{label}</span>
      {cards.map((card) => {
        const color = SYMBOL_COLOR[card[0]]
        const selected = card === chosen
        return (
          <button
            key={card}
            className={`chip${selected ? ' chip-selected' : ''}`}
            style={{ color, borderColor: selected ? color : undefined }}
            onClick={() => onPick(card)}
          >
            {labelOf(card)}
          </button>
        )
      })}
    </div>
  )

  const body = () => {
    if (!a || !b || a === b) return null
    const { rows, summary } = compareLeads(result.deals, a, b)
    if (summary.n === 0) return null

    const inBucket = bucket === 'all' ? rows : rows.filter((r) => r.outcome === bucket)
    const active = criterionActive(criterion)
    const filtered = active
      ? inBucket.filter((r) => dealMatches(result.deals.records[r.index].layout, criterion))
      : inBucket
    const shown = filtered.slice(0, limit)
    const { level, strain, declarer } = result.meta
    const filterSeats: Array<[Seat, string]> = [
      [declarer as Seat, 'declarer'],
      [dummySeat(declarer as Seat), 'dummy'],
      [partnerSeat(result.leader), 'your partner'],
    ]
    const stat = mode === 'imps'
      ? <>avg <b>{summary.avgImpSwing >= 0 ? '+' : ''}{summary.avgImpSwing.toFixed(3)} IMPs</b> per deal for <Card card={a} label={labelOf(a)} /></>
      : <>head-to-head <b>{summary.mpPct.toFixed(2)} MP%</b> for <Card card={a} label={labelOf(a)} /></>

    const buckets: [Bucket, string, number][] = [
      ['all', 'All', summary.n],
      ['win', 'Win', summary.win],
      ['draw', 'Draw', summary.draw],
      ['lose', 'Lose', summary.lose],
    ]

    return (
      <>
        <div className="banner banner-info">
          <Card card={a} label={labelOf(a)} /> vs <Card card={b} label={labelOf(b)} /> over {summary.n} deals:{' '}
          <b>{summary.win}</b> win / <b>{summary.draw}</b> draw / <b>{summary.lose}</b> lose
          {' — '}{stat}
        </div>
        <p className="caption">
          Win/draw/lose is per deal, from <Card card={a} label={labelOf(a)} />&apos;s side; the counts are the
          same at Matchpoints and IMPs.
        </p>
        <div className="seg">
          {buckets.map(([key, label, count]) => (
            <button key={key} className={bucket === key ? 'on' : ''} onClick={() => setBucket(key)}>
              {label} ({count})
            </button>
          ))}
        </div>
        <DealFilterBar seats={filterSeats} criterion={criterion} setCriterion={setCriterion} />
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
              </>}.
              Diagrams show declarer&apos;s tricks when <Card card={a} label={labelOf(a)} /> is led.
            </p>
            <div className="deal-grid">
              {shown.map((r) => (
                <div key={r.index}>
                  <DealDiagram
                    layout={result.deals.records[r.index].layout}
                    leader={result.leader}
                    declarer={declarer as Seat}
                    level={level}
                    strain={strain}
                    declTricks={r.tricksA}
                  />
                  <p className="caption tiny">
                    decl {r.tricksA} with <Card card={a} label={labelOf(a)} /> vs {r.tricksB} with <Card card={b} label={labelOf(b)} />
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
        Compare leads{' '}
        <button className="btn btn-small" onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Compare'}
        </button>
      </h2>
      {open && (
        <>
          <p className="caption">Pick two leads to compare deal-by-deal:</p>
          {chipRow('Lead A', a, pick('a'))}
          {chipRow('Lead B', b, pick('b'))}
          {body()}
        </>
      )}
    </section>
  )
}
