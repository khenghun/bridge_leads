import { useEffect, useState } from 'react'
import type { Quality, Seat, Suit } from '../api/types'
import { validateShape } from '../api/lead'
import {
  ERR_RED, FIXED_CARDS_HINT, OK_GREEN, QUALITY_HINT, SEAT_NAME, SUIT_COLOR,
  SUIT_SYMBOL, SUITS, cardsToHoldings, normHolding, type Holdings,
} from '../lib/bridge'

export interface SeatConstraint {
  hcp: [number, number]
  suits: Record<Suit, [number, number]>
  shape: string
  /** At most one suit graded, and only for one seat across the whole table. */
  quality: Partial<Record<Suit, Quality>>
  /** Cards this hand is known to hold, as per-suit rank strings ({H: 'AK'}). */
  cards: Holdings
}

export function emptyCards(): Holdings {
  return { S: '', H: '', D: '', C: '' }
}

export function defaultSeatConstraint(): SeatConstraint {
  return {
    hcp: [0, 40],
    suits: { S: [0, 13], H: [0, 13], D: [0, 13], C: [0, 13] },
    shape: '',
    quality: {},
    cards: emptyCards(),
  }
}

/** Rebuild the per-seat editor state from an API constraints dict — the
 * inverse of the buildConstraints functions in the two apps. Used when a
 * share link (or a stored setup) restores a request into the form. */
export function seatStateFromConstraints(
  c: import('../api/types').Constraints,
): Record<Seat, SeatConstraint> {
  const out = {} as Record<Seat, SeatConstraint>
  for (const seat of ['N', 'E', 'S', 'W'] as Seat[]) {
    const sc = defaultSeatConstraint()
    const hcp = c.hcp?.[seat]
    if (hcp) sc.hcp = [hcp[0], hcp[1]]
    for (const suit of SUITS) {
      const range = c.suit_length?.[seat]?.[suit]
      if (range) sc.suits[suit] = [range[0], range[1]]
    }
    if (c.shapes?.[seat]) sc.shape = c.shapes[seat]
    for (const [suit, level] of Object.entries(c.quality?.[seat] ?? {})) {
      sc.quality[suit as Suit] = level
    }
    const cards = c.fixed_cards?.[seat]
    if (cards?.length) sc.cards = cardsToHoldings(cards)
    out[seat] = sc
  }
  return out
}

interface ShapeFeedback {
  kind: 'ok' | 'warn' | 'error'
  message: string
}

function SeatPanel({ seat, tag, value, onChange, setQuality, cardIssue }: {
  seat: Seat
  tag: string
  value: SeatConstraint
  onChange: (v: SeatConstraint) => void
  setQuality: (seat: Seat, suit: Suit, level: Quality | '') => void
  /** Why this seat's pinned cards are unusable, if they are. */
  cardIssue?: string
}) {
  const [feedback, setFeedback] = useState<ShapeFeedback | null>(null)
  const [showShape, setShowShape] = useState(false)
  const cardCount = SUITS.reduce((n, s) => n + value.cards[s].length, 0)
  // Open on mount when cards are already pinned (a restored/demo state); the
  // count on the button keeps a collapsed constraint from hiding.
  const [showCards, setShowCards] = useState(cardCount > 0)

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
        {/* inputMode gets the digit pad on phones rather than the full keyboard. */}
        <label>HCP min
          <input type="number" inputMode="numeric" min={0} max={40} value={value.hcp[0]}
            onChange={(e) => onChange({ ...value, hcp: [Number(e.target.value), value.hcp[1]] })} />
        </label>
        <label>HCP max
          <input type="number" inputMode="numeric" min={0} max={40} value={value.hcp[1]}
            onChange={(e) => onChange({ ...value, hcp: [value.hcp[0], Number(e.target.value)] })} />
        </label>
      </div>

      {SUITS.map((s) => (
        <div key={s} className="suit-len-row">
          <span className="suit-symbol" style={{ color: SUIT_COLOR[s] }}>{SUIT_SYMBOL[s]}</span>
          <input type="number" inputMode="numeric" min={0} max={13} value={value.suits[s][0]}
            onChange={(e) => onChange({
              ...value, suits: { ...value.suits, [s]: [Number(e.target.value), value.suits[s][1]] },
            })} />
          <input type="number" inputMode="numeric" min={0} max={13} value={value.suits[s][1]}
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
            autoCapitalize="none" autoCorrect="off" spellCheck={false}
            onChange={(e) => onChange({ ...value, shape: e.target.value })}
          />
          {feedback && (
            <div style={{ color: feedbackColor, fontSize: '0.8em' }}>
              {feedback.kind === 'ok' ? '✓' : '⚠'} {feedback.message}
            </div>
          )}
        </div>
      )}

      <button className="btn btn-small" title={FIXED_CARDS_HINT}
        onClick={() => setShowCards((v) => !v)}>
        ➕ Specific cards{cardCount ? ` (${cardCount})` : ''}
      </button>
      {showCards && (
        <div className="shape-box">
          <p className="caption tiny">
            Cards you know this hand holds — type ranks per suit, e.g.{' '}
            <code>AK</code> in ♥ pins <span style={{ color: SUIT_COLOR.H }}>♥A ♥K</span>.
            The rest of the hand is still simulated around them.
          </p>
          {SUITS.map((s) => (
            <div key={s} className="fixed-card-row">
              <span className="suit-symbol" style={{ color: SUIT_COLOR[s] }}>{SUIT_SYMBOL[s]}</span>
              <input value={value.cards[s]} placeholder="e.g. AK" spellCheck={false}
                autoCapitalize="characters" autoCorrect="off" autoComplete="off"
                onChange={(e) => onChange({
                  ...value, cards: { ...value.cards, [s]: normHolding(e.target.value) },
                })} />
            </div>
          ))}
          {cardIssue && (
            <div style={{ color: ERR_RED, fontSize: '0.8em' }}>⚠ {cardIssue}</div>
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
  /** Per-seat pinned-card problems, from `fixedCardIssues` — the editor cannot
   * work them out itself, since the clash may be with the hand it never sees. */
  cardIssues?: Partial<Record<Seat, string>>
}

/** Constraint panels for the three unseen hands. */
export default function ConstraintsEditor({
  seats, constraints, setConstraint, setQuality, cardIssues,
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
            cardIssue={cardIssues?.[seat]}
          />
        ))}
      </div>
    </section>
  )
}
