/**
 * PlayApp — the play solver: load a completed hand, step through the recorded
 * play, and grade every decision one seat made.
 *
 * Composed from bridge_ai/src/App.jsx's upload and display screens, with the
 * tab bar, the BBO tab and the chatbot dropped. LIN is parsed here in the
 * browser (lib/lin.ts); the API only ever sees structured state.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Constraints, Quality, Seat, Suit } from '../../api/types'
import type { AnalyzeResponse, Decision, PlayMethod } from '../../api/playTypes'
import { analyzePlay } from '../../api/play'
import {
  SEAT_NAME, SEATS, SUITS, applyQuality, dummySeat, fixedCardIssues,
  holdingsToCards, leaderSeat, partnerSeat,
} from '../../lib/bridge'
import {
  SUIT_NAMES, SUIT_OF, handSize, isAnalyzable, parseLIN, toAnalyzeRequest,
  type GameState,
} from '../../lib/lin'
import ConstraintsEditor, {
  defaultSeatConstraint, type SeatConstraint,
} from '../../components/ConstraintsEditor'
import Changelog from '../../components/Changelog'
import AnalysisPanel, { buildAnalysisMap } from './AnalysisPanel'
import AuctionGrid from './AuctionGrid'
import { RELEASES } from './changelog/releases'
import PlayViewer, { stepForCard, totalStepsFor } from './PlayViewer'

/** The lead/contract simulator, a separate product on its own domain. */
const LEAD_APP_URL = 'https://bridge-leads.icycookie.xyz'

/** Board 17 from the source repo's own test fixture
 * (bridge_ai/tests/test_bridge_tools.py) — 1NT by West, nine tricks recorded,
 * player names replaced with the seat they sat in. Small enough to grade
 * quickly, and it has both a defensive and a declarer story. */
const EXAMPLE_LIN = (
  'pn|South,West,North,East|st||'
  + 'md|3SKT3HJT7D87CKQ843,SA54HQ94DT963CAT2,S9872HK85DAJ542C5,SQJ6HA632DKQCJ976|'
  + 'rh||ah|Board 17|sv|o|'
  + 'mb|p|mb|1C|mb|p|mb|1N|mb|p|mb|p|mb|p|pg||'
  + 'pc|S9|pc|SJ|pc|SK|pc|S5|pg||'
  + 'pc|ST|pc|S4|pc|S2|pc|SQ|pg||'
  + 'pc|C6|pc|C4|pc|CT|pc|C5|pg||'
  + 'pc|D3|pc|D5|pc|DQ|pc|D7|pg||'
  + 'pc|H2|pc|HT|pc|HQ|pc|HK|pg||'
  + 'pc|S8|pc|S6|pc|S3|pc|SA|pg||'
  + 'pc|H4|pc|H8|pc|H3|pc|H7|pg||'
  + 'pc|S7|pc|C7|pc|C3|pc|C2|pg||'
  + 'pc|DA|pc|DK|pc|D8|pc|D6|pg||'
  + 'pc|DJ|mc|7|'
)

function defaultConstraints(): Record<Seat, SeatConstraint> {
  return Object.fromEntries(
    SEATS.map((s) => [s, defaultSeatConstraint()]),
  ) as Record<Seat, SeatConstraint>
}

/** The hands the graded seat could see. Declarer sees dummy; a defender sees
 * dummy too (from trick one's second card onward). Everything else is
 * sampled — which is exactly what makes the grade "best given what you knew". */
export function visibleSeats(seat: Seat, declarer: Seat): Seat[] {
  const dummy = dummySeat(declarer)
  if (seat === declarer) return [declarer, dummy]
  return [seat, dummy]
}

/** The two hands the graded seat could NOT see, with a role label for the
 * constraint editor. Declaring: both defenders. Defending: declarer and your
 * own partner — dummy is face up, so it is never constrainable. */
export function unseenSeats(seat: Seat, declarer: Seat): Array<[Seat, string]> {
  if (seat === declarer) {
    const lho = leaderSeat(declarer)
    return [[lho, '  (opening leader)'], [partnerSeat(lho), '  (the other defender)']]
  }
  return [[declarer, '  (declarer)'], [partnerSeat(seat), '  (your partner)']]
}

/** Per-seat editor state → the API constraints dict, for the unseen seats only
 * (the backend 422s on a constraint aimed at a hand the grader can see). */
function buildConstraints(
  seats: Array<[Seat, string]>, state: Record<Seat, SeatConstraint>,
): Constraints {
  const out: Constraints = { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} }
  for (const [seat] of seats) {
    const c = state[seat]
    if (c.hcp[0] !== 0 || c.hcp[1] !== 40) out.hcp[seat] = c.hcp
    const lengths: Record<string, [number, number]> = {}
    for (const s of SUITS) {
      const [lo, hi] = c.suits[s]
      if (lo !== 0 || hi !== 13) lengths[s] = [lo, hi]
    }
    if (Object.keys(lengths).length) out.suit_length[seat] = lengths
    if (c.shape.trim()) out.shapes[seat] = c.shape
    const quality = Object.entries(c.quality).filter(([, level]) => level)
    if (quality.length) out.quality[seat] = Object.fromEntries(quality)
    const cards = holdingsToCards(c.cards)
    if (cards.length) out.fixed_cards[seat] = cards
  }
  return out
}

/** Every card held by the seats the graded player can see, in endplay form. */
function knownCards(game: GameState, seats: Seat[]): string[] {
  const out: string[] = []
  for (const seat of seats) {
    const hand = game.hands[seat]
    if (!hand) continue
    for (const name of SUIT_NAMES) {
      for (const rank of hand[name]) out.push(SUIT_OF[name] + rank)
    }
  }
  return out
}

// ── Upload screen ───────────────────────────────────────────────────────────

function UploadScreen({ onLoad }: { onLoad: (text: string) => void }) {
  const [dragging, setDragging] = useState(false)
  const [pasted, setPasted] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const readFile = useCallback((file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => onLoad(String(e.target?.result ?? ''))
    reader.onerror = () => onLoad('')
    reader.readAsText(file)
  }, [onLoad])

  return (
    <div className="flex flex-col items-center py-12 px-4">
      <p className="caption" style={{ marginBottom: '1.2rem' }}>
        Load a completed hand — a BBO <code>.lin</code> file — to step through
        the play and grade it.
      </p>

      <div
        className={`play-dropzone w-full max-w-xl flex flex-col items-center justify-center gap-3 py-14 px-8 select-none${dragging ? ' dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDrop={(e) => { e.preventDefault(); setDragging(false); readFile(e.dataTransfer.files[0]) }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
      >
        <div className="text-5xl">{dragging ? '📂' : '🃏'}</div>
        <div className="text-center">
          <p className="font-semibold">{dragging ? 'Drop to load' : 'Drop a .lin file here'}</p>
          <p className="caption" style={{ margin: 0 }}>or click to browse</p>
        </div>
        <input
          ref={inputRef} type="file" accept=".lin,text/plain" className="hidden"
          onChange={(e) => readFile(e.target.files?.[0] ?? undefined)}
        />
      </div>

      <div className="w-full max-w-xl mt-6">
        <label className="field">
          Or paste the LIN text
          <textarea
            rows={4} value={pasted} spellCheck={false}
            placeholder="pn|…|md|3S…|mb|p|…|pc|S9|…"
            onChange={(e) => setPasted(e.target.value)}
          />
        </label>
        <div className="flex gap-2 items-center">
          <button className="btn btn-primary" style={{ margin: '0.6rem 0' }}
            disabled={!pasted.trim()} onClick={() => onLoad(pasted)}>
            Load this hand
          </button>
          <button className="btn" onClick={() => onLoad(EXAMPLE_LIN)}>Load example</button>
        </div>
      </div>

      <p className="caption tiny" style={{ marginTop: '1rem' }}>
        The file is parsed in your browser. Only the deal, the contract and the
        play are sent for solving — never the file, and never the player names.
      </p>
    </div>
  )
}

// ── Display screen ──────────────────────────────────────────────────────────

const VUL_LABEL: Record<string, string> = { none: 'None', NS: 'N–S', EW: 'E–W', both: 'Both' }

export default function PlayApp() {
  const [light, setLight] = useState(false)
  const [whatsNew, setWhatsNew] = useState(false)
  const [game, setGame] = useState<GameState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [seat, setSeat] = useState<Seat>('S')
  const [method, setMethod] = useState<PlayMethod>('single_dummy')
  const [numDeals, setNumDeals] = useState(20)
  const [constraints, setConstraints] = useState<Record<Seat, SeatConstraint>>(defaultConstraints)

  const [result, setResult] = useState<AnalyzeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [step, setStep] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => { document.body.classList.toggle('light', light) }, [light])

  const load = (text: string) => {
    if (!text.trim()) { setLoadError('Could not read that file.'); return }
    const parsed = parseLIN(text)
    const short = SEATS.filter((s) => handSize(parsed.hands[s]) !== 13)
    if (short.length) {
      setLoadError(
        'That does not look like a BBO LIN hand — no complete deal in it'
        + ` (${short.join(', ')} came out short). Expected an md| field with three or four hands.`,
      )
      return
    }
    setLoadError(null)
    setGame(parsed)
    setSeat(parsed.declarer ?? 'S')
    setResult(null)
    setError(null)
    setStep(0)
    setSelected(null)
    setConstraints(defaultConstraints())
  }

  const reset = () => {
    setGame(null); setResult(null); setError(null); setLoadError(null)
  }

  const setConstraint = (s: Seat, v: SeatConstraint) => {
    setConstraints((prev) => ({ ...prev, [s]: v }))
  }
  const setQuality = (s: Seat, suit: Suit, level: Quality | '') => {
    setConstraints((prev) => applyQuality(prev, s, suit, level))
  }

  const analysis = useMemo(
    () => (result ? buildAnalysisMap(result.decisions) : null), [result],
  )

  if (!game) {
    return (
      <div className="play-shell">
        <Header light={light} setLight={setLight} whatsNew={whatsNew} setWhatsNew={setWhatsNew} />
        {whatsNew && <WhatsNew onClose={() => setWhatsNew(false)} />}
        {loadError && (
          <div className="banner banner-error" style={{ margin: '0.8rem auto', maxWidth: '40rem' }}>
            {loadError}
          </div>
        )}
        <UploadScreen onLoad={load} />
      </div>
    )
  }

  const declarer = game.declarer
  const dummy = declarer ? dummySeat(declarer) : null
  const analyzable = isAnalyzable(game) && game.play.length > 0
  const unseen = declarer ? unseenSeats(seat, declarer) : []
  const visible = declarer ? visibleSeats(seat, declarer) : []
  const cardIssues = fixedCardIssues(
    unseen.map(([s]) => s), constraints, knownCards(game, visible),
  )
  const hasCardIssue = Object.keys(cardIssues).length > 0

  const chooseSeat = (next: Seat) => {
    if (next === seat) return
    setSeat(next)
    // A grade belongs to one seat's view of the hand; keeping it after a switch
    // would silently mislabel every row.
    setResult(null)
    setSelected(null)
    setError(null)
  }

  async function runAnalysis() {
    if (!game || !declarer) return
    setLoading(true)
    setError(null)
    setSelected(null)
    try {
      const req = toAnalyzeRequest(game, seat, {
        method, numDeals, constraints: buildConstraints(unseen, constraints),
      })
      setResult(await analyzePlay(req))
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const jumpTo = (decision: Decision, index: number) => {
    setSelected(index)
    setStep(Math.min(stepForCard(decision.index), totalStepsFor(game.play.length)))
  }

  return (
    <div className="play-shell">
      <Header light={light} setLight={setLight} whatsNew={whatsNew} setWhatsNew={setWhatsNew} />
      {whatsNew && <WhatsNew onClose={() => setWhatsNew(false)} />}

      <div className="flex flex-wrap items-center gap-4 px-6 py-2 text-sm"
        style={{ borderBottom: '1px solid var(--border)', color: 'var(--muted)' }}>
        <button className="btn btn-small" onClick={reset}>← Load another hand</button>
        {game.board && <span style={{ color: 'var(--text)', fontWeight: 600 }}>{game.board}</span>}
        <span>Dealer <b style={{ color: 'var(--text)' }}>{game.dealer}</b></span>
        <span>
          Vul{' '}
          <b style={{ color: game.vulnerability === 'none' ? 'var(--text)' : 'var(--error)' }}>
            {VUL_LABEL[game.vulnerability]}
          </b>
        </span>
        {game.contract && declarer && (
          <span>
            Contract{' '}
            <b style={{ color: 'var(--text)' }}>
              {game.contract.level}
              {game.contract.suit}
              {game.contract.doubled === 1 ? 'X' : game.contract.doubled === 2 ? 'XX' : ''}
            </b>{' '}
            by {declarer}
          </span>
        )}
        <span>{game.play.length} cards played</span>
      </div>

      <div className="layout">
        <aside className="sidebar">
          <h2 style={{ marginTop: 0 }}>Grade a seat</h2>
          {!analyzable && (
            <div className="banner banner-error">
              {game.play.length === 0
                ? 'This hand has no recorded play, so there is nothing to grade.'
                : 'This hand did not parse to a complete deal and contract.'}
            </div>
          )}

          <div className="flex flex-col gap-0.5 my-2">
            {SEATS.map((s) => {
              const isDummy = s === dummy
              return (
                <button
                  key={s}
                  className={`play-seat-btn${seat === s ? ' on' : ''}`}
                  disabled={isDummy || !analyzable}
                  onClick={() => chooseSeat(s)}
                  title={isDummy
                    ? 'Dummy makes no decisions — its cards are graded as part of declarer.'
                    : undefined}
                >
                  <input type="radio" readOnly checked={seat === s} disabled={isDummy || !analyzable} />
                  <span>{SEAT_NAME[s]}</span>
                  <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>
                    {s === declarer ? 'declarer' : isDummy ? 'dummy' : 'defender'}
                  </span>
                </button>
              )
            })}
          </div>
          <p className="caption tiny">
            {seat === declarer
              ? 'Declarer is graded on both hands — the cards played from dummy are declarer’s decisions.'
              : 'A defender is graded on what they could see: their own hand and dummy.'}
          </p>

          <h2>Method</h2>
          <div className="seg">
            <button className={method === 'single_dummy' ? 'on' : ''}
              onClick={() => { setMethod('single_dummy'); setResult(null) }}>
              Single dummy
            </button>
            <button className={method === 'double_dummy' ? 'on' : ''}
              onClick={() => { setMethod('double_dummy'); setResult(null) }}>
              Double dummy
            </button>
          </div>
          <p className="caption tiny">
            {method === 'single_dummy'
              ? 'Samples the two hands this seat could not see and solves every candidate card on each — “what was best given what you knew”.'
              : 'Grades against the actual deal: one solve per decision, no sampling — hindsight’s answer, and much faster.'}
          </p>

          {method === 'single_dummy' && (
            <label className="field">
              Deals per decision: <b>{numDeals}</b>
              <input
                type="range" min={5} max={100} step={5} value={numDeals}
                onChange={(e) => setNumDeals(Number(e.target.value))}
              />
              <span className="caption tiny" style={{ margin: 0 }}>
                Every decision is its own batch, so cost is roughly deals ×
                decisions — 100 deals over a full hand runs for minutes.
              </span>
            </label>
          )}

          {declarer && (
            <ConstraintsEditor
              seats={unseen}
              constraints={constraints}
              setConstraint={setConstraint}
              setQuality={setQuality}
              cardIssues={cardIssues}
            />
          )}

          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            disabled={loading || !analyzable || hasCardIssue}
            onClick={runAnalysis}
          >
            {loading ? <><span className="play-spinner" /> Analyzing…</> : 'Analyze'}
          </button>
          {hasCardIssue && (
            <p className="err">Fix the pinned cards above before analyzing.</p>
          )}
        </aside>

        <main className="content" style={{ maxWidth: '1400px' }}>
          <div className="flex flex-col xl:flex-row gap-4 items-start">
            <div className="play-felt flex-shrink-0">
              <PlayViewer
                game={game} step={step} setStep={setStep}
                analysis={analysis} gradedSeat={result ? result.seat : seat}
              />
            </div>

            <div className="flex flex-col gap-4 w-full xl:w-auto xl:min-w-[22rem] xl:max-w-[30rem]">
              <div className="play-panel">
                <h2 className="play-panel-title">Auction</h2>
                <AuctionGrid game={game} />
              </div>
              <AnalysisPanel
                result={result}
                loading={loading}
                error={error}
                selected={selected}
                onSelect={(d) => {
                  const idx = result?.decisions.indexOf(d) ?? -1
                  jumpTo(d, idx)
                }}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

interface HeaderProps {
  light: boolean
  setLight: (v: boolean) => void
  whatsNew: boolean
  setWhatsNew: (v: boolean) => void
}

/** The play solver's current version — the newest entry of its own changelog. */
const CURRENT_VERSION = RELEASES[0]?.version ?? ''

function Header({ light, setLight, whatsNew, setWhatsNew }: HeaderProps) {
  return (
    <header className="topbar">
      <div className="flex items-baseline gap-3 flex-wrap">
        <strong style={{ fontSize: '1rem' }}>♣ Bridge Play Solver</strong>
        <a href={LEAD_APP_URL} style={{ color: 'var(--accent)', fontSize: '0.85rem' }}>
          Opening lead &amp; optimal contract →
        </a>
      </div>
      <div className="flex items-center gap-4">
        <button
          className={`btn btn-small${whatsNew ? ' on' : ''}`}
          onClick={() => setWhatsNew(!whatsNew)}
          aria-pressed={whatsNew}
          title="Release notes for the play solver"
        >
          What’s new {CURRENT_VERSION && <span style={{ color: 'var(--muted)' }}>· {CURRENT_VERSION}</span>}
        </button>
        <label className="toggle">
          <input type="checkbox" checked={light} onChange={(e) => setLight(e.target.checked)} />
          Light mode
        </label>
      </div>
    </header>
  )
}

/** The play solver's release notes — its own version line, separate from the
 * lead/contract app's. Static content, shown in place of nothing: it drops in
 * under the header without unloading the hand or a finished analysis. */
function WhatsNew({ onClose }: { onClose: () => void }) {
  return (
    <section className="play-panel mx-6 my-3" style={{ maxWidth: '52rem' }}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="play-panel-title" style={{ marginBottom: 0 }}>What’s new in the play solver</h2>
        <button className="btn btn-small" onClick={onClose}>Close</button>
      </div>
      <p className="caption" style={{ margin: '0.3rem 0 0.8rem' }}>
        Every release that changed something you can see, newest first. The
        play solver is versioned on its own — these are not the lead simulator’s notes.
      </p>
      <Changelog releases={RELEASES} />
    </section>
  )
}
