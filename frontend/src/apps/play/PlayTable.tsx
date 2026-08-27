/**
 * PlayTable — the four hands in a bridge-table layout, ported from
 * bridge_ai/src/components/HandDisplay.jsx.
 *
 *          NORTH
 *   WEST  COMPASS  EAST
 *          SOUTH
 *
 * The compass carries the current trick laid out spatially (each card next to
 * the seat that played it), so the table reads the way it looks in real life.
 * Played cards are struck through; a card that was graded shows its status
 * colour and the trick loss on hover.
 */
import type { Seat, Suit } from '../../api/types'
import type { Decision } from '../../api/playTypes'
import { SUIT_COLOR, SUIT_SYMBOL } from '../../lib/bridge'
import {
  SUIT_NAMES, SUIT_OF, type CardPlay, type GameState, type Vulnerability,
} from '../../lib/lin'
import { STATUS_COLOR, STATUS_LABEL } from './AnalysisPanel'

export interface PlayInfo {
  playedByPlayer: Record<Seat, Set<string>>
  currentTrick: { cards: CardPlay[]; leader: Seat | null }
}

/** Graded decisions keyed by the card played ('SK'). */
export type AnalysisMap = Map<string, Decision>

export function isVulnerable(vul: Vulnerability, seat: Seat): boolean {
  if (vul === 'both') return true
  if (vul === 'NS') return seat === 'N' || seat === 'S'
  if (vul === 'EW') return seat === 'E' || seat === 'W'
  return false
}

function Hand({ seat, game, played, analysis, graded }: {
  seat: Seat
  game: GameState
  played?: Set<string>
  analysis: AnalysisMap | null
  graded: Seat | null
}) {
  const hand = game.hands[seat]
  if (!hand) return null
  const isDeclarer = game.declarer === seat
  const vul = isVulnerable(game.vulnerability, seat)

  return (
    <div
      className="flex flex-col gap-0.5 px-3 py-2 rounded-lg font-mono text-sm leading-tight"
      style={{
        background: isDeclarer ? '#dceafb' : '#f7fbff',
        boxShadow: graded === seat
          ? '0 0 0 2px #2563eb'
          : isDeclarer ? '0 0 0 1px #93b4de' : '0 0 0 1px #d9e6f5',
      }}
    >
      <div
        className="text-xs font-bold tracking-widest mb-1 text-center"
        style={{ color: vul ? '#c0392b' : '#475569' }}
      >
        {seat}
        {isDeclarer && <span className="ml-1 font-normal" style={{ color: '#2563eb' }}>(decl)</span>}
        {graded === seat && <span className="ml-1 font-normal" style={{ color: '#2563eb' }}>◆</span>}
      </div>

      {SUIT_NAMES.map((name) => {
        const letter = SUIT_OF[name] as Suit
        const ranks = hand[name]
        return (
          <div key={name} className="flex items-baseline gap-1">
            <span className="font-bold" style={{ color: SUIT_COLOR[letter] }}>
              {SUIT_SYMBOL[letter]}
            </span>
            <span className="tracking-wide">
              {ranks.length === 0 ? <span style={{ color: '#94a3b8' }}>—</span> : ranks.map((rank) => {
                const code = letter + rank
                const isPlayed = played?.has(code)
                const decision = analysis?.get(code)
                if (isPlayed && decision) {
                  const loss = decision.diff == null
                    ? 'no choice'
                    : `${decision.diff >= 0 ? '+' : ''}${decision.diff.toFixed(2)} tricks`
                  return (
                    <span
                      key={rank}
                      className="line-through font-bold cursor-help"
                      style={{ color: STATUS_COLOR[decision.status] ?? '#94a3b8' }}
                      title={
                        `Trick ${decision.trick} · ${STATUS_LABEL[decision.status] ?? decision.status}`
                        + ` · ${loss}`
                        + (decision.best_cards.length ? ` · best: ${decision.best_cards.join(' ')}` : '')
                      }
                    >
                      {rank}
                    </span>
                  )
                }
                return (
                  <span
                    key={rank}
                    className={isPlayed ? 'line-through' : ''}
                    style={{ color: isPlayed ? '#94a3b8' : SUIT_COLOR[letter] }}
                  >
                    {rank}
                  </span>
                )
              })}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** One card face-up on the table. */
function TrickCard({ suit, rank }: { suit: Suit; rank: string }) {
  return (
    <div
      className="text-lg font-mono font-bold bg-white rounded-md px-2.5 py-1 leading-none min-w-[2.4rem] text-center"
      style={{ color: SUIT_COLOR[suit], boxShadow: '0 1px 3px rgba(15, 23, 42, 0.25)' }}
    >
      {SUIT_SYMBOL[suit]}{rank}
    </div>
  )
}

function CompassLabel({ seat, game }: { seat: Seat; game: GameState }) {
  const vul = isVulnerable(game.vulnerability, seat)
  return (
    <span
      className="font-bold text-sm px-1.5 py-0.5 rounded select-none text-white"
      style={{
        background: vul ? '#c0392b' : '#64748b',
        boxShadow: seat === game.dealer ? '0 0 0 2px #eab308' : undefined,
      }}
      title={seat === game.dealer ? 'dealer' : undefined}
    >
      {seat}
    </span>
  )
}

function contractText(game: GameState): string | null {
  if (!game.contract) return null
  const { level, suit, doubled } = game.contract
  const sym = suit === 'NT' ? 'NT' : SUIT_SYMBOL[suit as Suit]
  return `${level}${sym}${doubled === 1 ? 'X' : doubled === 2 ? 'XX' : ''}`
}

function Compass({ game, currentTrick }: {
  game: GameState
  currentTrick?: { cards: CardPlay[]; leader: Seat | null }
}) {
  const onTable = new Map<Seat, CardPlay>()
  for (const card of currentTrick?.cards ?? []) onTable.set(card.player, card)
  const hasTrick = onTable.size > 0

  const slot = (seat: Seat, spacer: string) => {
    const card = onTable.get(seat)
    if (!hasTrick) return null
    return card ? <TrickCard suit={card.suit} rank={card.rank} /> : <div className={spacer} />
  }

  const label = contractText(game)

  return (
    <div className="flex flex-col items-center justify-center gap-1 min-w-[120px]">
      <div className="flex flex-col items-center gap-0.5">
        <CompassLabel seat="N" game={game} />
        {slot('N', 'h-8')}
      </div>

      <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-1">
          <CompassLabel seat="W" game={game} />
          {slot('W', 'w-12 h-8')}
        </div>
        <div className="flex flex-col items-center gap-0.5" style={{ color: '#cbd5e1' }}>
          <div className="w-px h-4 bg-current" />
          <div className="w-4 h-px bg-current" />
          <div className="w-px h-4 bg-current" />
        </div>
        <div className="flex items-center gap-1">
          {slot('E', 'w-12 h-8')}
          <CompassLabel seat="E" game={game} />
        </div>
      </div>

      <div className="flex flex-col items-center gap-0.5">
        {slot('S', 'h-8')}
        <CompassLabel seat="S" game={game} />
      </div>

      {label && (
        <div className="mt-2 text-center">
          <div className="text-[0.65rem] uppercase tracking-widest" style={{ color: '#64748b' }}>
            contract
          </div>
          <div className="text-base font-bold leading-tight" style={{ color: '#1e293b' }}>{label}</div>
          {game.declarer && (
            <div className="text-xs" style={{ color: '#64748b' }}>by {game.declarer}</div>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  game: GameState
  playInfo: PlayInfo | null
  analysis: AnalysisMap | null
  /** The seat whose decisions are being graded, marked on the table. */
  gradedSeat?: Seat | null
}

export default function PlayTable({ game, playInfo, analysis, gradedSeat = null }: Props) {
  const cell = (seat: Seat) => (
    <Hand
      seat={seat}
      game={game}
      played={playInfo?.playedByPlayer[seat]}
      analysis={analysis}
      graded={gradedSeat}
    />
  )

  return (
    <div className="flex flex-col items-center gap-2">
      {game.board && (
        <div className="text-sm font-semibold tracking-wide" style={{ color: '#475569' }}>
          {game.board}
        </div>
      )}
      <div
        className="grid grid-rows-3 gap-2 items-center justify-items-center"
        style={{ gridTemplateColumns: '1fr auto 1fr' }}
      >
        <div />
        {cell('N')}
        <div />

        {cell('W')}
        <Compass game={game} currentTrick={playInfo?.currentTrick} />
        {cell('E')}

        <div />
        {cell('S')}
        <div />
      </div>
    </div>
  )
}
