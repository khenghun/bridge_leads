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
  graded: Seat[]
}) {
  const hand = game.hands[seat]
  if (!hand) return null
  const isDeclarer = game.declarer === seat
  const vul = isVulnerable(game.vulnerability, seat)

  return (
    <div
      className="flex flex-col gap-0.5 px-3 py-2 rounded-lg font-mono text-sm leading-tight"
      style={{
        background: isDeclarer ? 'var(--felt-hand-bg-declarer)' : 'var(--felt-hand-bg)',
        boxShadow: graded.includes(seat)
          ? '0 0 0 2px var(--accent)'
          : isDeclarer ? '0 0 0 1px var(--felt-hand-ring-declarer)' : '0 0 0 1px var(--felt-hand-ring)',
      }}
    >
      <div
        className="text-xs font-bold tracking-widest mb-1 text-center"
        style={{ color: vul ? 'var(--felt-vul)' : 'var(--felt-muted)' }}
      >
        {seat}
        {isDeclarer && <span className="ml-1 font-normal" style={{ color: 'var(--accent)' }}>(decl)</span>}
        {graded.includes(seat) && <span className="ml-1 font-normal" style={{ color: 'var(--accent)' }}>◆</span>}
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
              {ranks.length === 0 ? <span style={{ color: 'var(--felt-faded)' }}>—</span> : ranks.map((rank) => {
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
                      style={{ color: STATUS_COLOR[decision.status] ?? 'var(--felt-faded)' }}
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
                    style={{ color: isPlayed ? 'var(--felt-faded)' : SUIT_COLOR[letter] }}
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
        background: vul ? 'var(--felt-vul)' : 'var(--felt-seat-bg)',
        boxShadow: seat === game.dealer ? '0 0 0 2px var(--felt-dealer)' : undefined,
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
        <div className="flex flex-col items-center gap-0.5" style={{ color: 'var(--felt-lines)' }}>
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
          <div className="text-[0.65rem] uppercase tracking-widest" style={{ color: 'var(--felt-muted)' }}>
            contract
          </div>
          <div className="text-base font-bold leading-tight" style={{ color: 'var(--felt-text)' }}>{label}</div>
          {game.declarer && (
            <div className="text-xs" style={{ color: 'var(--felt-muted)' }}>by {game.declarer}</div>
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
  gradedSeats?: Seat[]
}

export default function PlayTable({ game, playInfo, analysis, gradedSeats = [] }: Props) {
  const cell = (seat: Seat) => (
    <Hand
      seat={seat}
      game={game}
      played={playInfo?.playedByPlayer[seat]}
      analysis={analysis}
      graded={gradedSeats}
    />
  )

  return (
    <div className="flex flex-col items-center gap-2">
      {game.board && (
        <div className="text-sm font-semibold tracking-wide" style={{ color: 'var(--felt-muted)' }}>
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
