import { useMemo, useState } from 'react'
import type { Mode, Seat } from '../../api/types'
import type { ContractResponse } from '../../api/contractTypes'
import { SEAT_NAME, SUIT_COLOR } from '../../lib/bridge'
import { benchmarkOptions, rankContracts } from './ranking'

const TOP_N = 5

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
}

/** Ranked contracts, each measured against the benchmark contract. */
export default function ContractResults({ result, mode, benchmark, setBenchmark }: Props) {
  const [showAll, setShowAll] = useState(false)
  const rows = useMemo(
    () => rankContracts(result, benchmark, mode), [result, benchmark, mode],
  )
  const options = useMemo(() => benchmarkOptions(result), [result])
  const shown = showAll ? rows : rows.slice(0, TOP_N)
  const benchLabel = result.candidates.find((c) => c.key === benchmark)?.label ?? '—'
  const top = rows[0]
  const opps = result.opponents

  return (
    <section>
      <h2>Best contracts</h2>

      <div className="banner banner-info">
        {top && (top.isBenchmark
          ? <>Nothing beats <b>{benchLabel}</b> — that is the spot.</>
          : <>
              Best spot: <b>{top.best.label}</b> by {SEAT_NAME[top.best.declarer as Seat]},
              {' '}making {(top.best.make_rate * 100).toFixed(0)}% of the time
              {' '}({mode === 'matchpoints'
                ? `${top.metric.mpPct.toFixed(1)}% of matchpoints`
                : `${top.score >= 0 ? '+' : ''}${top.score.toFixed(2)} IMPs`} vs {benchLabel}).
            </>)}
      </div>

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
