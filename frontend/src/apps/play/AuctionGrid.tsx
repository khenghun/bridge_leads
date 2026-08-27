/**
 * AuctionGrid — the bidding as a four-column grid, ported from
 * bridge_ai/src/components/AuctionGrid.jsx.
 *
 * Columns are always W | N | E | S; the first call sits in the dealer's
 * column, so the leading cells are blank. The final contract bid is boxed.
 */
import type { Suit } from '../../api/types'
import { SUIT_COLOR, SUIT_SYMBOL } from '../../lib/bridge'
import { isCall, normBid, type Bid, type GameState } from '../../lib/lin'

const COLUMNS = ['W', 'N', 'E', 'S'] as const

/** Colour a call: passes recede, penalty doubles stand out, bids take their
 * suit's colour from the shared four-colour scheme. */
function bidColor(bid: string): string {
  const b = normBid(bid)
  if (b === 'P' || b === 'PASS' || b === '-') return 'var(--muted)'
  if (b === 'D' || b === 'X' || b === 'DBL') return '#e74c3c'
  if (b === 'R' || b === 'XX' || b === 'RDBL') return '#2563eb'
  const denom = b.slice(1)
  if (denom === 'N' || denom === 'NT') return 'var(--text)'
  return SUIT_COLOR[denom as Suit] ?? 'var(--text)'
}

function bidLabel(bid: string): string {
  const b = normBid(bid)
  if (b === 'P' || b === 'PASS' || b === '-') return 'Pass'
  if (b === 'D' || b === 'X' || b === 'DBL') return 'Dbl'
  if (b === 'R' || b === 'XX' || b === 'RDBL') return 'Rdbl'
  const denom = b.slice(1)
  if (denom === 'N' || denom === 'NT') return `${b[0]}NT`
  return `${b[0]}${SUIT_SYMBOL[denom as Suit] ?? denom}`
}

/** Index of the last real bid — the one that became the contract. */
function finalBidIndex(auction: Bid[]): number {
  let last = -1
  auction.forEach((item, i) => { if (normBid(item.bid) && !isCall(item.bid)) last = i })
  return last
}

export default function AuctionGrid({ game }: { game: GameState }) {
  const { auction, dealer } = game
  if (!auction.length) {
    return <div className="text-sm text-center py-3" style={{ color: 'var(--muted)' }}>No auction data</div>
  }

  const offset = COLUMNS.indexOf(dealer as typeof COLUMNS[number])
  const finalIdx = finalBidIndex(auction)
  const padded: Array<Bid | null> = [...Array(Math.max(offset, 0)).fill(null), ...auction]
  const rows: Array<Array<Bid | null>> = []
  for (let i = 0; i < padded.length; i += 4) rows.push(padded.slice(i, i + 4))

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-center border-collapse">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col}
                className="px-3 py-1 text-xs font-bold tracking-widest"
                style={{
                  color: col === dealer ? '#eab308' : 'var(--muted)',
                  borderBottom: '1px solid var(--border)',
                }}
                title={col === dealer ? 'dealer' : undefined}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {row.map((item, colIdx) => {
                const auctionIdx = rowIdx * 4 + colIdx - offset
                const isFinal = auctionIdx === finalIdx
                return (
                  <td
                    key={colIdx}
                    className="px-3 py-1 text-sm font-mono"
                    style={{
                      borderBottom: '1px solid var(--border)',
                      background: isFinal ? 'rgba(234, 179, 8, 0.15)' : undefined,
                      boxShadow: isFinal ? 'inset 0 0 0 1px rgba(234, 179, 8, 0.6)' : undefined,
                    }}
                    title={item?.alert || undefined}
                  >
                    {item && (
                      <span style={{ color: bidColor(item.bid), fontWeight: 600 }}>
                        {bidLabel(item.bid)}
                        {item.alert && (
                          <sup className="ml-0.5 text-xs cursor-help" style={{ color: '#eab308' }}>*</sup>
                        )}
                      </span>
                    )}
                  </td>
                )
              })}
              {row.length < 4 && Array(4 - row.length).fill(null).map((_, i) => (
                <td key={`pad-${i}`} className="px-3 py-1" />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
