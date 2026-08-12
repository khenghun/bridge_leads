import type { Seat, Suit } from '../api/types'
import {
  SEAT_NAME, SUIT_SYMBOL, SUITS, criterionActive, defaultCriterion,
  type DealCriterion,
} from '../lib/bridge'

interface Props {
  /** The seats worth filtering on (the unseen hands), with role labels. */
  seats: Array<[Seat, string]>
  criterion: DealCriterion
  setCriterion: (c: DealCriterion) => void
}

/** One-criterion filter over the browsable deals: seat + HCP window +
 * optional suit-length window, include or exclude. Browse-only by design —
 * the sections that embed this keep every ranking and aggregate full-run and
 * show a "showing N of M" line whenever the filter is live. */
export default function DealFilterBar({ seats, criterion, setCriterion }: Props) {
  const c = criterion
  const set = (patch: Partial<DealCriterion>) => setCriterion({ ...c, ...patch })
  const num = (v: string, lo: number, hi: number, fallback: number) => {
    const n = Number(v)
    return Number.isFinite(n) && v !== '' ? Math.max(lo, Math.min(hi, n)) : fallback
  }

  return (
    <div className="filter-bar">
      <span className="caption">Only deals where</span>
      <select value={c.seat} onChange={(e) => set({ seat: e.target.value })}>
        {seats.map(([s, role]) => (
          <option key={s} value={s}>{SEAT_NAME[s]} ({role})</option>
        ))}
      </select>
      <span className="caption">has</span>
      <input type="number" inputMode="numeric" min={0} max={40} value={c.hcp[0]}
        aria-label="HCP min"
        onChange={(e) => set({ hcp: [num(e.target.value, 0, 40, 0), c.hcp[1]] })} />
      <span className="caption">–</span>
      <input type="number" inputMode="numeric" min={0} max={40} value={c.hcp[1]}
        aria-label="HCP max"
        onChange={(e) => set({ hcp: [c.hcp[0], num(e.target.value, 0, 40, 40)] })} />
      <span className="caption">HCP and</span>
      <select value={c.suit} aria-label="Suit"
        onChange={(e) => set({ suit: e.target.value as Suit | '' })}>
        <option value="">any suit</option>
        {SUITS.map((s) => <option key={s} value={s}>{SUIT_SYMBOL[s]}</option>)}
      </select>
      <input type="number" inputMode="numeric" min={0} max={13} value={c.len[0]}
        aria-label="Length min" disabled={c.suit === ''}
        onChange={(e) => set({ len: [num(e.target.value, 0, 13, 0), c.len[1]] })} />
      <span className="caption">–</span>
      <input type="number" inputMode="numeric" min={0} max={13} value={c.len[1]}
        aria-label="Length max" disabled={c.suit === ''}
        onChange={(e) => set({ len: [c.len[0], num(e.target.value, 0, 13, 13)] })} />
      <span className="caption">cards</span>
      <div className="seg seg-compact">
        <button className={!c.exclude ? 'on' : ''} onClick={() => set({ exclude: false })}>
          Include
        </button>
        <button className={c.exclude ? 'on' : ''} onClick={() => set({ exclude: true })}>
          Exclude
        </button>
      </div>
      <button className="btn btn-small" disabled={!criterionActive(c)}
        onClick={() => setCriterion(defaultCriterion(c.seat))}>
        Clear
      </button>
    </div>
  )
}
