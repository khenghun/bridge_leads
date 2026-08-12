import { useEffect, useMemo, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { SimulateResponse } from '../../api/leadTypes'
import {
  SEAT_NAME, SYMBOL_COLOR, criterionActive, dealMatches, defaultCriterion,
  describeCriterion, dummySeat, groupEquivalentLeads, leadGroupIndex,
  partnerSeat, strainLabel,
  type DealCriterion,
} from '../../lib/bridge'
import DealDiagram from '../../components/DealDiagram'
import DealFilterBar from '../../components/DealFilterBar'

interface Props {
  result: SimulateResponse
  mode: Mode
}

/** Clickable lead chips + 4-hand cross diagrams for deals the lead defeats,
 * browsed straight from the per-deal matrix (every simulated deal, not a
 * server-chosen sample) and narrowable by a hand-feature filter. One chip per
 * group of equivalent leads; the viewed lead tracks the recommended lead for
 * the active scoring mode and re-points on a mode flip or a new run. */
export default function SampleDeals({ result, mode }: Props) {
  const sortKey = mode === 'matchpoints' ? 'matchpoints' : 'imps'
  const groups = useMemo(() => groupEquivalentLeads(result.deals), [result])
  const byCard = useMemo(() => leadGroupIndex(groups), [groups])
  const labelOf = (card: string) => byCard.get(card)?.label ?? card
  // One chip per group; every lookup uses the group's representative card.
  const leads = result.leads.filter((r) => byCard.get(r.card)?.card === r.card)

  const leadOrder = [...leads].sort((a, b) => b[sortKey] - a[sortKey]).map((r) => r.card)
  const bestRaw = mode === 'matchpoints' ? result.best_mp : result.best_imp
  const recommended = (bestRaw && byCard.get(bestRaw)?.card) ?? bestRaw
  // Star every lead tied for best, using the same rounding as the banner in
  // ResultsTable so the starred set matches its "(n tied)" count.
  const ndp = mode === 'matchpoints' ? 1 : 2
  const round = (v: number) => Number(v.toFixed(ndp))
  const bestValue = Math.max(...leads.map((r) => round(r[sortKey])))
  const starred = new Set(
    leads.filter((r) => round(r[sortKey]) === bestValue).map((r) => r.card))
  const defeatByCard: Record<string, number> = Object.fromEntries(
    leads.map((r) => [r.card, r.defeat_rate]),
  )

  const { level, strain, declarer } = result.meta
  // The three hands the leader cannot see — what the filter can ask about.
  const filterSeats: Array<[Seat, string]> = [
    [declarer as Seat, 'declarer'],
    [dummySeat(declarer as Seat), 'dummy'],
    [partnerSeat(result.leader), 'your partner'],
  ]

  const [picked, setPicked] = useState<string | null>(recommended)
  const [limit, setLimit] = useState(10)
  const [criterion, setCriterion] = useState<DealCriterion>(
    () => defaultCriterion(filterSeats[0][0]))
  // Re-point at the recommendation on a new run or a mode flip; a new run also
  // resets the filter (its seats may have changed with the declarer).
  useEffect(() => { setPicked(recommended) }, [result, mode, recommended])
  useEffect(() => { setCriterion(defaultCriterion(result.meta.declarer)) }, [result])

  const chosen = picked && leadOrder.includes(picked) ? picked : recommended
  const col = chosen ? result.deals.cards.indexOf(chosen) : -1
  const tricksNeeded = 6 + level
  // Every deal this lead defeats, straight from the matrix.
  const defeats = useMemo(() => (col < 0 ? [] : result.deals.records
    .map((rec, index) => ({ index, declarer_tricks: rec.tricks[col] }))
    .filter((d) => d.declarer_tricks < tricksNeeded)), [result, col, tricksNeeded])
  const active = criterionActive(criterion)
  const deals = active
    ? defeats.filter((d) => dealMatches(result.deals.records[d.index].layout, criterion))
    : defeats

  const modeName = mode === 'matchpoints' ? 'Matchpoints' : 'IMPs'
  const shown = deals.slice(0, limit)

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
              {starred.has(card) ? '★ ' : ''}{labelOf(card)}
            </button>
          )
        })}
      </div>

      <DealFilterBar seats={filterSeats} criterion={criterion} setCriterion={setCriterion} />

      {deals.length === 0 ? (
        <p className="caption">
          {active
            ? `No deal matching the filter is defeated by ${chosen ? labelOf(chosen) : ''} `
              + `(filter matches ${describeCriterion(criterion)}).`
            : `No simulated deal was defeated by ${chosen ? labelOf(chosen) : ''}.`}
        </p>
      ) : (
        <>
          <label className="inline-field">
            Max deals to show{' '}
            <input
              type="number" inputMode="numeric" min={1} max={deals.length} value={limit}
              onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
          <p className="caption">
            Showing {shown.length}{shown.length < deals.length ? ` of ${deals.length}` : ''} deal(s)
            where <b>{chosen ? labelOf(chosen) : ''}</b> sets {level}{strainLabel(strain)} by{' '}
            {SEAT_NAME[declarer as Seat]}
            {active && <>
              {' '}— <b>filtered</b> ({SEAT_NAME[criterion.seat as Seat]}{' '}
              {describeCriterion(criterion)}; {deals.length} of {defeats.length} defeated deals,
              {' '}rankings above stay full-run)
            </>}.
          </p>
          <div className="deal-grid">
            {shown.map((d) => (
              <DealDiagram
                key={d.index}
                layout={result.deals.records[d.index].layout}
                leader={result.leader}
                declarer={declarer as Seat}
                level={level}
                strain={strain}
                declTricks={d.declarer_tricks}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
