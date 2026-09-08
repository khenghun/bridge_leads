/**
 * PlayApp — the play solver: load a completed hand, step through the recorded
 * play, and grade every decision a pair — or the whole table — made.
 *
 * Composed from bridge_ai/src/App.jsx's upload and display screens, with the
 * tab bar, the BBO tab and the chatbot dropped. LIN is parsed here in the
 * browser (lib/lin.ts); the API only ever sees structured state.
 *
 * One Analyze press is a plan of one to three seats (see analysis.ts). The
 * requests go out one after another — each is a DDS batch that would only
 * queue behind the server's global lock anyway — and every result renders as
 * it lands, so a three-seat analysis shows its first grades as early as a
 * single seat used to.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Quality, Seat, Suit } from '../../api/types'
import type { AnalyzeResponse, Decision, ExpertOptions, PlayMethod } from '../../api/playTypes'
import { analyzePlay } from '../../api/play'
import {
  SEATS, SEAT_NAME, applyQuality, dummySeat, fixedCardIssues,
} from '../../lib/bridge'
import {
  handSize, handToPbn, isAnalyzable, parseLIN, toAnalyzeRequest, type GameState,
} from '../../lib/lin'
import ConstraintsEditor, {
  defaultSeatConstraint, type SeatConstraint,
} from '../../components/ConstraintsEditor'
import Changelog from '../../components/Changelog'
import AnalysisPanel, {
  buildAnalysisMap, type AnalysisPlan, type SeatStatus, type Selection,
} from './AnalysisPanel'
import {
  DEFAULT_DEALS, ESCALATION_FACTOR, EXPERT_DEALS, EXPERT_DEFAULTS, PAIR_LABEL, chunkByDecision, constrainableSeats,
  constraintsExcludeHand, constraintsForView, decisionIndices, hiddenFrom, mergeChunks,
  mergeDecisions, pairRole, pairsFor, pinnedCardsNotHeld, seatsToGrade, withRetry,
  type AnalysisAction, type Pair,
} from './analysis'
import AuctionGrid from './AuctionGrid'
import { RELEASES } from './changelog/releases'
import { EXAMPLES } from './examples'
import PlayViewer, { stepForCard, totalStepsFor } from './PlayViewer'

/** The lead/contract simulator, a separate product on its own domain. */
const LEAD_APP_URL = 'https://bridge-leads.icycookie.xyz'

function defaultConstraints(): Record<Seat, SeatConstraint> {
  return Object.fromEntries(
    SEATS.map((s) => [s, defaultSeatConstraint()]),
  ) as Record<Seat, SeatConstraint>
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
        <button className="btn btn-primary" style={{ margin: '0.6rem 0' }}
          disabled={!pasted.trim()} onClick={() => onLoad(pasted)}>
          Load this hand
        </button>
      </div>

      <div className="w-full max-w-xl mt-4" data-examples>
        <p className="caption" style={{ margin: '0 0 0.4rem' }}>Or start from an example hand:</p>
        <div className="flex flex-col gap-1">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.id}
              className="play-seat-btn play-example-btn"
              data-example={ex.id}
              onClick={() => onLoad(ex.lin)}
              title={ex.blurb}
            >
              <span style={{ fontWeight: 600 }}>{ex.title}</span>
              <span style={{ color: 'var(--muted)', fontSize: '0.78rem' }}>{ex.blurb}</span>
            </button>
          ))}
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

const ACTIONS: AnalysisAction[] = ['NS', 'EW', 'table']

export default function PlayApp() {
  const [light, setLight] = useState(false)
  const [whatsNew, setWhatsNew] = useState(false)
  const [game, setGame] = useState<GameState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [action, setAction] = useState<AnalysisAction>('NS')
  const [method, setMethod] = useState<PlayMethod>('single_dummy')
  const [numDeals, setNumDeals] = useState(DEFAULT_DEALS)
  const [constraints, setConstraints] = useState<Record<Seat, SeatConstraint>>(defaultConstraints)
  // Expert opponents (v1.3): the toggle, its knobs, and the Advanced disclosure.
  const [expert, setExpert] = useState(false)
  const [expertOpts, setExpertOpts] = useState<ExpertOptions>(EXPERT_DEFAULTS)
  // Sample-size escalation (v1.4): on by default, ×3 deals for a decision in doubt.
  const [escalate, setEscalate] = useState(true)
  const [advanced, setAdvanced] = useState(false)
  // Per-seat "trick 5 of 13" while a chunked analysis is arriving.
  const [progress, setProgress] = useState<Partial<Record<Seat, string>>>({})

  const [plan, setPlan] = useState<AnalysisPlan | null>(null)
  const [results, setResults] = useState<Partial<Record<Seat, AnalyzeResponse>>>({})
  const [statuses, setStatuses] = useState<Partial<Record<Seat, SeatStatus>>>({})
  const [errors, setErrors] = useState<Partial<Record<Seat, string>>>({})
  const [loading, setLoading] = useState(false)
  // Bumped whenever a run must be abandoned (new hand, new run); a loop that
  // finds itself stale stops writing state.
  const runRef = useRef(0)
  // What an interrupted run still owes, so Resume can pick it up: the
  // settings it was started with, and per seat the chunks done and left.
  interface Pending {
    signature: string
    seats: Seat[]
    parts: Partial<Record<Seat, AnalyzeResponse[]>>
    remaining: Partial<Record<Seat, Array<number[] | undefined>>>
  }
  const pendingRef = useRef<Pending | null>(null)
  const [canResume, setCanResume] = useState(false)

  const [step, setStep] = useState(0)
  const [selected, setSelected] = useState<Selection | null>(null)

  useEffect(() => { document.body.classList.toggle('light', light) }, [light])

  const clearAnalysis = () => {
    runRef.current += 1
    pendingRef.current = null
    setCanResume(false)
    setPlan(null); setResults({}); setStatuses({}); setErrors({}); setProgress({})
    setLoading(false); setSelected(null)
  }

  /** The toggle swaps the deal-count default with it: 30 is what the filter
   * needs to be worth running; 20 is the plain default. A count the user has
   * set to anything else is left alone. */
  const toggleExpert = (on: boolean) => {
    setExpert(on)
    if (on && numDeals === DEFAULT_DEALS) setNumDeals(EXPERT_DEALS)
    if (!on && numDeals === EXPERT_DEALS) setNumDeals(DEFAULT_DEALS)
  }
  const setExpertOpt = <K extends keyof ExpertOptions>(key: K, value: ExpertOptions[K]) => {
    setExpertOpts((prev) => ({ ...prev, [key]: value }))
  }

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
    clearAnalysis()
    setStep(0)
    setConstraints(defaultConstraints())
  }

  const reset = () => {
    setGame(null); setLoadError(null); clearAnalysis()
  }

  const setConstraint = (s: Seat, v: SeatConstraint) => {
    setConstraints((prev) => ({ ...prev, [s]: v }))
  }
  const setQuality = (s: Seat, suit: Suit, level: Quality | '') => {
    setConstraints((prev) => applyQuality(prev, s, suit, level))
  }

  const analysis = useMemo(
    () => (plan ? buildAnalysisMap(mergeDecisions(results)) : null), [plan, results],
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
  const contractText = game.contract
    ? `${game.contract.level}${game.contract.suit}${game.contract.doubled === 1 ? 'X' : game.contract.doubled === 2 ? 'XX' : ''}`
    : ''

  // Constraints are per hand — what the auction revealed — and every request
  // takes the slice its graded seat cannot see. Dummy is visible to every
  // view, so it is never offered.
  const editorSeats: Array<[Seat, string]> = declarer
    ? constrainableSeats(declarer).map((s) => [s, s === declarer ? '  (declarer)' : '  (defender)'])
    : []
  const cardIssues = fixedCardIssues(editorSeats.map(([s]) => s), constraints, [])
  const excluded: Array<[Seat, string[]]> = []
  for (const [s] of editorSeats) {
    const pbn = handToPbn(game.hands[s])
    const notHeld = pinnedCardsNotHeld(constraints[s], pbn)
    if (notHeld.length) {
      const msg = `${notHeld.join(' ')} not in ${SEAT_NAME[s]}’s actual hand`
      cardIssues[s] = cardIssues[s] ? `${cardIssues[s]}; ${msg}` : msg
    }
    const reasons = constraintsExcludeHand(constraints[s], pbn)
    if (reasons.length) excluded.push([s, reasons])
  }
  const hasCardIssue = Object.keys(cardIssues).length > 0

  /** The settings a run is made of — a resume must match them exactly. */
  const runSignature = () => JSON.stringify({
    action, method, numDeals, expert, expertOpts, escalate, constraints, play: game?.play.length,
  })

  /** Start an analysis, or — with `resume` — continue the interrupted one.
   *
   * Expert opponents is slow by nature, so its requests go out one decision
   * at a time and the table fills in as each lands (`decisions` chunks,
   * merged here); the plain run stays a single request per seat. A request
   * that fails on the network is retried, because the server keeps computing
   * after the client drops and caches every chunk — so a retry, or a Resume
   * after the browser gave up (a sleeping laptop, a throttled tab), mostly
   * collects answers that are already there. A screen wake-lock is held for
   * the duration where the browser allows it. */
  async function runAnalysis(resume = false) {
    if (!game || !declarer) return
    const signature = runSignature()
    const pending = resume && pendingRef.current?.signature === signature ? pendingRef.current : null
    const run = ++runRef.current
    const seats = pending?.seats ?? seatsToGrade(action, declarer)
    if (!pending) {
      setPlan({ action, declarer, pairs: pairsFor(action, declarer), seats })
      setResults({})
      setStatuses(Object.fromEntries(seats.map((s) => [s, 'queued'])))
      setSelected(null)
      pendingRef.current = { signature, seats, parts: {}, remaining: {} }
    }
    const state = pendingRef.current!
    setErrors({})
    setProgress({})
    setCanResume(false)
    setLoading(true)
    let wakeLock: { release: () => Promise<void> } | null = null
    try {
      wakeLock = await (navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } })
        .wakeLock?.request('screen') ?? null
    } catch { /* not available (hidden tab, http, old browser) — carry on */ }

    const expertOn = expert && method === 'single_dummy'
    let interrupted = false
    try {
      for (const seat of seats) {
        if (runRef.current !== run) return
        if (state.remaining[seat]?.length === 0) continue          // finished before the interruption
        setStatuses((prev) => ({ ...prev, [seat]: 'solving' }))
        try {
          const options = {
            method, numDeals,
            constraints: constraintsForView(constraints, hiddenFrom(seat, declarer)),
            expert: expertOn ? expertOpts : null,
            expertConstraints: expertOn
              ? constraintsForView(constraints, constrainableSeats(declarer)) : undefined,
            escalation: escalate ? { factor: ESCALATION_FACTOR } : null,
          }
          if (!state.remaining[seat]) {
            const chunks: Array<number[] | undefined> = expertOn
              ? chunkByDecision(decisionIndices(game.play, seat, declarer)) : []
            if (!chunks.length) chunks.push(undefined)
            state.remaining[seat] = chunks
            state.parts[seat] = []
          }
          const parts = state.parts[seat]!
          const total = parts.length + state.remaining[seat]!.length
          while (state.remaining[seat]!.length) {
            const decisions = state.remaining[seat]![0]
            const res = await withRetry(() =>
              analyzePlay(toAnalyzeRequest(game, seat, { ...options, decisions })))
            if (runRef.current !== run) return
            parts.push(res)
            state.remaining[seat]!.shift()
            const merged = total > 1 ? mergeChunks(parts)! : res
            setResults((prev) => ({ ...prev, [seat]: merged }))
            if (total > 1 && state.remaining[seat]!.length) {
              setProgress((prev) => ({ ...prev, [seat]: `decision ${parts.length} of ${total} done` }))
            }
          }
          setProgress((prev) => ({ ...prev, [seat]: undefined }))
          setStatuses((prev) => ({ ...prev, [seat]: 'done' }))
        } catch (e) {
          if (runRef.current !== run) return
          interrupted = true
          setErrors((prev) => ({ ...prev, [seat]: `${(e as Error).message} — what was graded is kept; press Resume to continue.` }))
          setStatuses((prev) => ({ ...prev, [seat]: 'failed' }))
          break
        }
      }
    } finally {
      try { await wakeLock?.release() } catch { /* ignore */ }
    }
    setCanResume(interrupted)
    if (!interrupted) pendingRef.current = null
    setLoading(false)
  }

  const jumpTo = (seat: Seat, decision: Decision, index: number) => {
    setSelected({ seat, index })
    setStep(Math.min(stepForCard(decision.index), totalStepsFor(game.play.length)))
  }

  const actionLabel = (a: AnalysisAction): [string, string] => {
    if (a === 'table') return ['Whole table', declarer ? `${seatsToGrade(a, declarer).length} grades` : '']
    const pair = a as Pair
    if (!declarer) return [PAIR_LABEL[pair], '']
    return [
      PAIR_LABEL[pair],
      pairRole(pair, declarer) === 'declarer' ? `declaring ${contractText}` : 'defending',
    ]
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
            Contract <b style={{ color: 'var(--text)' }}>{contractText}</b> by {declarer}
          </span>
        )}
        <span>{game.play.length} cards played</span>
      </div>

      <div className="layout">
        <aside className="sidebar">
          <h2 style={{ marginTop: 0 }}>Analyze</h2>
          {!analyzable && (
            <div className="banner banner-error">
              {game.play.length === 0
                ? 'This hand has no recorded play, so there is nothing to grade.'
                : 'This hand did not parse to a complete deal and contract.'}
            </div>
          )}

          <div className="flex flex-col gap-0.5 my-2" role="radiogroup" aria-label="Who to analyze">
            {ACTIONS.map((a) => {
              const [label, sub] = actionLabel(a)
              return (
                <button
                  key={a}
                  className={`play-seat-btn${action === a ? ' on' : ''}`}
                  disabled={!analyzable || loading}
                  onClick={() => setAction(a)}
                  data-action={a}
                >
                  <input type="radio" readOnly checked={action === a} disabled={!analyzable || loading} />
                  <span>{label}</span>
                  <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>{sub}</span>
                </button>
              )
            })}
          </div>
          <p className="caption tiny">
            A pair is graded as a pair: the declaring side through declarer
            (dummy{dummy ? ` — ${SEAT_NAME[dummy]} —` : ''} makes no decisions),
            the defending side through each defender on what they could see.
          </p>

          <h2>Method</h2>
          <div className="seg">
            <button className={method === 'single_dummy' ? 'on' : ''}
              onClick={() => setMethod('single_dummy')}>
              Single dummy
            </button>
            <button className={method === 'double_dummy' ? 'on' : ''}
              onClick={() => setMethod('double_dummy')}>
              Double dummy
            </button>
          </div>
          <p className="caption tiny">
            {method === 'single_dummy'
              ? 'Samples the two hands each graded seat could not see and solves every candidate card on each — “what was best given what you knew”.'
              : 'Grades against the actual deal: one solve per decision, no sampling — hindsight’s answer, and much faster.'}
          </p>

          {method === 'single_dummy' && (
            <label className="field">
              Deals per decision: <b>{numDeals}</b>
              <input
                type="range" min={5} max={200} step={5} value={numDeals}
                onChange={(e) => setNumDeals(Number(e.target.value))}
              />
              <span className="caption tiny" style={{ margin: 0 }}>
                Every decision is its own batch, so cost is roughly deals ×
                decisions × seats — 200 deals over a whole table runs for many minutes.
              </span>
            </label>
          )}

          {method === 'single_dummy' && (
            <div className="field" data-escalation>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={escalate} onChange={(e) => setEscalate(e.target.checked)} />
                <span>Spend more deals on doubtful grades (×{ESCALATION_FACTOR})</span>
              </label>
              <span className="caption tiny" style={{ margin: 0 }}>
                Every grade carries its sampling error. A decision that does not read clearly
                optimal — or whose grade could flip on another sample of this size — is re-graded
                on {ESCALATION_FACTOR}× the deals{expert ? ', at most 300' : ', at most 600'}; the
                rest cost nothing extra. A grade that is still a judgement call is marked{' '}
                <span className="play-badge marginal" style={{ color: 'var(--status-good)' }}>~ good ?</span>.
              </span>
            </div>
          )}

          {method === 'single_dummy' && (
            <div className="field" data-expert>
              <label className="flex items-center gap-2" style={{ cursor: 'pointer' }}>
                <input type="checkbox" checked={expert} onChange={(e) => toggleExpert(e.target.checked)} />
                <b>Expert opponents</b>
              </label>
              <span className="caption tiny" style={{ margin: 0 }}>
                Assumes the opponents found the best play at every earlier turn,
                judged by what they could see — sampled deals on which an earlier
                play of theirs was clearly wrong are thrown out. Much slower:
                minutes per seat, arriving trick by trick.
              </span>
              {expert && (
                <>
                  <button
                    type="button" className="btn btn-small" style={{ alignSelf: 'flex-start' }}
                    onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}
                  >
                    {advanced ? '▾' : '▸'} Advanced
                  </button>
                  {advanced && (
                    <div className="flex flex-col gap-1.5 text-xs" data-expert-advanced>
                      <label className="flex items-center gap-2" style={{ cursor: 'pointer' }}>
                        <input type="checkbox" checked={expertOpts.strict}
                          onChange={(e) => setExpertOpt('strict', e.target.checked)} />
                        <span>
                          <b>Strict</b> — judge every opponent decision, not only the ones
                          that lost a trick on the sampled deal. Several times slower; the
                          only way to catch a play that happened to work.
                        </span>
                      </label>
                      <label className="flex items-center gap-2">
                        <span style={{ minWidth: '9rem' }}>Margin (tricks)</span>
                        <input type="number" min={0} max={1} step={0.05} value={expertOpts.tolerance}
                          style={{ width: '5rem' }}
                          onChange={(e) => setExpertOpt('tolerance', Number(e.target.value))} />
                      </label>
                      <label className="flex items-center gap-2">
                        <span style={{ minWidth: '9rem' }}>Confidence (σ)</span>
                        <input type="number" min={1} max={4} step={0.5} value={expertOpts.confidence}
                          style={{ width: '5rem' }}
                          onChange={(e) => setExpertOpt('confidence', Number(e.target.value))} />
                      </label>
                      <label className="flex items-center gap-2">
                        <span style={{ minWidth: '9rem' }}>Inner sample ratio</span>
                        <input type="number" min={0.1} max={1} step={0.1} value={expertOpts.inner_ratio}
                          style={{ width: '5rem' }}
                          onChange={(e) => setExpertOpt('inner_ratio', Number(e.target.value))} />
                      </label>
                      <span className="caption tiny" style={{ margin: 0 }}>
                        A play is rejected only when an alternative is shown better by
                        more than the margin plus the sampling noise — at {numDeals} deals
                        that is about{' '}
                        {(expertOpts.tolerance + expertOpts.confidence * 0.6
                          / Math.sqrt(Math.max(8, Math.round(expertOpts.inner_ratio * numDeals)))).toFixed(2)}{' '}
                        tricks. Raise the deal count to tighten it.
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {declarer && (
            <ConstraintsEditor
              seats={editorSeats}
              constraints={constraints}
              setConstraint={setConstraint}
              setQuality={setQuality}
              cardIssues={cardIssues}
            />
          )}
          {excluded.length > 0 && (
            <div className="banner" data-excludes-deal
              style={{ background: 'var(--info-bg)', fontSize: '0.78rem', margin: '0.4rem 0' }}>
              <b>These constraints rule out the hand actually held</b>, so every
              sampled deal would be one that did not happen:
              <ul style={{ margin: '0.3rem 0 0 1rem', padding: 0 }}>
                {excluded.map(([s, reasons]) => (
                  <li key={s}>{SEAT_NAME[s]}: {reasons.join('; ')}</li>
                ))}
              </ul>
            </div>
          )}

          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            disabled={loading || !analyzable || hasCardIssue}
            onClick={() => runAnalysis(false)}
          >
            {loading ? <><span className="play-spinner" /> Analyzing…</> : 'Analyze'}
          </button>
          {canResume && !loading && (
            <button
              className="btn"
              style={{ width: '100%', marginTop: '0.4rem' }}
              onClick={() => runAnalysis(true)}
              data-resume
            >
              ▶ Resume — continue where it stopped
            </button>
          )}
          {hasCardIssue && (
            <p className="err">Fix the pinned cards above before analyzing.</p>
          )}
        </aside>

        <main className="content" style={{ maxWidth: '1400px' }}>
          <div className="flex flex-col xl:flex-row gap-4 items-start">
            <div className="play-felt flex-shrink-0">
              <PlayViewer
                game={game} step={step} setStep={setStep}
                analysis={analysis} gradedSeats={plan?.seats ?? []}
              />
            </div>

            <div className="flex flex-col gap-4 w-full xl:w-auto xl:min-w-[22rem] xl:max-w-[30rem]">
              <div className="play-panel">
                <h2 className="play-panel-title">Auction</h2>
                <AuctionGrid game={game} />
              </div>
              <AnalysisPanel
                plan={plan}
                results={results}
                statuses={statuses}
                progress={progress}
                errors={errors}
                contractText={contractText}
                selected={selected}
                onSelect={jumpTo}
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

/** The play solver's current version — the newest *released* entry of its
 * own changelog. An entry still flagged `unreleased` is in development and
 * must not be claimed in the header (the deployed-site checks read it). */
const CURRENT_VERSION = RELEASES.find((r) => !r.unreleased)?.version ?? ''

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
