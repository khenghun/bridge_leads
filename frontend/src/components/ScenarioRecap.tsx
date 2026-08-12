import type { Seat } from '../api/types'
import { SEAT_NAME } from '../lib/bridge'

export interface RecapSeat {
  seat: Seat
  /** Role suffix, e.g. 'declarer' / 'your partner'. */
  role: string
  /** Readable constraint lines from describeSeatConstraints; empty = any hand. */
  lines: string[]
}

interface Props {
  /** Run-level chips, e.g. '3NT by South', 'none vul', '300 deals'. */
  context: string[]
  seats: RecapSeat[]
}

/** The question echoed back beside the answer: what was fixed and what was
 * assumed, rendered from the request that produced the results (not the live
 * form, which may have drifted since). Doubles as the "here is what this link
 * asked" banner for a shared result. */
export default function ScenarioRecap({ context, seats }: Props) {
  return (
    <div className="recap">
      <div className="recap-row">
        {context.map((c) => <span key={c} className="recap-chip recap-context">{c}</span>)}
      </div>
      <div className="recap-row">
        {seats.map(({ seat, role, lines }) => (
          <span key={seat} className="recap-chip">
            <b>{SEAT_NAME[seat]}</b> ({role}):{' '}
            {lines.length ? lines.join(' · ') : 'any hand'}
          </span>
        ))}
      </div>
    </div>
  )
}
