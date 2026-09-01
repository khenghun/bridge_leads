/**
 * PlayViewer — trick-by-trick, card-by-card navigation over PlayTable.
 * Ported from bridge_ai/src/components/PlayViewer.jsx.
 *
 * Each completed trick takes FIVE navigation steps: its four cards, then a
 * pause with all four face up so you can see who won it before the table
 * clears. Step 0 is the start of play, with nothing on the table.
 *
 * The step lives in the parent (PlayApp) so clicking a graded decision can
 * jump the viewer to the moment that card was played.
 *
 * Keyboard (ignored while typing in an input):
 *   ← / →         previous / next card
 *   Shift+← / →   previous / next trick
 *   Home / End    start / end of play
 */
import { useEffect } from 'react'
import type { Seat } from '../../api/types'
import { CLOCKWISE, type GameState } from '../../lib/lin'
import PlayTable, { type AnalysisMap, type PlayInfo } from './PlayTable'

/** The step that shows the card at `cardIndex` as the last one played. */
export function stepForCard(cardIndex: number): number {
  return Math.floor(cardIndex / 4) * 5 + (cardIndex % 4) + 1
}

/** Total navigation steps for a play of `totalCards` cards. */
export function totalStepsFor(totalCards: number): number {
  return Math.floor(totalCards / 4) * 5 + (totalCards % 4)
}

function NavBtn({ onClick, disabled, title, children }: {
  onClick: () => void
  disabled: boolean
  title: string
  children: React.ReactNode
}) {
  return (
    <button className="play-navbtn" onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  )
}

interface Props {
  game: GameState
  step: number
  setStep: (next: number | ((prev: number) => number)) => void
  analysis: AnalysisMap | null
  gradedSeats?: Seat[]
}

export default function PlayViewer({ game, step, setStep, analysis, gradedSeats }: Props) {
  const { tricks, play } = game
  const totalCards = play.length
  const hasPlay = totalCards > 0
  const completeTricks = Math.floor(totalCards / 4)
  const totalSteps = totalStepsFor(totalCards)

  const s = Math.max(0, Math.min(step, totalSteps))

  // ── step → what is on the table ───────────────────────────────────────────
  let cardsShown = 0
  let isPause = false
  let activeTrickIdx = 0
  if (s > 0) {
    const completePhaseEnd = completeTricks * 5
    if (s <= completePhaseEnd) {
      activeTrickIdx = Math.floor((s - 1) / 5)
      const posInGroup = (s - 1) % 5
      isPause = posInGroup === 4
      cardsShown = activeTrickIdx * 4 + (isPause ? 4 : posInGroup + 1)
    } else {
      cardsShown = completeTricks * 4 + (s - completePhaseEnd)
      activeTrickIdx = completeTricks
    }
  }

  // ── trick-level jumps ─────────────────────────────────────────────────────
  function nextTrickStep(cur: number): number {
    if (cur >= totalSteps) return totalSteps
    if (cur <= 0) return completeTricks > 0 ? 5 : totalSteps
    if (cur > completeTricks * 5) return totalSteps
    const group = Math.floor((cur - 1) / 5)
    const pause = (group + 1) * 5
    if (cur < pause) return Math.min(pause, totalSteps)
    return Math.min(pause + 5, totalSteps)
  }

  function prevTrickStep(cur: number): number {
    if (cur <= 0) return 0
    if (cur > completeTricks * 5) {
      const remStart = completeTricks * 5 + 1
      if (cur > remStart) return remStart
      return completeTricks > 0 ? completeTricks * 5 : 0
    }
    const group = Math.floor((cur - 1) / 5)
    const groupStart = group * 5 + 1
    if (cur > groupStart) return groupStart
    return group > 0 ? (group - 1) * 5 + 1 : 0
  }

  // ── keyboard ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!hasPlay) return
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'ArrowRight' && !e.shiftKey) {
        e.preventDefault(); setStep((v) => Math.min(v + 1, totalSteps))
      } else if (e.key === 'ArrowLeft' && !e.shiftKey) {
        e.preventDefault(); setStep((v) => Math.max(v - 1, 0))
      } else if (e.key === 'ArrowRight' && e.shiftKey) {
        e.preventDefault(); setStep(nextTrickStep)
      } else if (e.key === 'ArrowLeft' && e.shiftKey) {
        e.preventDefault(); setStep(prevTrickStep)
      } else if (e.key === 'Home') {
        e.preventDefault(); setStep(0)
      } else if (e.key === 'End') {
        e.preventDefault(); setStep(totalSteps)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPlay, totalSteps, completeTricks])

  // ── derived: played cards, current trick, running trick count ─────────────
  const playedByPlayer: Record<Seat, Set<string>> = {
    N: new Set(), E: new Set(), S: new Set(), W: new Set(),
  }
  for (let i = 0; i < cardsShown; i++) {
    const { player, suit, rank } = play[i]
    playedByPlayer[player].add(suit + rank)
  }

  const trickStart = activeTrickIdx * 4
  const currentCards = play.slice(trickStart, cardsShown)
  const currentLeader = tricks[activeTrickIdx]?.leader ?? null

  const completedForScore = isPause ? activeTrickIdx + 1 : activeTrickIdx
  let nsTricks = 0
  let ewTricks = 0
  for (let i = 0; i < completedForScore && i < tricks.length; i++) {
    const w = tricks[i].winner
    if (w === 'N' || w === 'S') nsTricks += 1
    else if (w === 'E' || w === 'W') ewTricks += 1
  }

  const trickTotal = Math.ceil(totalCards / 4)
  let label: string
  if (s === 0) {
    label = 'Start of play'
  } else if (isPause) {
    label = `Trick ${activeTrickIdx + 1}/${trickTotal} · won by ${tricks[activeTrickIdx]?.winner ?? '?'}`
    if (s >= totalSteps) label += ' · end'
  } else if (s >= totalSteps) {
    label = 'End of play'
  } else {
    const inTrick = cardsShown - trickStart
    const next = currentLeader
      ? CLOCKWISE[(CLOCKWISE.indexOf(currentLeader) + inTrick) % 4]
      : '?'
    label = `Trick ${activeTrickIdx + 1}/${trickTotal} · card ${inTrick}/4 · ${next} to play`
  }

  const playInfo: PlayInfo | null = hasPlay
    ? { playedByPlayer, currentTrick: { cards: currentCards, leader: currentLeader } }
    : null

  return (
    <div className="flex flex-col items-center gap-3">
      {hasPlay && (
        <div className="flex items-center gap-3 text-sm" style={{ color: 'var(--felt-muted)' }}>
          <span>N–S <b className="tabular-nums" style={{ color: 'var(--felt-strong)' }}>{nsTricks}</b></span>
          <span className="text-xs font-mono" style={{ color: 'var(--felt-muted)' }}>{label}</span>
          <span>E–W <b className="tabular-nums" style={{ color: 'var(--felt-strong)' }}>{ewTricks}</b></span>
        </div>
      )}

      <PlayTable game={game} playInfo={playInfo} analysis={analysis} gradedSeats={gradedSeats} />

      {hasPlay ? (
        <div className="flex flex-col items-center gap-1.5 mt-1">
          <div className="flex items-center gap-1">
            <NavBtn onClick={() => setStep(0)} disabled={s === 0} title="Start (Home)">|◀</NavBtn>
            <NavBtn onClick={() => setStep(prevTrickStep)} disabled={s === 0} title="Previous trick (Shift+←)">◀◀</NavBtn>
            <NavBtn onClick={() => setStep((v) => Math.max(v - 1, 0))} disabled={s === 0} title="Previous card (←)">◀</NavBtn>
            <span
              className="px-2 text-xs font-mono w-14 text-center tabular-nums"
              style={{ color: 'var(--felt-muted)' }}
            >
              {cardsShown}/{totalCards}
            </span>
            <NavBtn onClick={() => setStep((v) => Math.min(v + 1, totalSteps))} disabled={s >= totalSteps} title="Next card (→)">▶</NavBtn>
            <NavBtn onClick={() => setStep(nextTrickStep)} disabled={s >= totalSteps} title="Next trick (Shift+→)">▶▶</NavBtn>
            <NavBtn onClick={() => setStep(totalSteps)} disabled={s >= totalSteps} title="End (End)">▶|</NavBtn>
          </div>
          <div className="text-xs" style={{ color: 'var(--felt-muted)' }}>
            ← → cards · Shift+← → tricks · Home / End
          </div>
        </div>
      ) : (
        <div className="text-sm" style={{ color: 'var(--felt-muted)' }}>
          This hand has no recorded play — there is nothing to step through or grade.
        </div>
      )}
    </div>
  )
}
