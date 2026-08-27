/**
 * AnalysisPanel — the graded decisions, ported from
 * bridge_ai/src/components/AnalysisPanel.jsx (minus its AI review modal).
 *
 * One row per decision the graded seat made. Clicking a row jumps the viewer
 * to the moment that card was played and expands the sub-table of every legal
 * card at that point, ranked by expected tricks.
 */
import { Fragment, useState } from 'react'
import type { Suit } from '../../api/types'
import type { AnalyzeResponse, CardOption, Decision, DecisionStatus } from '../../api/playTypes'
import { SUIT_COLOR, SUIT_SYMBOL } from '../../lib/bridge'

export const STATUS_COLOR: Record<string, string> = {
  optimal: 'var(--status-optimal)',
  good: 'var(--status-good)',
  suboptimal: 'var(--status-suboptimal)',
  forced: 'var(--muted)',
}

export const STATUS_LABEL: Record<string, string> = {
  optimal: '✓ optimal',
  good: '~ good',
  suboptimal: '✗ suboptimal',
  forced: 'forced',
}

/** Index the decisions by the card played, for the table's per-card tooltips. */
export function buildAnalysisMap(decisions: Decision[]): Map<string, Decision> {
  const map = new Map<string, Decision>()
  for (const d of decisions) map.set(d.card, d)
  return map
}

function CardText({ card }: { card: string }) {
  if (!card || card.length < 2) return <span>{card}</span>
  const suit = card[0] as Suit
  return (
    <span className="font-mono font-bold" style={{ color: SUIT_COLOR[suit] ?? 'var(--text)' }}>
      {SUIT_SYMBOL[suit] ?? suit}{card.slice(1)}
    </span>
  )
}

function StatusBadge({ status }: { status: DecisionStatus }) {
  return (
    <span className="play-badge" style={{ color: STATUS_COLOR[status] ?? 'var(--muted)' }}>
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

/** Every legal card at one decision, best first. */
function Options({ options, played }: { options: CardOption[]; played: string }) {
  if (!options.length) return null
  const best = options.reduce((m, o) => Math.max(m, o.tricks), options[0].tricks)
  return (
    <tr>
      <td colSpan={5} style={{ padding: 0, borderBottom: '1px solid var(--border)' }}>
        <div
          className="my-1 rounded-lg overflow-hidden"
          style={{ background: 'var(--panel-2)', borderLeft: '2px solid var(--accent)' }}
        >
          <div className="px-3 pt-2 pb-1 text-[0.62rem] uppercase tracking-widest font-semibold"
            style={{ color: 'var(--muted)' }}>
            All options
          </div>
          <table className="play-options">
            <thead>
              <tr>
                <th>#</th>
                <th>Card</th>
                <th title="Mean tricks for the graded side">Tricks</th>
                <th title="Make rate for declarer, defeat rate for a defender">Success</th>
                <th title="Expected tricks against the best card">vs best</th>
              </tr>
            </thead>
            <tbody>
              {options.map((o, i) => {
                const diff = o.tricks - best
                const isPlayed = o.card === played
                const isBest = Math.abs(diff) < 0.005
                return (
                  <tr key={o.card} className={isPlayed ? 'played' : undefined}>
                    <td style={{ color: 'var(--muted)' }}>{i + 1}</td>
                    <td>
                      <CardText card={o.card} />
                      {isPlayed && <span className="ml-1.5 text-[0.62rem]" style={{ color: 'var(--muted)' }}>played</span>}
                      {isBest && !isPlayed && (
                        <span className="ml-1.5 text-[0.62rem]" style={{ color: 'var(--status-optimal)' }}>best</span>
                      )}
                    </td>
                    <td className="tabular-nums">{o.tricks.toFixed(2)}</td>
                    <td className="tabular-nums" style={{ color: 'var(--muted)' }}>
                      {Number.isFinite(o.success_rate) ? `${(o.success_rate * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td
                      className="tabular-nums"
                      style={{
                        color: diff < -0.3 ? 'var(--status-suboptimal)'
                          : diff < -0.01 ? 'var(--status-good)' : 'var(--status-optimal)',
                      }}
                    >
                      {diff >= -0.005 ? '—' : diff.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  )
}

interface Props {
  result: AnalyzeResponse | null
  loading: boolean
  error: string | null
  /** Jump the viewer to the card this decision played. */
  onSelect: (decision: Decision) => void
  /** Index into `result.decisions` currently highlighted, or null. */
  selected: number | null
}

export default function AnalysisPanel({ result, loading, error, onSelect, selected }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (loading) {
    return (
      <div className="play-panel">
        <h2 className="play-panel-title">Analysis</h2>
        <div className="flex items-center justify-center gap-3 py-8 text-sm" style={{ color: 'var(--muted)' }}>
          <span className="play-spinner" style={{ color: 'var(--accent)' }} />
          Solving every decision…
        </div>
        <p className="caption tiny" style={{ textAlign: 'center' }}>
          Each decision is its own Monte-Carlo batch, so a full hand takes a while.
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="play-panel">
        <h2 className="play-panel-title">Analysis</h2>
        <div className="banner banner-error">{error}</div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="play-panel">
        <h2 className="play-panel-title">Analysis</h2>
        <p className="caption" style={{ textAlign: 'center' }}>
          Pick a seat and press <b>Analyze</b> to price every card that seat
          played against every card it could have played instead.
        </p>
      </div>
    )
  }

  const { decisions, summary } = result
  const sideLabel = result.role === 'defender' ? 'defensive tricks' : 'tricks'

  return (
    <div className="play-panel">
      <h2 className="play-panel-title">
        {result.role === 'defender' ? 'Defense' : 'Declarer'} analysis · {result.seat}
      </h2>

      <div className="flex flex-wrap items-center gap-2 mb-2 text-xs" style={{ color: 'var(--muted)' }}>
        <span style={{ color: 'var(--status-optimal)' }}>{summary.optimal}✓</span>
        {summary.good > 0 && <span style={{ color: 'var(--status-good)' }}>{summary.good}~</span>}
        {summary.suboptimal > 0 && (
          <span style={{ color: 'var(--status-suboptimal)' }}>{summary.suboptimal}✗</span>
        )}
        <span>of {summary.graded} graded</span>
        {summary.decisions > summary.graded && (
          <span>({summary.decisions - summary.graded} forced)</span>
        )}
        <span>·</span>
        <span>needs {result.tricks_needed} tricks</span>
        <span>·</span>
        <span>{result.method === 'double_dummy' ? 'double dummy' : `${result.num_deals} deals`}</span>
        {result.visible?.length > 0 && <span>· saw {result.visible.join(' + ')}</span>}
      </div>

      <div className="overflow-y-auto" style={{ maxHeight: '30rem' }}>
        <table className="play-decisions">
          <thead>
            <tr>
              <th title="Trick number">T#</th>
              <th>Card</th>
              <th title={`Expected ${sideLabel} after the card played`}>Act</th>
              <th title={`Expected ${sideLabel} after the best card`}>Best</th>
              <th style={{ textAlign: 'center' }}>Grade</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((d, i) => {
              const hasOptions = d.options.length > 1
              const isOpen = expanded === i
              return (
                <Fragment key={`${d.index}-${d.card}`}>
                  <tr
                    className={`clickable ${selected === i ? 'on' : ''}`}
                    style={d.forced ? { opacity: 0.55 } : undefined}
                    onClick={() => {
                      onSelect(d)
                      if (hasOptions) setExpanded((prev) => (prev === i ? null : i))
                    }}
                  >
                    <td style={{ color: 'var(--muted)' }}>
                      {hasOptions && (
                        <span className="inline-block mr-1 text-[0.6rem]"
                          style={{ transform: isOpen ? 'rotate(90deg)' : undefined }}>▶</span>
                      )}
                      {d.trick}
                      <span className="ml-1 text-[0.65rem]">{d.hand}</span>
                    </td>
                    <td><CardText card={d.card} /></td>
                    <td>{d.actual_tricks == null ? '—' : d.actual_tricks.toFixed(2)}</td>
                    <td>{d.best_tricks == null ? '—' : d.best_tricks.toFixed(2)}</td>
                    <td style={{ textAlign: 'center' }}>
                      {/* A forced card is not a decision — grading it would
                          read as praise for having no alternative. */}
                      {d.forced
                        ? <span className="text-[0.68rem]" style={{ color: 'var(--muted)' }}>forced</span>
                        : <StatusBadge status={d.status} />}
                    </td>
                  </tr>
                  {isOpen && <Options options={d.options} played={d.card} />}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-2 pt-2 text-xs" style={{ borderTop: '1px solid var(--border)', color: 'var(--muted)' }}>
        Total {sideLabel} given up:{' '}
        <b style={{ color: summary.total_trick_loss > 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)' }}>
          {summary.total_trick_loss.toFixed(2)}
        </b>
        {summary.graded > 0 && (
          <> · {summary.avg_trick_loss.toFixed(2)} per graded decision</>
        )}
      </div>
      <p className="caption tiny">
        Double-dummy solving sees all four hands on every sampled deal, so it
        finds plays a human could not — read a small loss as "there was a
        better card", not as a mistake.
      </p>
    </div>
  )
}
