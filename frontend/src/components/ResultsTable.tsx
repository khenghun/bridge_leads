import type { Mode, SimulateResponse } from '../api/types'
import { SYMBOL_COLOR } from '../lib/bridge'

interface Props {
  result: SimulateResponse
  mode: Mode
}

/** Recommendation banner + ranked lead table (sorted by declarer tricks). */
export default function ResultsTable({ result, mode }: Props) {
  const sortKey = mode === 'matchpoints' ? 'matchpoints' : 'imps'
  const ndp = mode === 'matchpoints' ? 1 : 2
  const round = (v: number, d: number) => Number(v.toFixed(d))

  const bestValue = Math.max(...result.leads.map((r) => round(r[sortKey], ndp)))
  const tied = result.leads
    .filter((r) => round(r[sortKey], ndp) === bestValue)
    .sort((a, b) => a.declarer_tricks - b.declarer_tricks)
  const bestCards = new Set(tied.map((r) => r.card))

  const metricStr = mode === 'matchpoints'
    ? `${bestValue.toFixed(1)} MP%`
    : `${bestValue >= 0 ? '+' : ''}${bestValue.toFixed(2)} IMPs`
  const defeats = [...new Set(tied.map((r) => Math.round(r.defeat_rate * 100)))].sort((a, b) => a - b)
  const defeatStr = defeats.length === 1
    ? `defeats ${defeats[0]}%`
    : `defeats ${defeats[0]}–${defeats[defeats.length - 1]}%`
  const cardsStr = tied.map((r) => r.card).join(' / ')
  const label = tied.length === 1 ? 'Recommended lead' : `Recommended leads (${tied.length} tied)`

  // Rank by the active scoring metric (best lead first); fewer declarer
  // tricks breaks ties.
  const rows = [...result.leads].sort(
    (a, b) => b[sortKey] - a[sortKey] || a.declarer_tricks - b.declarer_tricks)

  return (
    <section>
      <div className="banner banner-success">
        {label}: <b>{cardsStr}</b> · {metricStr} · {defeatStr} ({result.num_simulations} deals)
      </div>
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
              <td style={{ color: SYMBOL_COLOR[r.card[0]], fontWeight: 600 }}>{r.card}</td>
              <td>{r.declarer_tricks.toFixed(2)}</td>
              <td>{(r.defeat_rate * 100).toFixed(1)}%</td>
              <td>{r.matchpoints.toFixed(2)}</td>
              <td>{r.imps >= 0 ? '+' : ''}{r.imps.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
