import { useMemo, type ReactNode } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { SimulateResponse } from '../../api/leadTypes'
import {
  SEAT_NAME, SYMBOL_COLOR, groupEquivalentLeads, leadGroupIndex,
  leadMetricDiffs, pairedMarginStats, strainLabel,
} from '../../lib/bridge'
import CopyLinkButton from '../../components/CopyLinkButton'

export const LEAD_DEALS_CAP = 1000

interface Props {
  result: SimulateResponse
  mode: Mode
  /** Re-run the identical request with more deals (the too-close escape hatch). */
  onRerun?: (numDeals: number) => void
  /** Scenario recap, rendered between the conclusion card and the table. */
  recap?: ReactNode
  /** Share link for this result (built at click time from the frozen request). */
  shareUrl?: () => string
}

/** Conclusion card (the answer, with its margin and sampling error), scenario
 * recap, and the ranked lead table — one row per group of equivalent leads
 * (same suit, identical tricks on every deal, e.g. ♦T9 touching cards).
 * Metrics are identical across a group's members, so each row shows its
 * representative's numbers under the combined label. */
export default function ResultsTable({ result, mode, onRerun, recap, shareUrl }: Props) {
  const sortKey = mode === 'matchpoints' ? 'matchpoints' : 'imps'
  const ndp = mode === 'matchpoints' ? 1 : 2
  const round = (v: number, d: number) => Number(v.toFixed(d))

  const groups = useMemo(() => groupEquivalentLeads(result.deals), [result])
  const byCard = useMemo(() => leadGroupIndex(groups), [groups])
  // One row per group: keep only each group's representative lead.
  const leads = result.leads.filter((r) => byCard.get(r.card)?.card === r.card)
  const labelOf = (card: string) => byCard.get(card)?.label ?? card

  const bestValue = Math.max(...leads.map((r) => round(r[sortKey], ndp)))
  const tied = leads
    .filter((r) => round(r[sortKey], ndp) === bestValue)
    .sort((a, b) => a.declarer_tricks - b.declarer_tricks)
  const bestCards = new Set(tied.map((r) => r.card))

  // Rank by the active scoring metric (best lead first); fewer declarer
  // tricks breaks ties.
  const rows = [...leads].sort(
    (a, b) => b[sortKey] - a[sortKey] || a.declarer_tricks - b.declarer_tricks)

  // Margin of the recommendation over the next-best *distinct* lead, with its
  // sampling error — computed pairwise per deal, so it is exactly the
  // difference of the two table rows plus an honest ± on it.
  const top = rows[0]
  const runnerUp = rows.find((r) => !bestCards.has(r.card))
  const stats = useMemo(
    () => (runnerUp
      ? pairedMarginStats(leadMetricDiffs(result.deals, top.card, runnerUp.card, mode))
      : null),
    [result, mode, top?.card, runnerUp?.card],
  )

  const metricStr = mode === 'matchpoints'
    ? `${bestValue.toFixed(1)} MP%`
    : `${bestValue >= 0 ? '+' : ''}${bestValue.toFixed(2)} IMPs`
  const defeats = [...new Set(tied.map((r) => Math.round(r.defeat_rate * 100)))].sort((a, b) => a - b)
  const defeatStr = defeats.length === 1
    ? `defeats the contract ${defeats[0]}%`
    : `defeats the contract ${defeats[0]}–${defeats[defeats.length - 1]}%`
  const cardsStr = tied.map((r) => labelOf(r.card)).join(' / ')

  const unit = mode === 'matchpoints' ? 'MP%' : 'IMPs'
  const mdp = mode === 'matchpoints' ? 1 : 2
  const { level, strain, declarer } = result.meta
  const canRerun = onRerun && result.num_simulations < LEAD_DEALS_CAP

  return (
    <section>
      <div className="conclusion">
        <p className="headline">
          {tied.length === 1 ? 'Lead' : `Lead (${tied.length} tied)`}{' '}
          {tied.map((r, i) => (
            <span key={r.card}>
              {i > 0 && ' / '}
              <b style={{ color: SYMBOL_COLOR[r.card[0]] }}>{labelOf(r.card)}</b>
            </span>
          ))}
          {' '}<span className="caption">
            vs {level}{strainLabel(strain)} by {SEAT_NAME[declarer as Seat]}
          </span>
          {shareUrl && <span style={{ float: 'right' }}><CopyLinkButton getUrl={shareUrl} /></span>}
        </p>
        <p className="margin-line">
          {metricStr} · {defeatStr} · {result.num_simulations} deals
        </p>
        {stats && runnerUp && (
          <p className="margin-line">
            {stats.tooClose ? (
              <>
                ⚖ <b>Too close to call</b> at {stats.n} deals — the{' '}
                {Math.abs(stats.margin).toFixed(mdp)} {unit} gap over{' '}
                <b style={{ color: SYMBOL_COLOR[runnerUp.card[0]] }}>{labelOf(runnerUp.card)}</b>{' '}
                is within sampling noise (±{stats.sem.toFixed(mdp)}).
              </>
            ) : (
              <>
                Margin over next best{' '}
                <b style={{ color: SYMBOL_COLOR[runnerUp.card[0]] }}>{labelOf(runnerUp.card)}</b>:{' '}
                {stats.margin >= 0 ? '+' : ''}{stats.margin.toFixed(mdp)} ±{stats.sem.toFixed(mdp)} {unit}.
              </>
            )}
            {stats.tooClose && canRerun && (
              <button className="btn btn-small" onClick={() => onRerun(LEAD_DEALS_CAP)}>
                Re-run with {LEAD_DEALS_CAP} deals
              </button>
            )}
          </p>
        )}
      </div>

      {recap}

      <div className="table-scroll">
      <table className="results">
        <thead>
          <tr>
            <th>Lead</th>
            <th title="Average tricks taken by declarer's side (lower is better for the defense).">
              Decl. tricks
            </th>
            <th title="Share of simulated deals where this lead beats the contract.">Defeat %</th>
            <th>MP%</th>
            <th>IMPs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.card} className={bestCards.has(r.card) ? 'row-best' : ''}>
              <td style={{ color: SYMBOL_COLOR[r.card[0]], fontWeight: 600 }}>{labelOf(r.card)}</td>
              <td>{r.declarer_tricks.toFixed(2)}</td>
              <td>{(r.defeat_rate * 100).toFixed(1)}%</td>
              <td>{r.matchpoints.toFixed(2)}</td>
              <td>{r.imps >= 0 ? '+' : ''}{r.imps.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {/* The column meanings are also `title` tooltips, which touch devices
          cannot reach — so state them in text as well. */}
      <p className="caption tiny">
        A row like <b>♦T9</b> is two equivalent leads — no simulated deal told
        them apart. <b>Decl. tricks</b>: average tricks declarer takes, so lower
        is better for you. <b>Defeat %</b>: how often this lead beats the
        contract. <b>MP%</b> and <b>IMPs</b>: the two scoring modes — the table
        is ranked by whichever is selected, best first.
      </p>
    </section>
  )
}
