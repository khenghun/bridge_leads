import { useEffect, useMemo, useRef, useState } from 'react'
import type { Constraints, Mode, Quality, Seat, Suit } from '../../api/types'
import type { ContractRequest, ContractResponse } from '../../api/contractTypes'
import { simulateContracts } from '../../api/contract'
import {
  SEATS, SEAT_NAME, SUIT_COLOR, SUIT_SYMBOL, SUITS,
  applyQuality, describeSeatConstraints, fixedCardIssues, holdingError,
  holdingsToCards, holdingsToPbn, partnerSeat, strainLabel,
  type Holdings,
} from '../../lib/bridge'
import HandEntry from '../../components/HandEntry'
import ConstraintsEditor, {
  defaultSeatConstraint, seatStateFromConstraints, type SeatConstraint,
} from '../../components/ConstraintsEditor'
import ScenarioRecap from '../../components/ScenarioRecap'
import RunHistory from '../../components/RunHistory'
import {
  buildShareUrl, loadLastSetup, saveLastSetup, type SharePayload,
} from '../../lib/share'
import { parsePbn } from '../../lib/bridge'
import ContractResults from './ContractResults'

const HISTORY_CAP = 10

interface RunEntry {
  request: ContractRequest
  result: ContractResponse
  at: number
}
import StrainGrid from './StrainGrid'
import CompareContracts from './CompareContracts'
import ContractSampleDeals from './ContractSampleDeals'

const ALL_STRAINS = ['N', 'S', 'H', 'D', 'C']

/** Rough wall-clock estimate: a full double-dummy table costs ~45 ms/deal on a
 * 4-thread box, and each excluded strain shaves roughly a fifth off. */
function estimateSeconds(deals: number, strains: string[]): number {
  return (deals * 0.045 * (0.4 + 0.12 * strains.length))
}

function emptyHoldings(): Holdings {
  return { S: '', H: '', D: '', C: '' }
}

function defaultConstraints(): Record<Seat, SeatConstraint> {
  return Object.fromEntries(SEATS.map((s) => [s, defaultSeatConstraint()])) as Record<Seat, SeatConstraint>
}

/** The three hands we cannot see: partner first, then the opponents. */
function unseenSeats(seat: Seat): Array<[Seat, string]> {
  const i = SEATS.indexOf(seat)
  return [
    [partnerSeat(seat), '  (your partner)'],
    [SEATS[(i + 1) % 4], '  (LHO)'],
    [SEATS[(i + 3) % 4], '  (RHO)'],
  ]
}

function buildConstraints(seat: Seat, constraints: Record<Seat, SeatConstraint>): Constraints {
  const out: Constraints = { hcp: {}, suit_length: {}, shapes: {}, quality: {}, fixed_cards: {} }
  for (const [s] of unseenSeats(seat)) {
    const c = constraints[s]
    if (c.hcp[0] !== 0 || c.hcp[1] !== 40) out.hcp[s] = c.hcp
    const sl: Record<string, [number, number]> = {}
    for (const suit of SUITS) {
      const [lo, hi] = c.suits[suit]
      if (lo !== 0 || hi !== 13) sl[suit] = [lo, hi]
    }
    if (Object.keys(sl).length) out.suit_length[s] = sl
    if (c.shape.trim()) out.shapes[s] = c.shape
    const q = Object.entries(c.quality).filter(([, level]) => level)
    if (q.length) out.quality[s] = Object.fromEntries(q)
    const cards = holdingsToCards(c.cards)
    if (cards.length) out.fixed_cards[s] = cards
  }
  return out
}

interface Props {
  mode: Mode
  setMode: (m: Mode) => void
  /** A share-link payload for this tool, decoded by the shell at startup. */
  shared?: Extract<SharePayload, { tool: 'contract' }> | null
}

export default function ContractApp({ mode, setMode, shared }: Props) {
  const [seat, setSeat] = useState<Seat>('S')
  const [weVul, setWeVul] = useState(false)
  const [theyVul, setTheyVul] = useState(false)
  const [numDeals, setNumDeals] = useState(150)
  const [strains, setStrains] = useState<string[]>(ALL_STRAINS)
  const [holdings, setHoldings] = useState<Holdings>(emptyHoldings)
  const [constraints, setConstraints] = useState<Record<Seat, SeatConstraint>>(defaultConstraints)
  const [result, setResult] = useState<ContractResponse | null>(null)
  // The request that produced `result`, frozen at simulate time — the form may
  // have drifted since. Feeds the recap, the re-run button, and share links.
  const [lastRequest, setLastRequest] = useState<ContractRequest | null>(null)
  // This session's completed runs, newest first (in-memory by design), and the
  // last setup simulated on this device (offered once, never auto-applied).
  const [history, setHistory] = useState<RunEntry[]>([])
  const [storedSetup, setStoredSetup] = useState(() => (shared ? null : loadLastSetup('contract')))
  const [benchmark, setBenchmark] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A new result resets the benchmark to the engine's suggestion (the best
  // normal contract by mean score) — unless a share link asked for a specific
  // benchmark, which wins once, if the new result still offers it.
  const pendingBenchmark = useRef<string | null>(null)
  useEffect(() => {
    if (!result) return
    const wanted = pendingBenchmark.current
    pendingBenchmark.current = null
    if (wanted && result.candidates.some((c) => c.key === wanted)) setBenchmark(wanted)
    else if (result.default_benchmark) setBenchmark(result.default_benchmark)
  }, [result])

  /** Restore the whole form from a request (a share link opening, and later a
   * stored setup). The simulation itself runs from the request verbatim. */
  const applyRequest = (req: ContractRequest) => {
    const { holdings: h } = parsePbn(req.hand)
    if (h) setHoldings(h)
    setSeat(req.seat)
    const ns = req.seat === 'N' || req.seat === 'S'
    setWeVul(req.vul === 'both' || req.vul === (ns ? 'ns' : 'ew'))
    setTheyVul(req.vul === 'both' || req.vul === (ns ? 'ew' : 'ns'))
    setNumDeals(req.num_deals)
    setStrains(req.strains)
    setConstraints(seatStateFromConstraints(req.constraints))
  }

  // A shared link lands on the result, not on a form: populate and auto-run.
  useEffect(() => {
    if (!shared) return
    applyRequest(shared.request)
    if (shared.view?.benchmark) pendingBenchmark.current = shared.view.benchmark
    runRequest(shared.request)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shared])

  const partner = partnerSeat(seat)
  const weAreNS = seat === 'N' || seat === 'S'
  const vul = weVul && theyVul ? 'both'
    : weVul ? (weAreNS ? 'ns' : 'ew')
      : theyVul ? (weAreNS ? 'ew' : 'ns')
        : 'none'

  const setConstraint = (s: Seat, v: SeatConstraint) =>
    setConstraints((prev) => ({ ...prev, [s]: v }))
  const setQuality = (s: Seat, suit: Suit, level: Quality | '') =>
    setConstraints((prev) => applyQuality(prev, s, suit, level))

  const toggleStrain = (s: string) =>
    setStrains((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))

  const cardCount = SUITS.reduce((n, s) => n + holdings[s].length, 0)
  const handValid = useMemo(
    () => cardCount === 13 && !SUITS.some((s) => holdingError(holdings[s])),
    [holdings, cardCount],
  )
  // Pinned cards are checked against our own hand and each other here so the
  // user sees the clash while typing, not as a 422 after Simulate.
  const cardIssues = useMemo(
    () => fixedCardIssues(
      unseenSeats(seat).map(([s]) => s), constraints, holdingsToCards(holdings),
    ),
    [seat, constraints, holdings],
  )
  const canSimulate = handValid && strains.length > 0 && !Object.keys(cardIssues).length

  const runRequest = async (req: ContractRequest) => {
    setLoading(true)
    setError(null)
    try {
      const res = await simulateContracts(req)
      setResult(res)
      setLastRequest(req)
      const reqKey = JSON.stringify(req)
      setHistory((prev) => [
        { request: req, result: res, at: Date.now() },
        ...prev.filter((h) => JSON.stringify(h.request) !== reqKey),
      ].slice(0, HISTORY_CAP))
      saveLastSetup({ v: 1, tool: 'contract', request: req })
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
      setLastRequest(null)
    } finally {
      setLoading(false)
    }
  }

  const onSimulate = () => {
    if (!canSimulate) return
    runRequest({
      hand: holdingsToPbn(holdings),
      seat,
      vul,
      num_deals: numDeals,
      strains,
      constraints: buildConstraints(seat, constraints),
    })
  }

  // "Too close to call" escape hatch: the identical frozen request, more deals.
  const onRerun = (deals: number) => {
    if (!lastRequest) return
    setNumDeals(deals)
    runRequest({ ...lastRequest, num_deals: deals })
  }

  const shareUrl = () => buildShareUrl({
    v: 1, tool: 'contract', request: lastRequest!, view: { mode, benchmark },
  })

  // Flip the shown result back to a previous run: result, frozen request and
  // form all restore together, so recap/share/re-run stay consistent. The
  // benchmark re-resolves through the result effect above.
  const selectRun = (i: number) => {
    const entry = history[i]
    if (!entry) return
    setResult(entry.result)
    setLastRequest(entry.request)
    applyRequest(entry.request)
  }
  const activeRun = history.findIndex((h) => h.result === result)

  const runLabel = (h: RunEntry) => {
    const best = h.result.candidates.find((c) => c.key === h.result.default_benchmark)
    return `${SEAT_NAME[h.request.seat]} · ${h.request.num_deals} deals`
      + (best ? ` · ${best.label}` : '')
  }

  const VUL_TEXT: Record<string, string> = {
    none: 'none vul', both: 'both vul', ns: 'NS vul', ew: 'EW vul',
  }
  const recap = lastRequest && (
    <ScenarioRecap
      context={[
        `you sit ${SEAT_NAME[lastRequest.seat]}: ${lastRequest.hand}`,
        VUL_TEXT[lastRequest.vul] ?? lastRequest.vul,
        `${lastRequest.num_deals} deals`,
        ...(lastRequest.strains.length < ALL_STRAINS.length
          ? [`strains ${lastRequest.strains.map(strainLabel).join(' ')}`]
          : []),
      ]}
      seats={unseenSeats(lastRequest.seat).map(([s, label]) => ({
        seat: s,
        role: label.trim().replace(/[()]/g, ''),
        lines: describeSeatConstraints(lastRequest.constraints, s),
      }))}
    />
  )

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>Your seat</h2>
        <label className="field">
          You are
          <select value={seat} onChange={(e) => setSeat(e.target.value as Seat)}>
            {SEATS.map((s) => <option key={s} value={s}>{SEAT_NAME[s]}</option>)}
          </select>
        </label>

        <h2>Vulnerability</h2>
        <div className="row">
          <label className="toggle">
            <input type="checkbox" checked={weVul} onChange={(e) => setWeVul(e.target.checked)} />
            We
          </label>
          <label className="toggle">
            <input type="checkbox" checked={theyVul} onChange={(e) => setTheyVul(e.target.checked)} />
            They
          </label>
        </div>

        <h2>Scoring</h2>
        <div className="seg">
          <button className={mode === 'matchpoints' ? 'on' : ''} onClick={() => setMode('matchpoints')}>
            Matchpoints
          </button>
          <button className={mode === 'imps' ? 'on' : ''} onClick={() => setMode('imps')}>
            IMPs
          </button>
        </div>

        <h2>Simulation</h2>
        <label className="field">
          Deals to simulate: <b>{numDeals}</b>
          <input type="range" min={50} max={500} step={50} value={numDeals}
            onChange={(e) => setNumDeals(Number(e.target.value))} />
        </label>
        <p className="caption tiny">
          ≈ {estimateSeconds(numDeals, strains).toFixed(0)} s — a full double-dummy
          table per deal costs about five times a single lead solve.
        </p>

        <h2>Strains to consider</h2>
        <div className="chips">
          {ALL_STRAINS.map((s) => {
            const color = s === 'N' ? undefined : SUIT_COLOR[s as Suit]
            const on = strains.includes(s)
            const name = s === 'N' ? 'notrump' : SUIT_SYMBOL[s as Suit]
            return (
              <button key={s}
                className={`chip chip-toggle${on ? ' chip-selected' : ''}`}
                style={{ color, borderColor: on && color ? color : undefined }}
                aria-pressed={on}
                title={`${on ? 'Exclude' : 'Include'} ${name}`}
                onClick={() => toggleStrain(s)}>
                {s === 'N' ? 'NT' : SUIT_SYMBOL[s as Suit]}
              </button>
            )
          })}
        </div>
        <p className="caption tiny">
          Dropping strains you would never play speeds the solve up.
        </p>
      </aside>

      <main className="content">
        <h1>Optimal Contract Calculator</h1>
        <p className="caption">
          Where do these two hands belong? Monte-Carlo + double-dummy. No AI —
          pure simulation.
        </p>

        <div className="banner banner-info">
          You sit <b>{SEAT_NAME[seat]}</b>, partner is <b>{SEAT_NAME[partner]}</b>.
          Describe partner's hand (and the opponents', if the auction told you
          something) below — every contract is then ranked by how it would score.
        </div>
        {strains.length === 0 && (
          <div className="banner banner-error">Pick at least one strain to consider.</div>
        )}

        <HandEntry seat={seat} role="your hand" holdings={holdings} setHoldings={setHoldings} />
        <ConstraintsEditor seats={unseenSeats(seat)} constraints={constraints}
          setConstraint={setConstraint} setQuality={setQuality} cardIssues={cardIssues} />

        <button className="btn btn-primary" disabled={!canSimulate || loading} onClick={onSimulate}>
          {loading ? `Simulating ${numDeals} deals…` : 'Find the best contract'}
        </button>

        {storedSetup && !result && !loading && (
          <p className="caption">
            Last time on this device: seat {SEAT_NAME[storedSetup.request.seat]},{' '}
            {storedSetup.request.num_deals} deals.{' '}
            <button className="btn btn-small"
              onClick={() => { applyRequest(storedSetup.request); setStoredSetup(null) }}>
              ↩ Restore last setup
            </button>
          </p>
        )}

        {error && <div className="banner banner-error">{error}</div>}

        <RunHistory items={history.map((h) => ({ at: h.at, label: runLabel(h) }))}
          activeIndex={activeRun} onSelect={selectRun} />

        {result && result.num_deals === 0 && (
          <div className="banner banner-error">
            No deals could be generated — your constraints may be impossible.
          </div>
        )}
        {result && result.num_deals > 0 && benchmark && (
          <>
            <ContractResults result={result} mode={mode}
              benchmark={benchmark} setBenchmark={setBenchmark}
              onRerun={onRerun} recap={recap}
              shareUrl={lastRequest ? shareUrl : undefined} />
            <StrainGrid result={result} mode={mode} benchmark={benchmark} />
            <CompareContracts result={result} mode={mode} benchmark={benchmark} />
            <ContractSampleDeals result={result} mode={mode} benchmark={benchmark} />
          </>
        )}
      </main>
    </div>
  )
}
