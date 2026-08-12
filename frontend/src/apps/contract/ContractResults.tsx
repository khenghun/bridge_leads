import { useMemo, useState, type ReactNode } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { ContractResponse } from '../../api/contractTypes'
import {
  SEAT_NAME, SUIT_COLOR, benchmarkMetricDiffs, pairedMarginStats,
} from '../../lib/bridge'
import CopyLinkButton from '../../components/CopyLinkButton'
import { benchmarkOptions, rankContracts } from './ranking'

const TOP_N = 5
export const CONTRACT_DEALS_CAP = 500

/** Colour a contract label by its strain ('4♠', '♠ partscore', '3NT'). */
function contractColor(strain: string): string | undefined {
  if (strain === 'N') return undefined
  return SUIT_COLOR[strain as 'S' | 'H' | 'D' | 'C']
}

interface Props {
  result: ContractResponse
  mode: Mode
  benchmark: string
  setBenchmark: (key: string) => void
  /** Re-run the identical request with more deals (the too-close escape hatch). */
  onRerun?: (numDeals: number) => void
  /** Scenario recap, rendered between the conclusion card and the table. */
  recap?: ReactNode
  /** Share link for this result (built at click time from the frozen request). */
  shareUrl?: () => string
}

/** Conclusion card + ranked contracts, each measured against the benchmark. */
export default function ContractResults({
  result, mode, benchmark, setBenchmark, onRerun, recap, shareUrl,
}: Props) {
  const [showAll, setShowAll] = useState(false)
  const rows = useMemo(
    () => rankContracts(result, benchmark, mode), [result, benchmark, mode],
  )
  const options = useMemo(() => benchmarkOptions(result), [result])
  const shown = showAll ? rows : rows.slice(0, TOP_N)
  const benchLabel = result.candidates.find((c) => c.key === benchmark)?.label ?? '—'
  const top = rows[0]
  const opps = result.opponents

  // The margin behind the headline, with its sampling error. When the top row
  // IS the benchmark, the question becomes "does the runner-up really trail?".
  const rival = top?.isBenchmark ? rows[1] : undefined
  const stats = useMemo(() => {
    if (!top) return null
    const [a, b] = top.isBenchmark
      ? (rival ? [benchmark, rival.best.key] : [null, null])
      : [top.best.key, benchmark]
    if (!a || !b) return null
    return pairedMarginStats(benchmarkMetricDiffs(result.deals, a, b, benchmark, mode))
  }, [result, mode, benchmark, top, rival])

  const unit = mode === 'matchpoints' ? 'MP%' : 'IMPs'
  const mdp = mode === 'matchpoints' ? 1 : 2
  const canRerun = onRerun && result.num_deals < CONTRACT_DEALS_CAP
  const rivalRow = top?.isBenchmark ? rival : top
  const rerunButton = canRerun && (
    <button className="btn btn-small" onClick={() => onRerun(CONTRACT_DEALS_CAP)}>
      Re-run with {CONTRACT_DEALS_CAP} deals
    </button>
  )

  return (
    <section>
      <h2>Best contracts</h2>

      {top && (
        <div className="conclusion">
          <p className="headline">
            {top.isBenchmark ? (
              <>Stay in{' '}
                <b style={{ color: contractColor(top.best.strain) }}>{top.best.label}</b>
                {' '}<span className="caption">by {SEAT_NAME[top.best.declarer as Seat]}</span>
              </>
            ) : (
              <>Bid{' '}
                <b style={{ color: contractColor(top.best.strain) }}>{top.best.label}</b>
                {' '}<span className="caption">
                  by {SEAT_NAME[top.best.declarer as Seat]}, instead of {benchLabel}
                </span>
              </>
            )}
            {shareUrl && <span style={{ float: 'right' }}><CopyLinkButton getUrl={shareUrl} /></span>}
          </p>
          <p className="margin-line">
            makes {(top.best.make_rate * 100).toFixed(0)}% ·{' '}
            {top.best.mean_tricks.toFixed(1)} of {top.best.tricks_needed} tricks ·{' '}
            {result.num_deals} deals
            {top.seatMatters && <> · ⚠ play it from {SEAT_NAME[top.best.declarer as Seat]}</>}
            {top.thinEdge && <> · ⚠ thin edge</>}
          </p>
          {stats && rivalRow && (
            <p className="margin-line">
              {stats.tooClose ? (
                <>
                  ⚖ <b>Too close to call</b> at {stats.n} deals —{' '}
                  {top.isBenchmark
                    ? <>{benchLabel} vs <b>{rivalRow.best.label}</b></>
                    : <><b>{rivalRow.best.label}</b> vs {benchLabel}</>}
                  {' '}differ by {Math.abs(stats.margin).toFixed(mdp)} {unit}, within
                  sampling noise (±{stats.sem.toFixed(mdp)}).
                </>
              ) : top.isBenchmark ? (
                <>
                  Next best <b>{rivalRow.best.label}</b> trails by{' '}
                  {Math.abs(stats.margin).toFixed(mdp)} ±{stats.sem.toFixed(mdp)} {unit}.
                </>
              ) : (
                <>
                  Worth {stats.margin >= 0 ? '+' : ''}{stats.margin.toFixed(mdp)}{' '}
                  ±{stats.sem.toFixed(mdp)} {unit} over {benchLabel}
                  {mode === 'matchpoints' && ' (0 = coin flip)'}.
                </>
              )}
              {stats.tooClose && rerunButton}
            </p>
          )}
        </div>
      )}

      {recap}

      <div className="row">
        <label className="field">
          Compare against (defaults to the highest expected score; set it to the
          contract you'd otherwise be in)
          <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
            {options.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label} by {SEAT_NAME[c.declarer as Seat]}
              </option>
            ))}
          </select>
        </label>
        <p className="caption">
          {result.num_deals} deals · opponents make a game on{' '}
          <b>{(opps.opps_game_rate * 100).toFixed(0)}%</b>
          {opps.par_competitive_rate !== null && <>
            {' '}· par is theirs or a save on{' '}
            <b>{(opps.par_competitive_rate * 100).toFixed(0)}%</b>
          </>}
        </p>
      </div>

      <div className="table-scroll">
      <table className="results">
        <thead>
          <tr>
            <th>#</th>
            <th>Contract</th>
            <th>By</th>
            <th>Make %</th>
            <th>Tricks</th>
            <th>{mode === 'matchpoints' ? `MP% vs ${benchLabel}` : `IMPs vs ${benchLabel}`}</th>
            <th>Mean score</th>
            <th>When it fails</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={r.best.key} className={i === 0 && !r.isBenchmark ? 'row-best' : ''}>
              <td>{i + 1}</td>
              <td style={{ color: contractColor(r.best.strain), fontWeight: 700 }}>
                {r.best.label}
                {r.isBenchmark && <span className="tag"> baseline</span>}
              </td>
              <td>{r.best.declarer}</td>
              <td>{(r.best.make_rate * 100).toFixed(0)}%</td>
              <td className="mono">
                {r.best.mean_tricks.toFixed(1)} / {r.best.tricks_needed}
              </td>
              <td className="mono">
                {mode === 'matchpoints'
                  ? `${r.metric.mpPct.toFixed(1)}%`
                  : `${r.metric.imps >= 0 ? '+' : ''}${r.metric.imps.toFixed(2)}`}
              </td>
              <td className="mono">{Math.round(r.best.mean_score)}</td>
              <td className="mono">
                {r.best.fail_mean_score === null
                  ? '—'
                  : Math.round(r.best.fail_mean_score)}
              </td>
              <td className="caption tiny">
                {r.seatMatters && (
                  <span title={`${r.best.seat_delta.toFixed(1)} more tricks than by ${r.alt.declarer}`}>
                    ⚠ play it from {SEAT_NAME[r.best.declarer as Seat]}{' '}
                  </span>
                )}
                {r.thinEdge && (
                  <span title="Most of the gain comes from a handful of lucky layouts">
                    ⚠ thin edge
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      {rows.length > TOP_N && (
        <button className="btn btn-small" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show top 5' : `Show all ${rows.length} contracts`}
        </button>
      )}

      {/* Both flags are explained here as well as in a `title`, which touch
          devices cannot reach — and "thin edge" is the caveat that most needs
          saying. */}
      <p className="caption tiny">
        <b>⚠ play it from X</b>: that hand averages at least 0.3 more tricks, so
        the contract is worth playing from its side. <b>⚠ thin edge</b>: most of
        the gain comes from the luckiest 15% of deals, so the advantage is less
        solid than the number suggests.
      </p>
      <p className="caption tiny">
        One row per contract — every partscore level in a strain scores the same
        undoubled, so they are a single decision ("{'♠'} partscore"), and each row
        is shown for whichever hand declares better. Double-dummy assumes perfect
        play by everyone and no competition from the opponents: read a thin slam's
        make % with that in mind.
      </p>
    </section>
  )
}
