import { useMemo } from 'react'
import type { Mode } from '../../api/types'
import type { ContractResponse } from '../../api/contractTypes'
import { SUIT_COLOR, SUIT_SYMBOL } from '../../lib/bridge'
import { rankContracts } from './ranking'

const KINDS = [
  { kind: 'part', head: 'Partscore' },
  { kind: 'game', head: 'Game' },
  { kind: 'slam', head: 'Slam (6)' },
  { kind: 'grand', head: 'Grand (7)' },
] as const

const STRAINS = ['N', 'S', 'H', 'D', 'C']

function strainHead(strain: string) {
  if (strain === 'N') return <span>NT</span>
  const s = strain as 'S' | 'H' | 'D' | 'C'
  return <span style={{ color: SUIT_COLOR[s] }}>{SUIT_SYMBOL[s]}</span>
}

/** Green for better than the benchmark, red for worse; alpha by magnitude. */
function cellStyle(value: number, mode: Mode) {
  const centred = mode === 'matchpoints' ? (value - 50) / 50 : value / 6
  const clipped = Math.max(-1, Math.min(1, centred))
  const alpha = Math.abs(clipped) * 0.55
  const hue = clipped >= 0 ? '39, 174, 96' : '231, 76, 60'
  return { background: `rgba(${hue}, ${alpha.toFixed(2)})` }
}

interface Props {
  result: ContractResponse
  mode: Mode
  benchmark: string
}

/** Strain x decision-level grid of the active metric — the at-a-glance view of
 * where the hands belong. */
export default function StrainGrid({ result, mode, benchmark }: Props) {
  const rows = useMemo(
    () => rankContracts(result, benchmark, mode), [result, benchmark, mode],
  )
  const byCell = new Map(rows.map((r) => [`${r.best.strain}-${r.best.kind}`, r]))
  const strains = STRAINS.filter((s) => result.candidates.some((c) => c.strain === s))
  const best = rows[0]?.best.key

  return (
    <section>
      <h2>Every contract at a glance</h2>
      <p className="caption">
        {mode === 'matchpoints' ? 'Matchpoints' : 'IMPs'} against the benchmark,
        for the better declarer. Make % in small type.
      </p>
      <div className="grid-scroll">
        <table className="grid-heat">
          <thead>
            <tr>
              <th></th>
              {KINDS.map((k) => <th key={k.kind}>{k.head}</th>)}
            </tr>
          </thead>
          <tbody>
            {strains.map((strain) => (
              <tr key={strain}>
                <th>{strainHead(strain)}</th>
                {KINDS.map((k) => {
                  const cell = byCell.get(`${strain}-${k.kind}`)
                  if (!cell) return <td key={k.kind}>—</td>
                  const value = cell.score
                  return (
                    <td key={k.kind} style={cellStyle(value, mode)}
                      className={cell.best.key === best ? 'cell-best' : ''}>
                      <div className="mono">
                        {mode === 'matchpoints'
                          ? `${value.toFixed(0)}%`
                          : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`}
                      </div>
                      <div className="caption tiny">
                        {cell.best.label} · {(cell.best.make_rate * 100).toFixed(0)}%
                        {' '}by {cell.best.declarer}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
