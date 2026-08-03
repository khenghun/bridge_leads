import { useEffect, useMemo, useState } from 'react'
import type { Constraints, Mode, Quality, Seat, Suit } from '../../api/types'
import type { ContractResponse } from '../../api/contractTypes'
import { simulateContracts } from '../../api/contract'
import {
  SEATS, SEAT_NAME, SUIT_SYMBOL, SUITS,
  applyQuality, holdingError, holdingsToPbn, partnerSeat,
  type Holdings,
} from '../../lib/bridge'
import HandEntry from '../../components/HandEntry'
import ConstraintsEditor, {
  defaultSeatConstraint, type SeatConstraint,
} from '../../components/ConstraintsEditor'
import ContractResults from './ContractResults'
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
  const out: Constraints = { hcp: {}, suit_length: {}, shapes: {}, quality: {} }
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
  }
  return out
}

interface Props {
  mode: Mode
  setMode: (m: Mode) => void
}

export default function ContractApp({ mode, setMode }: Props) {
  const [seat, setSeat] = useState<Seat>('S')
  const [weVul, setWeVul] = useState(false)
  const [theyVul, setTheyVul] = useState(false)
  const [numDeals, setNumDeals] = useState(150)
  const [strains, setStrains] = useState<string[]>(ALL_STRAINS)
  const [holdings, setHoldings] = useState<Holdings>(emptyHoldings)
  const [constraints, setConstraints] = useState<Record<Seat, SeatConstraint>>(defaultConstraints)
  const [result, setResult] = useState<ContractResponse | null>(null)
  const [benchmark, setBenchmark] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A new result resets the benchmark to the engine's suggestion (the best
  // normal contract by mean score).
  useEffect(() => { if (result?.default_benchmark) setBenchmark(result.default_benchmark) }, [result])

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
  const canSimulate = handValid && strains.length > 0

  const onSimulate = async () => {
    if (!canSimulate) return
    setLoading(true)
    setError(null)
    try {
      const res = await simulateContracts({
        hand: holdingsToPbn(holdings),
        seat,
        vul,
        num_deals: numDeals,
        strains,
        constraints: buildConstraints(seat, constraints),
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
          {ALL_STRAINS.map((s) => (
            <button key={s}
              className={`chip${strains.includes(s) ? ' chip-selected' : ''}`}
              onClick={() => toggleStrain(s)}>
              {s === 'N' ? 'NT' : SUIT_SYMBOL[s as Suit]}
            </button>
          ))}
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
          setConstraint={setConstraint} setQuality={setQuality} />

        <button className="btn btn-primary" disabled={!canSimulate || loading} onClick={onSimulate}>
          {loading ? `Simulating ${numDeals} deals…` : 'Find the best contract'}
        </button>

        {error && <div className="banner banner-error">{error}</div>}

        {result && result.num_deals === 0 && (
          <div className="banner banner-error">
            No deals could be generated — your constraints may be impossible.
          </div>
        )}
        {result && result.num_deals > 0 && benchmark && (
          <>
            <ContractResults result={result} mode={mode}
              benchmark={benchmark} setBenchmark={setBenchmark} />
            <StrainGrid result={result} mode={mode} benchmark={benchmark} />
            <CompareContracts result={result} mode={mode} benchmark={benchmark} />
            <ContractSampleDeals result={result} mode={mode} benchmark={benchmark} />
          </>
        )}
      </main>
    </div>
  )
}
