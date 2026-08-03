import { useEffect, useState } from 'react'
import type { Quality, Seat, Suit } from '../api/types'
import { validateShape } from '../api/lead'
import {
  ERR_RED, OK_GREEN, QUALITY_HINT, SEAT_NAME, SUIT_COLOR, SUIT_SYMBOL, SUITS,
} from '../lib/bridge'

export interface SeatConstraint {
  hcp: [number, number]
  suits: Record<Suit, [number, number]>
  shape: string
  /** At most one suit graded, and only for one seat across the whole table. */
  quality: Partial<Record<Suit, Quality>>
}

export function defaultSeatConstraint(): SeatConstraint {
  return {
    hcp: [0, 40],
    suits: { S: [0, 13], H: [0, 13], D: [0, 13], C: [0, 13] },
    shape: '',
    quality: {},
  }
}

interface ShapeFeedback {
  kind: 'ok' | 'warn' | 'error'
  message: string
}

function SeatPanel({ seat, tag, value, onChange, setQuality }: {
  seat: Seat
  tag: string
  value: SeatConstraint
  onChange: (v: SeatConstraint) => void
  setQuality: (seat: Seat, suit: Suit, level: Quality | '') => void
}) {
  const [feedback, setFeedback] = useState<ShapeFeedback | null>(null)
  const [showShape, setShowShape] = useState(false)

  // Debounced live validation of the advanced-shape text (mirrors the old
  // Streamlit popover's ✓/⚠ feedback).
  useEffect(() => {
    const text = value.shape.trim()
    if (!text) { setFeedback(null); return }
    let cancelled = false
    const id = setTimeout(() => {
      validateShape(text)
        .then((r) => {
          if (cancelled) return
          setFeedback(r.warnings.length
            ? { kind: 'warn', message: r.warnings.join('; ') }
            : { kind: 'ok', message: `${r.terms_count} term(s) parsed` })
        })
        .catch((e: Error) => { if (!cancelled) setFeedback({ kind: 'error', message: e.message }) })
    }, 300)
    return () => { cancelled = true; clearTimeout(id) }
  }, [value.shape])

  const feedbackColor = feedback?.kind === 'ok' ? OK_GREEN : ERR_RED

  return (
    <div className="seat-panel">
      <h3>{SEAT_NAME[seat]}<span className="tag">{tag}</span></h3>

      <div className="hcp-row">
        <label>HCP min
          <input type="number" min={0} max={40} value={value.hcp[0]}
            onChange={(e) => onChange({ ...value, hcp: [Number(e.target.value), value.hcp[1]] })} />
        </label>
        <label>HCP max
          <input type="number" min={0} max={40} value={value.hcp[1]}
            onChange={(e) => onChange({ ...value, hcp: [value.hcp[0], Number(e.target.value)] })} />
        </label>
      </div>

      {SUITS.map((s) => (
        <div key={s} className="suit-len-row">
          <span className="suit-symbol" style={{ color: SUIT_COLOR[s] }}>{SUIT_SYMBOL[s]}</span>
          <input type="number" min={0} max={13} value={value.suits[s][0]}
            onChange={(e) => onChange({
              ...value, suits: { ...value.suits, [s]: [Number(e.target.value), value.suits[s][1]] },
            })} />
          <input type="number" min={0} max={13} value={value.suits[s][1]}
            onChange={(e) => onChange({
              ...value, suits: { ...value.suits, [s]: [value.suits[s][0], Number(e.target.value)] },
            })} />
          {/* Picking a quality anywhere clears every other one — the engine
              accepts exactly one across the whole table. */}
          <select className="quality-select" title={QUALITY_HINT}
            value={value.quality[s] ?? ''}
            onChange={(e) => setQuality(seat, s, e.target.value as Quality | '')}>
            <option value="">—</option>
            <option value="good">good</option>
            <option value="poor">poor</option>
          </select>
        </div>
      ))}

      <button className="btn btn-small" onClick={() => setShowShape((v) => !v)}>
        ➕ Advanced shape
      </button>
      {showShape && (
        <div className="shape-box">
          <p className="caption tiny">
            Disjunctive shape: each <code>(…)</code> ANDs suit-length bounds, join terms with{' '}
            <code>or</code>. Lengths: <code>2-4h</code>, <code>5s</code>, <code>&gt;=2c</code>,{' '}
            <code>&lt;=3h</code>. Combines with the numeric bounds.
          </p>
          <textarea
            rows={3}
            value={value.shape}
            placeholder="(2-4s,2-4h,2-5d,2-5c) or (5h,2-3s,2-4d,2-4c)"
            onChange={(e) => onChange({ ...value, shape: e.target.value })}
          />
          {feedback && (
            <div style={{ color: feedbackColor, fontSize: '0.8em' }}>
              {feedback.kind === 'ok' ? '✓' : '⚠'} {feedback.message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  /** The three hands the current tool cannot see, each with a role label —
   * declarer/dummy/partner for the lead tool, partner/LHO/RHO for the
   * contract tool. */
  seats: Array<[Seat, string]>
  constraints: Record<Seat, SeatConstraint>
  setConstraint: (seat: Seat, v: SeatConstraint) => void
  setQuality: (seat: Seat, suit: Suit, level: Quality | '') => void
}

/** Constraint panels for the three unseen hands. */
export default function ConstraintsEditor({
  seats, constraints, setConstraint, setQuality,
}: Props) {
  return (
    <section>
      <h2>Constraints on the unseen hands (optional)</h2>
      <p className="caption">Leave HCP at 0–40 and suit lengths at 0–13 for no constraint.</p>
      <p className="caption tiny">
        The last column grades one suit's <strong>quality</strong> —{' '}
        <em>good</em> = 2 of AKQ or 3 of AKQJT (what a preempt or overcall
        promises), <em>poor</em> = anything worse. Only one suit in the whole
        table can be graded, so picking a new one clears the previous.
      </p>
      <div className="constraint-grid">
        {seats.map(([seat, tag]) => (
          <SeatPanel
            key={seat}
            seat={seat}
            tag={tag}
            value={constraints[seat]}
            onChange={(v) => setConstraint(seat, v)}
            setQuality={setQuality}
          />
        ))}
      </div>
    </section>
  )
}
