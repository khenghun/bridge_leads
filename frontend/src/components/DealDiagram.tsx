import type { Seat } from '../api/types'
import { SEAT_NAME, SUIT_COLOR, SUIT_SYMBOL, SUITS, strainLabel } from '../lib/bridge'

/** One hand ('S.H.D.C') as four colour-coded suit lines. */
function HandLines({ pbn }: { pbn: string }) {
  const parts = (pbn.split('.').concat(['', '', '', ''])).slice(0, 4)
  return (
    <>
      {SUITS.map((suit, i) => (
        <div key={suit} className="hand-line">
          <span style={{ color: SUIT_COLOR[suit], fontWeight: 700 }}>{SUIT_SYMBOL[suit]}</span>{' '}
          <span className="mono">{parts[i] || '—'}</span>
        </div>
      ))}
    </>
  )
}

interface Props {
  layout: Record<string, string>
  leader: Seat
  declarer: Seat
  level: number
  strain: string
  declTricks: number
}

/** A full 4-hand deal as a cross diagram with the contract result centred. */
export default function DealDiagram({ layout, leader, declarer, level, strain, declTricks }: Props) {
  const result = declTricks - (6 + level)
  const resStr = result > 0 ? `made +${result}` : result === 0 ? 'made exactly' : `down ${-result}`

  const Cell = ({ seat }: { seat: Seat }) => {
    const tag = seat === leader ? ' · lead' : seat === declarer ? ' · decl' : ''
    return (
      <div className="deal-cell">
        <div className="deal-cell-name">{SEAT_NAME[seat]}{tag}</div>
        <HandLines pbn={layout[seat] ?? ''} />
      </div>
    )
  }

  const center = (
    <div className="deal-center">
      <b>{level}{strainLabel(strain)}</b> by {declarer}<br />
      decl {declTricks} trick(s)<br />
      <span style={{ color: '#27ae60', fontWeight: 600 }}>{resStr}</span>
    </div>
  )

  return (
    <table className="deal-table">
      <tbody>
        <tr><td /><td><Cell seat="N" /></td><td /></tr>
        <tr><td><Cell seat="W" /></td><td>{center}</td><td><Cell seat="E" /></td></tr>
        <tr><td /><td><Cell seat="S" /></td><td /></tr>
      </tbody>
    </table>
  )
}
