import { useEffect, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { SimulateResponse } from '../../api/leadTypes'
import { SEAT_NAME, SYMBOL_COLOR, strainLabel } from '../../lib/bridge'
import DealDiagram from '../../components/DealDiagram'

const SAMPLE_CAP = 100

interface Props {
  result: SimulateResponse
  mode: Mode
}

/** Clickable lead chips + 4-hand cross diagrams for deals the lead defeats.
 * The viewed lead tracks the recommended lead for the active scoring mode, and
 * re-points on a mode flip or a new run — matching the old Streamlit behaviour. */
export default function SampleDeals({ result, mode }: Props) {
  const sortKey = mode === 'matchpoints' ? 'matchpoints' : 'imps'
  const leadOrder = [...result.leads].sort((a, b) => b[sortKey] - a[sortKey]).map((r) => r.card)
  const recommended = mode === 'matchpoints' ? result.best_mp : result.best_imp
  // Star every lead tied for best, using the same rounding as the banner in
  // ResultsTable so the starred set matches its "(n tied)" count.
  const ndp = mode === 'matchpoints' ? 1 : 2
  const round = (v: number) => Number(v.toFixed(ndp))
  const bestValue = Math.max(...result.leads.map((r) => round(r[sortKey])))
  const starred = new Set(
    result.leads.filter((r) => round(r[sortKey]) === bestValue).map((r) => r.card))
  const defeatByCard: Record<string, number> = Object.fromEntries(
    result.leads.map((r) => [r.card, r.defeat_rate]),
  )

  const [picked, setPicked] = useState<string | null>(recommended)
  const [limit, setLimit] = useState(10)
  // Re-point at the recommendation on a new run or a mode flip.
  useEffect(() => { setPicked(recommended) }, [result, mode, recommended])

  const chosen = picked && leadOrder.includes(picked) ? picked : recommended
  const deals = (chosen && result.samples[chosen]) || []
  const { level, strain, declarer } = result.meta
  const modeName = mode === 'matchpoints' ? 'Matchpoints' : 'IMPs'

  const shown = deals.slice(0, limit)
  const capNote = deals.length === SAMPLE_CAP ? ` (collection caps at ${SAMPLE_CAP})` : ''

  return (
    <section>
      <h2>Sample deals</h2>
      <p className="caption">
        Click a lead to see deals where it defeats the contract (★ = recommended for {modeName}):
      </p>
      <div className="chips">
        {leadOrder.map((card) => {
          const color = SYMBOL_COLOR[card[0]]
          const selected = card === chosen
          return (
            <button
              key={card}
              className={`chip${selected ? ' chip-selected' : ''}`}
              style={{ color, borderColor: selected ? color : undefined }}
              onClick={() => setPicked(card)}
              title={`defeats ${Math.round(defeatByCard[card] * 100)}%`}
            >
              {starred.has(card) ? '★ ' : ''}{card}
            </button>
          )
        })}
      </div>

      {deals.length === 0 ? (
        <p className="caption">No simulated deal was defeated by {chosen}.</p>
      ) : (
        <>
          <label className="inline-field">
            Max deals to show{' '}
            <input
              type="number" inputMode="numeric" min={1} max={SAMPLE_CAP} value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(SAMPLE_CAP, Number(e.target.value) || 1)))}
            />
          </label>
          <p className="caption">
            Showing {shown.length}{shown.length < deals.length ? ` of ${deals.length}` : ''} deal(s)
            where <b>{chosen}</b> sets {level}{strainLabel(strain)} by {SEAT_NAME[declarer as Seat]}
            {capNote}.
          </p>
          <div className="deal-grid">
            {shown.map((s, i) => (
              <DealDiagram
                key={i}
                layout={s.layout}
                leader={result.leader}
                declarer={declarer as Seat}
                level={level}
                strain={strain}
                declTricks={s.declarer_tricks}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
