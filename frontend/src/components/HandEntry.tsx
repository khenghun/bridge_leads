import { useState } from 'react'
import type { Seat } from '../api/types'
import {
  SEAT_NAME, SUIT_COLOR, SUIT_SYMBOL, SUITS,
  holdingError, normHolding, parsePbn, randomHand, sortHolding,
  type Holdings,
} from '../lib/bridge'

interface Props {
  seat: Seat
  /** What this hand is in the current tool, e.g. 'the opening leader'. */
  role: string
  holdings: Holdings
  setHoldings: (h: Holdings) => void
}

/** Known-hand entry: PBN paste, random-hand, per-suit boxes, live validation.
 * Shared by both tools — the lead tool enters the leader's hand, the contract
 * tool your own. */
export default function HandEntry({ seat, role, holdings, setHoldings }: Props) {
  const [pbnEntry, setPbnEntry] = useState('')
  const [pbnError, setPbnError] = useState('')

  const applyPbn = (raw: string) => {
    setPbnEntry(raw)
    if (!raw.trim()) { setPbnError(''); return }
    const { holdings: parsed, error } = parsePbn(raw)
    if (error) { setPbnError(error); return }
    if (parsed) { setHoldings(parsed); setPbnError('') }
  }

  const setSuit = (suit: string, raw: string) => {
    setHoldings({ ...holdings, [suit]: normHolding(raw) })
  }

  const suitErrors = Object.fromEntries(
    SUITS.map((s) => [s, holdingError(holdings[s])]),
  ) as Record<string, string | null>
  const cardCount = SUITS.reduce((n, s) => n + holdings[s].length, 0)
  const pbn = SUITS.map((s) => holdings[s]).join('.')

  return (
    <section>
      <h2>{SEAT_NAME[seat]}'s hand ({role})</h2>
      <div className="hand-entry">
        <label className="field">
          Paste PBN (spades.hearts.diamonds.clubs)
          <input
            value={pbnEntry}
            placeholder="T.KT932.Q2.T9843"
            onChange={(e) => applyPbn(e.target.value)}
          />
        </label>
        {pbnError && <div className="err">⚠ {pbnError}</div>}
        <button
          className="btn"
          onClick={() => { setHoldings(randomHand()); setPbnError(''); setPbnEntry('') }}
        >
          🎲 Random hand
        </button>

        <div className="suit-boxes">
          {SUITS.map((s) => (
            <div key={s} className="suit-row">
              <span className="suit-symbol" style={{ color: SUIT_COLOR[s] }}>{SUIT_SYMBOL[s]}</span>
              <input
                value={holdings[s]}
                placeholder="AKQ / T = ten"
                onChange={(e) => setSuit(s, e.target.value)}
                onBlur={(e) => setSuit(s, sortHolding(normHolding(e.target.value)))}
              />
              {suitErrors[s] && <span className="err inline">⚠ {suitErrors[s]}</span>}
            </div>
          ))}
        </div>

        <p className="caption">
          {cardCount}/13 cards entered · PBN: <code>{pbn}</code>
        </p>
        {cardCount > 13 && !Object.values(suitErrors).some(Boolean) && (
          <div className="err">Too many cards ({cardCount}) — a hand holds exactly 13.</div>
        )}
      </div>
    </section>
  )
}
