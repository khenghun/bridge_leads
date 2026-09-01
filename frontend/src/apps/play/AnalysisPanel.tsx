/**
 * AnalysisPanel — the graded decisions, ported from
 * bridge_ai/src/components/AnalysisPanel.jsx (minus its AI review modal) and
 * regrouped by pair for v1.1.
 *
 * One analysis is a plan (which pairs, which seats) plus one result per seat
 * as they arrive. Each pair is a card: its summary, then a section per graded
 * seat with the decisions table — one row per decision, click to jump the
 * viewer to that card and expand every legal alternative ranked by expected
 * tricks. The whole-table view adds the biggest swings across all seats at
 * the top.
 */
import { Fragment, useEffect, useState } from 'react'
import type { Seat, Suit } from '../../api/types'
import type { AnalyzeResponse, CardOption, Decision, DecisionStatus } from '../../api/playTypes'
import { SEAT_NAME, SUIT_COLOR, SUIT_SYMBOL } from '../../lib/bridge'
import {
  PAIR_LABEL, pairRole, pairSummary, rankSwings, seatsOfPair,
  type AnalysisAction, type Pair, type Swing,
} from './analysis'

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

export type SeatStatus = 'queued' | 'solving' | 'done' | 'failed'

/** What one Analyze press asked for. */
export interface AnalysisPlan {
  action: AnalysisAction
  declarer: Seat
  pairs: Pair[]
  seats: Seat[]
}

export interface Selection {
  seat: Seat
  index: number
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

/** Signed number with a fixed number of decimals; '—' for zero. */
function signed(n: number | null | undefined, digits: number): string {
  if (n == null || Math.abs(n) < 0.005) return '—'
  return `${n > 0 ? '+' : '−'}${Math.abs(n).toFixed(digits)}`
}

function impColor(n: number | null | undefined): string {
  if (n == null || Math.abs(n) < 0.005) return 'var(--muted)'
  return n < 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)'
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
      <td colSpan={6} style={{ padding: 0, borderBottom: '1px solid var(--border)' }}>
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
                <th title="Mean duplicate score for your side, with vulnerability and doubling">Score</th>
                <th title="IMPs against the best card, converted deal by deal">IMPs</th>
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
                    <td className="tabular-nums" style={{ color: 'var(--muted)' }}>
                      {o.score == null ? '—' : signed(o.score, 0)}
                    </td>
                    <td className="tabular-nums" style={{ color: impColor(o.imps) }}>
                      {signed(o.imps, 2)}
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

/** One seat's graded decisions — the v1.0 table, now one section of a pair card. */
function DecisionsTable({ result, selected, onSelect }: {
  result: AnalyzeResponse
  selected: number | null
  onSelect: (decision: Decision, index: number) => void
}) {
  const [expanded, setExpanded] = useState<number | null>(null)
  // A selection made elsewhere (the biggest-swings list) opens the options
  // here too, so the jump lands on the alternatives, not just the row.
  useEffect(() => { if (selected != null) setExpanded(selected) }, [selected])
  const { decisions, summary } = result
  const sideLabel = result.role === 'defender' ? 'defensive tricks' : 'tricks'

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 mb-1 text-xs" style={{ color: 'var(--muted)' }}>
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
        <span>{result.method === 'double_dummy' ? 'double dummy' : `${result.num_deals} deals`}</span>
        {result.visible?.length > 0 && <span>· saw {result.visible.join(' + ')}</span>}
      </div>

      <div className="overflow-y-auto" style={{ maxHeight: '24rem' }}>
        <table className="play-decisions">
          <thead>
            <tr>
              <th title="Trick number">T#</th>
              <th>Card</th>
              <th title={`Expected ${sideLabel} after the card played`}>Act</th>
              <th title={`Expected ${sideLabel} after the best card`}>Best</th>
              <th title="IMPs given up against the best card, converted deal by deal">IMPs</th>
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
                      onSelect(d, i)
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
                    <td className="tabular-nums" style={{ color: impColor(d.imp_diff) }}
                      title={d.score_diff == null ? undefined : `${signed(d.score_diff, 0)} points`}>
                      {d.forced ? '—' : signed(d.imp_diff, 2)}
                    </td>
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

      <div className="mt-1 text-xs" style={{ color: 'var(--muted)' }}>
        {sideLabel[0].toUpperCase() + sideLabel.slice(1)} given up:{' '}
        <b style={{ color: summary.total_trick_loss > 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)' }}>
          {summary.total_trick_loss.toFixed(2)}
        </b>
        {summary.graded > 0 && (
          <> · {summary.avg_trick_loss.toFixed(2)} per graded decision</>
        )}
        {summary.total_imp_loss != null && (
          <>
            {' · '}
            <b style={{ color: summary.total_imp_loss > 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)' }}>
              {summary.total_imp_loss.toFixed(2)} IMPs
            </b>
            {summary.total_score_loss > 0 && (
              <span> ({Math.round(summary.total_score_loss)} points)</span>
            )}
          </>
        )}
      </div>
    </>
  )
}

function SeatSection({ seat, status, result, error, selected, onSelect }: {
  seat: Seat
  status: SeatStatus | undefined
  result: AnalyzeResponse | undefined
  error: string | undefined
  selected: number | null
  onSelect: (decision: Decision, index: number) => void
}) {
  return (
    <section className="play-seat-section" data-seat={seat} data-status={status ?? 'queued'}>
      <h3 className="play-seat-heading">
        {SEAT_NAME[seat]}
        {status === 'solving' && (
          <span className="play-seat-status"><span className="play-spinner" /> solving…</span>
        )}
        {status === 'queued' && <span className="play-seat-status">queued</span>}
      </h3>
      {status === 'failed' && <div className="banner banner-error">{error}</div>}
      {result && <DecisionsTable result={result} selected={selected} onSelect={onSelect} />}
    </section>
  )
}

function PairCard({ pair, plan, results, statuses, errors, contractText, selected, onSelect }: {
  pair: Pair
  plan: AnalysisPlan
  results: Partial<Record<Seat, AnalyzeResponse>>
  statuses: Partial<Record<Seat, SeatStatus>>
  errors: Partial<Record<Seat, string>>
  contractText: string
  selected: Selection | null
  onSelect: (seat: Seat, decision: Decision, index: number) => void
}) {
  const role = pairRole(pair, plan.declarer)
  const seats = seatsOfPair(pair, plan.declarer)
  const sum = pairSummary(results, seats)
  const partial = sum && sum.seats.length < seats.length
  return (
    <div className="play-panel" data-pair={pair}>
      <h2 className="play-panel-title" style={{ marginBottom: '0.2rem' }}>
        {PAIR_LABEL[pair]} · {role === 'declarer' ? `declaring ${contractText}` : 'defending'}
      </h2>
      {sum ? (
        <div className="flex flex-wrap items-center gap-2 mb-2 text-xs" style={{ color: 'var(--muted)' }}>
          <span style={{ color: 'var(--status-optimal)' }}>{sum.optimal}✓</span>
          {sum.good > 0 && <span style={{ color: 'var(--status-good)' }}>{sum.good}~</span>}
          {sum.suboptimal > 0 && <span style={{ color: 'var(--status-suboptimal)' }}>{sum.suboptimal}✗</span>}
          <span>of {sum.graded} graded</span>
          <span>·</span>
          <span>
            {role === 'defender' ? 'defensive tricks' : 'tricks'} given up{' '}
            <b style={{ color: sum.total_trick_loss > 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)' }}>
              {sum.total_trick_loss.toFixed(2)}
            </b>
          </span>
          <span>·</span>
          <span>
            <b style={{ color: sum.total_imp_loss > 0 ? 'var(--status-suboptimal)' : 'var(--status-optimal)' }}>
              {sum.total_imp_loss.toFixed(2)} IMPs
            </b>
          </span>
          {partial && <span>· {sum.seats.join(' ')} so far</span>}
        </div>
      ) : (
        <p className="caption tiny" style={{ margin: '0 0 0.4rem' }}>
          {role === 'declarer'
            ? 'Declarer is graded on both hands — the cards played from dummy are declarer’s decisions.'
            : 'Each defender is graded on what they could see: their own hand and dummy.'}
        </p>
      )}
      {seats.map((seat) => (
        <SeatSection
          key={seat}
          seat={seat}
          status={statuses[seat]}
          result={results[seat]}
          error={errors[seat]}
          selected={selected?.seat === seat ? selected.index : null}
          onSelect={(d, i) => onSelect(seat, d, i)}
        />
      ))}
    </div>
  )
}

const SWINGS_SHOWN = 8

/** The whole table's costliest decisions, any seat, worst first. */
function Swings({ swings, results, done, onSelect }: {
  swings: Swing[]
  results: Partial<Record<Seat, AnalyzeResponse>>
  done: boolean
  onSelect: (seat: Seat, decision: Decision, index: number) => void
}) {
  const [all, setAll] = useState(false)
  const shown = all ? swings : swings.slice(0, SWINGS_SHOWN)
  return (
    <div className="play-panel" data-swings>
      <h2 className="play-panel-title" style={{ marginBottom: '0.2rem' }}>Biggest swings</h2>
      <p className="caption tiny" style={{ margin: '0 0 0.4rem' }}>
        Ranked by IMPs — a game let through outranks an overtrick, whatever the trick count says.
      </p>
      {swings.length === 0 ? (
        <p className="caption tiny" style={{ margin: 0 }}>
          {done ? 'No decision cost a trick — a clean board all round.' : 'Nothing costly yet…'}
        </p>
      ) : (
        <>
          <table className="play-decisions">
            <thead>
              <tr>
                <th>T#</th>
                <th>Seat</th>
                <th>Card</th>
                <th title="IMPs given up against the best card, converted deal by deal">IMPs</th>
                <th title="Tricks given up against the best card">Tricks</th>
                <th style={{ textAlign: 'center' }}>Grade</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => {
                const index = results[s.seat]?.decisions.indexOf(s.decision) ?? -1
                return (
                  <tr
                    key={`${s.seat}-${s.decision.index}`}
                    className="clickable"
                    onClick={() => onSelect(s.seat, s.decision, index)}
                  >
                    <td style={{ color: 'var(--muted)' }}>{s.decision.trick}</td>
                    <td>
                      {s.seat}
                      <span className="ml-1 text-[0.65rem]" style={{ color: 'var(--muted)' }}>
                        {s.role === 'declarer' ? (s.decision.hand === s.seat ? 'decl' : 'dummy') : 'def'}
                      </span>
                    </td>
                    <td><CardText card={s.decision.card} /></td>
                    <td className="tabular-nums" style={{ color: impColor(-s.imps) }}
                      title={s.decision.score_diff == null ? undefined : `${signed(s.decision.score_diff, 0)} points`}>
                      {signed(-s.imps, 2)}
                    </td>
                    <td className="tabular-nums" style={{ color: 'var(--status-suboptimal)' }}>
                      −{s.loss.toFixed(2)}
                    </td>
                    <td style={{ textAlign: 'center' }}><StatusBadge status={s.decision.status} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {swings.length > SWINGS_SHOWN && (
            <button className="btn btn-small" style={{ marginTop: '0.4rem' }} onClick={() => setAll(!all)}>
              {all ? 'Show fewer' : `Show all ${swings.length}`}
            </button>
          )}
          {!done && <p className="caption tiny" style={{ margin: '0.3rem 0 0' }}>Still solving — the list grows as seats finish.</p>}
        </>
      )}
    </div>
  )
}

interface Props {
  plan: AnalysisPlan | null
  results: Partial<Record<Seat, AnalyzeResponse>>
  statuses: Partial<Record<Seat, SeatStatus>>
  errors: Partial<Record<Seat, string>>
  /** e.g. "1NT" — for the declaring pair's heading. */
  contractText: string
  selected: Selection | null
  /** Jump the viewer to the card this decision played. */
  onSelect: (seat: Seat, decision: Decision, index: number) => void
}

export default function AnalysisPanel({
  plan, results, statuses, errors, contractText, selected, onSelect,
}: Props) {
  if (!plan) {
    return (
      <div className="play-panel">
        <h2 className="play-panel-title">Analysis</h2>
        <p className="caption" style={{ textAlign: 'center' }}>
          Choose a pair — or the whole table — and press <b>Analyze</b> to
          price every card they played against every card they could have
          played instead.
        </p>
      </div>
    )
  }

  const done = plan.seats.every((s) => statuses[s] === 'done' || statuses[s] === 'failed')

  return (
    <>
      {plan.action === 'table' && (
        <Swings swings={rankSwings(results)} results={results} done={done} onSelect={onSelect} />
      )}
      {plan.pairs.map((pair) => (
        <PairCard
          key={pair}
          pair={pair}
          plan={plan}
          results={results}
          statuses={statuses}
          errors={errors}
          contractText={contractText}
          selected={selected}
          onSelect={onSelect}
        />
      ))}
      {done && (
        <p className="caption tiny" style={{ margin: 0 }}>
          Double-dummy solving sees all four hands on every sampled deal, so it
          finds plays a human could not — read a small loss as "there was a
          better card", not as a mistake.
        </p>
      )}
    </>
  )
}
