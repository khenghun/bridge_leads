import { useEffect, useMemo, useState } from 'react'
import type { Auction, Constraints, Mode, Seat, SimulateResponse } from './api/types'
import { fetchAuctions, simulate } from './api/client'
import {
  SEATS, SEAT_NAME, SUITS,
  dummySeat, holdingError, holdingsToPbn, leaderSeat, parseContract, partnerSeat,
  type Holdings,
} from './lib/bridge'
import HandEntry from './components/HandEntry'
import ConstraintsEditor, {
  defaultSeatConstraint, type SeatConstraint,
} from './components/ConstraintsEditor'
import ResultsTable from './components/ResultsTable'
import SampleDeals from './components/SampleDeals'

const MANUAL = '(manual entry)'

function emptyHoldings(): Holdings {
  return { S: '', H: '', D: '', C: '' }
}

function defaultConstraints(): Record<Seat, SeatConstraint> {
  return Object.fromEntries(SEATS.map((s) => [s, defaultSeatConstraint()])) as Record<Seat, SeatConstraint>
}

/** Assemble the API constraints dict from the per-seat editor state, for the
 * three seats that are actually constrainable given the declarer. */
function buildConstraints(declarer: Seat, constraints: Record<Seat, SeatConstraint>): Constraints {
  const leader = leaderSeat(declarer)
  const seats: Seat[] = [declarer, dummySeat(declarer), partnerSeat(leader)]
  const out: Constraints = { hcp: {}, suit_length: {}, shapes: {} }
  for (const seat of seats) {
    const c = constraints[seat]
    if (c.hcp[0] !== 0 || c.hcp[1] !== 40) out.hcp[seat] = c.hcp
    const sl: Record<string, [number, number]> = {}
    for (const s of SUITS) {
      const [lo, hi] = c.suits[s]
      if (lo !== 0 || hi !== 13) sl[s] = [lo, hi]
    }
    if (Object.keys(sl).length) out.suit_length[seat] = sl
    if (c.shape.trim()) out.shapes[seat] = c.shape
  }
  return out
}

export default function App() {
  const [auctions, setAuctions] = useState<Auction[]>([])
  const [demoName, setDemoName] = useState(MANUAL)
  const [contractStr, setContractStr] = useState('3NT')
  const [declarer, setDeclarer] = useState<Seat>('S')
  const [penalty, setPenalty] = useState('none')
  const [vul, setVul] = useState(false)
  const [mode, setMode] = useState<Mode>('imps')
  const [numSims, setNumSims] = useState(300)
  const [holdings, setHoldings] = useState<Holdings>(emptyHoldings)
  const [constraints, setConstraints] = useState<Record<Seat, SeatConstraint>>(defaultConstraints)
  const [result, setResult] = useState<SimulateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [light, setLight] = useState(false)

  useEffect(() => { fetchAuctions().then(setAuctions).catch(() => {}) }, [])
  useEffect(() => { document.body.classList.toggle('light', light) }, [light])

  const parsed = parseContract(contractStr)
  const leader = leaderSeat(declarer)

  const applyDemo = (name: string) => {
    setDemoName(name)
    setConstraints((prev) => {
      const next = { ...prev }
      if (name === MANUAL) {
        for (const s of SEATS) next[s] = { ...next[s], hcp: [0, 40], shape: '' }
        return next
      }
      const a = auctions.find((x) => x.name === name)
      if (!a) return prev
      setContractStr(a.contract)
      setDeclarer(a.declarer)
      for (const s of SEATS) {
        const rng = a.hcp[s]
        next[s] = {
          ...next[s],
          hcp: rng ? [rng[0], rng[1]] : [0, 40],
          shape: a.shapes_text[s] ?? '',
        }
      }
      return next
    })
  }

  const setConstraint = (seat: Seat, v: SeatConstraint) =>
    setConstraints((prev) => ({ ...prev, [seat]: v }))

  const cardCount = SUITS.reduce((n, s) => n + holdings[s].length, 0)
  const handValid = useMemo(
    () => cardCount === 13 && !SUITS.some((s) => holdingError(holdings[s])),
    [holdings, cardCount],
  )
  const canSimulate = handValid && parsed !== null

  const onSimulate = async () => {
    if (!parsed || !handValid) return
    setLoading(true)
    setError(null)
    try {
      const res = await simulate({
        leader_hand: holdingsToPbn(holdings),
        level: parsed.level,
        strain: parsed.strain,
        declarer,
        vul: vul ? 'both' : 'none',
        penalty,
        num_simulations: numSims,
        constraints: buildConstraints(declarer, constraints),
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <label className="toggle">
          <input type="checkbox" checked={light} onChange={(e) => setLight(e.target.checked)} />
          Light mode
        </label>

        <h2>Demo</h2>
        <label className="field">
          Sample auction
          <select value={demoName} onChange={(e) => applyDemo(e.target.value)}>
            <option>{MANUAL}</option>
            {auctions.map((a) => <option key={a.name}>{a.name}</option>)}
          </select>
        </label>

        <h2>Contract</h2>
        <div className="row">
          <label className="field">Contract
            <input value={contractStr} placeholder="3NT, 4H"
              onChange={(e) => setContractStr(e.target.value)} />
          </label>
          <label className="field">Declarer
            <select value={declarer} onChange={(e) => setDeclarer(e.target.value as Seat)}>
              {SEATS.map((s) => <option key={s} value={s}>{SEAT_NAME[s]}</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <label className="field">Penalty
            <select value={penalty} onChange={(e) => setPenalty(e.target.value)}>
              <option value="none">None</option>
              <option value="doubled">Doubled</option>
              <option value="redoubled">Redoubled</option>
            </select>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={vul} onChange={(e) => setVul(e.target.checked)} />
            Vul.
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
          Deals to simulate: <b>{numSims}</b>
          <input type="range" min={100} max={1000} step={100} value={numSims}
            onChange={(e) => setNumSims(Number(e.target.value))} />
        </label>
      </aside>

      <main className="content">
        <h1>Opening Lead Simulator</h1>
        <p className="caption">Monte-Carlo + double-dummy. No AI — pure simulation.</p>

        <div className="banner banner-info">
          Opening leader: <b>{SEAT_NAME[leader]}</b> (left of declarer {SEAT_NAME[declarer]})
        </div>
        {!parsed && (
          <div className="banner banner-error">
            Invalid contract <code>{contractStr}</code> — enter a level 1–7 and strain, e.g.{' '}
            <code>3NT</code> or <code>4H</code>.
          </div>
        )}

        <HandEntry leader={leader} holdings={holdings} setHoldings={setHoldings} />
        <ConstraintsEditor declarer={declarer} constraints={constraints} setConstraint={setConstraint} />

        <button className="btn btn-primary" disabled={!canSimulate || loading} onClick={onSimulate}>
          {loading ? `Simulating ${numSims} deals…` : 'Simulate'}
        </button>

        {error && <div className="banner banner-error">{error}</div>}

        {result && result.num_simulations === 0 && (
          <div className="banner banner-error">
            No deals could be generated — your constraints may be impossible.
          </div>
        )}
        {result && result.num_simulations > 0 && (
          <>
            <ResultsTable result={result} mode={mode} />
            <SampleDeals result={result} mode={mode} />
          </>
        )}
      </main>
    </div>
  )
}
