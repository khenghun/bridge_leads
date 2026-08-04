# Latest updates — session handoff (2026-08-04)

## v2.1: `fixed_cards` — pin named cards into an unseen hand ✅ both tools, verified in a browser

The constraint vocabulary could say *how many* and *how good* but never *which*:
there was no way to express "partner holds ♥AK". `fixed_cards` was already
plumbed through `engine/sampling.py` (it predates the split) but was not in the
Pydantic schema, so nothing could reach it. Now it is exposed end to end, in the
opening-lead simulator **and** the optimal-contract calculator.

### Representation

Wire format is the engine's own, so there is no translation layer:

```
constraints: { ..., "fixed_cards": {"E": ["HA", "HK"]} }
```

endplay card form (`SA`, `HK`, `DT`), keyed by player letter like every other
constraint block. In the UI each seat panel gains a collapsible **➕ Specific
cards** box holding four per-suit rank inputs — type `AK` in the ♥ row — which
is how a bridge player says it, and reuses the existing holding helpers
(`normHolding` / `holdingError`). The button carries a count (`Specific cards
(2)`) so a collapsed box never hides a live constraint.

### How it composes (the reason this was cheap)

Pinned cards are merged into `known_hands`, so they are *dealt*, not *tested*:
the HCP bounds count them, `ExactDealSampler`'s quality DP seeds its base
counts from them, and both samplers treat them exactly like the user's own 13
cards. So `{fixed_cards: {N: ['HA','HQ']}, quality: {N: {H: 'poor'}}}` is
reported infeasible rather than silently sampling forever.

### Validation, split by what each layer knows

- `app/common/constraints.build_fixed_cards` — card syntax, no card claimed
  twice (within a seat or across two).
- `engine/sampling.resolve_fixed_cards` — what needs the user's hand: not your
  own seat, not a card you already hold. Lives in the engine so calling it
  directly stays safe.
- `engine/sampling.check_length_feasibility` — **new**: pinned cards vs the
  suit-length bounds. Without it the sampler builds a valid DP and then rejects
  every draw, and the user gets "no deals could be generated" instead of "N is
  pinned 3 H cards but its H maximum is 2".
- `fixedCardIssues` in `lib/bridge.ts` mirrors all of the above client-side and
  disables Simulate, so the 422 is a backstop rather than the normal path.

### Also fixed (pre-existing, surfaced by the new box)

`.constraint-grid` was `repeat(3, 1fr)`, so an expanded box widened its own
column and squeezed the other two seats' min/max inputs into unreadable
slivers (the Advanced shape box already did this). Now
`repeat(auto-fit, minmax(15rem, 1fr))` + a `min-width` floor on the inputs:
equal columns, dropping to two then one rather than shrinking past what the
controls need.

### Tests

- Backend **237 pass** (was 226). New `tests/test_fixed_cards.py` covers all
  three layers plus the end-to-end invariant that every sampled deal really
  contains the pinned cards in the named seat, and the composition cases
  (HCP band, quality grade, cache key).
- Frontend **30 vitest pass** (was 24); `tsc -b` + build clean.
- Browser (Playwright): both tabs. Confirmed the request body carries
  `fixed_cards`, all 300 lead deals / 150 contract deals put ♥AK in the named
  seat and no other seat holds either card, and that typing a card the leader
  already holds shows `⚠ ♥K is already in your own hand` and greys Simulate.

## Also in v2.1: a **What's new** tab ✅

A third tab of user-facing release notes, `frontend/src/apps/changelog/`.
`releases.ts` holds the data (version, date, title, New/Improved/Fixed entries)
and is now the **source of truth for public version numbers**; `ROADMAP.md`
follows it. Static content, so it stays mounted beside the two tools for free.

Version numbering was reworked at the same time: everything through 2026-07-16
is **v1.0** (its six development milestones are kept inside that ROADMAP
section, since `docs/vN-plan.md` are named after them), then v1.1 (compare
leads), v1.2 (suit quality), v2.0 (contract calculator), v2.1 (this session).

### State

Uncommitted on `main`. Everything below this line is the previous session.

---

# Latest updates — session handoff (2026-08-03)

## v7: Optimal Contract Calculator ✅ backend + UI done, verified in a browser

A second tool in a second tab: enter **your own** hand plus constraints on the
unseen hands, and rank the **contracts your side could be in** (3NT, 4♠, ♠
partscore, …). Design rationale in [`docs/v7-contract-plan.md`](docs/v7-contract-plan.md);
what shipped, below.

### The repo is now shared-core + one package per tool

Nothing about the lead tool's behaviour or endpoints changed, but its code moved:

```
backend/engine/dds_runtime.py   NEW  thread cap, the one global DDS lock, solve_all + calc_tables
backend/engine/sampling.py      NEW  constraint building + deal generation (parameterised by OWN seat)
backend/engine/lead/            moved from engine/lead_simulator.py, engine/auctions.py
backend/engine/contract/        NEW  candidates.py + simulator.py
backend/app/common/             NEW  cache.py (ResultCache), constraints.py, schemas.py
backend/app/lead/               moved from app/{routes,service,schemas}.py — same URLs
backend/app/contract/           NEW  POST /api/contract/simulate
frontend/src/apps/lead/         moved: LeadApp + ResultsTable/CompareLeads/SampleDeals
frontend/src/apps/contract/     NEW  ContractApp, ContractResults, StrainGrid, CompareContracts,
                                     ContractSampleDeals, ranking.ts
frontend/src/api/               split into http.ts / lead.ts / contract.ts + per-tool types
```

The **DDS lock is the load-bearing part of that refactor**: libdds's multi-board
functions are not re-entrant, and there are now two endpoints solving
concurrently in Starlette's threadpool. `dds_runtime.DDS_LOCK` is process-global
and both `solve_all()` and `calc_tables()` take it. A per-tool lock would
protect nothing.

Shared UI needed two small generalisations: `HandEntry` takes `seat` + `role`
instead of hardcoding "the opening leader", and `ConstraintsEditor` takes
`seats: [Seat, label][]` instead of deriving declarer/dummy/partner itself (the
contract tool passes partner / LHO / RHO).

### Engine: one DD table per deal prices every contract

`engine/contract/simulator.py` samples deals with our hand fixed, then calls
`calc_all_tables` once per deal (5 strains × 4 declarers, batched at
`MAXNOOFTABLES` = 40). Given the table, scoring any level/strain/declarer is
arithmetic (~5 µs), so **deal count is the only cost driver**: ~45–70 ms/deal on
4 threads, ~160 ms on a 2-core box, hence the 150-deal default (50–500) and the
per-strain checkboxes that feed `exclude=`.

Two things that would silently corrupt every ranking if they broke, so both are
pinned by tests: the DD table cross-checks against `solve_board` (the oracle the
lead tool already trusts), and **we declare here** — the declarer score IS our
score, no sign flip, unlike the lead simulator.

The candidate set is **20, not 70** — undoubled, every partscore level in a
strain scores the same for a given trick count and the lowest never scores less,
so per strain the decisions are `partscore | game | 6 | 7`. Both declarers are
evaluated and the better one is shown with a "play it from X" flag.

### Ranking: pairwise against a benchmark contract

Head-to-head-against-all (what the lead tool does) would make every number
depend on which contracts are in the list, and would flatter grand slams at
matchpoints. Instead both modes compare against **one benchmark** — the contract
you would otherwise be in:

- IMPs: mean `imps(candidate − benchmark)`; the benchmark reads 0.00.
- MP: `win% + ½·ties`; over 50% means bid it.

The backend suggests the benchmark (highest EV — best mean score of all 20
candidates) and ships the
per-deal score matrix; `rankVsBenchmark()` in `lib/bridge.ts` does the ranking,
so both the mode toggle and the benchmark selector are instant and refetch-free
— the same division of labour the lead tool's mode toggle already used.
`compareLeads()` was generalised to `compareCandidates()` over that matrix and
the lead tool now calls a thin alias.

Beside the metric: make %, mean tricks / needed, mean score, mean score when it
fails, and flags for a declarer-dependent contract (≥ 0.3 tricks) or a thin edge
(≥ 0.5 IMPs concentrated in the best 15% of deals). Opponent context comes free
from the same tables: *opponents make a game on X%* and *par is theirs or a save
on Y%* (`endplay.dds.par`, withheld when strains were excluded since par needs a
complete table).

### Verified

- **Tests:** backend 205 passed (31 new: candidates, simulator, API); frontend
  22 passed (new: `compareCandidates`, `rankVsBenchmark`, `ranking.ts`);
  `npm run build` clean.
- **Browser (Playwright):** both tabs; the lead tab still simulates identically;
  a contract run with partner 10–14 HCP — request body carried the constraint,
  and the response's 150 layouts all had North between 10 and 14 HCP with our
  hand fixed; matrix make-rate matched the summary; mode flip re-ranked (4♠ tops
  at IMPs, 3NT at matchpoints — correct, since 3NT+1 beats 4♠= at MP); heatmap,
  compare, and sample deals all render.
- **Bridge sanity** (100 deals, seed 0): slam fit → benchmark 6♠ at 99% make,
  with 7♠ +0.86 IMPs at 59% (right: a grand needs ~57% vs a small slam at IMPs,
  and it is the concavity case — 7♠'s raw EV is lower); misfit → ♠ partscore
  tops with opps-game 97% / par-competitive 100%; balanced 21 HCP → 6NT at 49%
  ≈ break-even against 3NT at 92%; vulnerable → 4♠ over 3NT.

## State at session end

- v7 is **committed on `main`** on top of `7bfbe41`. Nothing since v6 is pushed
  or deployed: prod (https://bridge-leads.icycookie.xyz, verified up and healthy
  this session) still runs the **v6** build, without compare-leads (`f911954`)
  and without v7.
- Deploy recipe unchanged: push (build runs) then manual `workflow_dispatch`
  (deploy job).

## Next session (carried over)

1. Push, deploy, and **time a 150-deal contract run on the VPS** —
   if it is much over ~30 s, lower the default rather than raising nginx's
   120 s proxy timeout.
2. Prod verification of the lead tool still pending from the last session
   (1NT preset, hands `T.KT932.Q2.T9843` / `AK872.Q95.J98.Q4` /
   `Q84.A72.T653.K92` / `J9743.86.AQ2.J85`, 500+1000).
3. v8 candidates, all deliberately out of v7: "they compete to X" toggle,
   auto-doubling of large sets, realistic (single-dummy) opening lead before
   solving, and demo auctions for the contract tab.
4. Still declined: adaptive early stopping, VPS resize, persistent cache
   warming.

---

# Previous session (2026-08-02)

## Suit-quality constraint ✅ backend + UI done, verified in a browser

New constraint on the unseen hands: grade **one** suit of **one** seat by its
top honours. Definitions agreed this session:

- **good** = 2 of AKQ **or** 3 of AKQJT (what a preempt / overcall promises)
- **poor** = anything worse (a plain complement — matches ~70% of holdings, so
  it is a deliberately weak filter; `good` is the one that does real work)

Exactly **one** constraint exists table-wide, because it comes from the one
player who described a suit in the auction. That ceiling is a design input, not
a limitation to remove casually — it is what keeps the sampler's DP small.

### Dealt inside the DP, not by rejection

Per the session's explicit direction, quality honours are placed in the *same*
pass that satisfies HCP rather than being tested afterwards. In
`honor_sampler.py`: honor classes split by the constrained suit (aces become
`[SA]` + `[HA,DA,CA]`), the constrained suit's **ten** joins as a zero-value
class (`HONORS` is A/K/Q/J, so `T` is an ordinary spot card to the rest of the
engine — the "3 of top 5" arm is the only reason it must be tracked), and two
state dimensions carry the seat's running top-3 / J-T counts, filtered in the
terminal pass beside the HCP minimums.

Consequences, all verified:

- Zero rejection for quality; the draw stays **exactly uniform**.
- `.total` now counts HCP- **and** quality-consistent deals → exact
  infeasibility with a specific error, instead of the old silent
  `num_simulations: 0` empty result.
- HCP and quality prune **each other**: a seat capped at 2 HCP can never hold a
  good suit (cheapest good holding is QJT = 3 HCP), and the DP sees it.

### It made things faster, not slower

Benchmark (500 deals, leader `T.KT932.Q2.T9843`):

| constraint set                    | build   | 500 deals | accept |
|-----------------------------------|---------|-----------|--------|
| none                              |  3.5 ms | 0.028 s   | 100%   |
| weak 2H: 6 hearts, 5–10 HCP       |  7.3 ms | 2.897 s   | 0.9%   |
| **weak 2H + good hearts**         | 15.8 ms | **0.332 s** | 8.3% |
| weak 2H + poor hearts             | 16.8 ms | 5.057 s   | 0.6%   |
| 1S overcall: 5 spades, good, 8–16 | 42.9 ms | 0.103 s   | 32.0%  |

Adding `good` to the weak-two case is **~9× faster**, because conditioning on
good hearts raises P(6 hearts) and the length rejection was the bottleneck.
`poor` costs a little for the mirror-image reason. Build cost 3.5 → ~16–45 ms,
once per constraint set and behind the result cache.

Note the 2.9 s baseline row is **pre-existing** (exact 6=6 length rejection),
not something this feature introduced.

### Files

- `engine/suit_quality.py` (new) — definitions, `counts`/`is_good`/`satisfies`,
  `min_length`, `predicate` (fallback path only), `describe`.
- `engine/honor_sampler.py` — class splitting, ten class, quality state dims,
  `_step` now takes the whole state + class kind. `poor` prunes as a ceiling.
- `engine/lead_simulator.py` — `_resolve_quality` (validates down to one
  tuple), `_all_of` (a seat can now have shape **and** quality acceptors — the
  old `acceptors[p] = predicate` would have silently dropped one), implied
  length minimum (`good` ⇒ 2+ cards), quality-aware infeasibility message.
  `_build_known_and_constraints` now returns **5** values.
- `app/schemas.py` / `app/service.py` — additive `quality` field, pass-through.
- Frontend: `api/types.ts`, `lib/bridge.ts` (`QUALITY_HINT`, `applyQuality`),
  `components/ConstraintsEditor.tsx` (a `<select>` per suit row),
  `App.tsx`, `index.css`.

The selects act as one table-wide **radio group**: `applyQuality` clears every
other pick, so the "only one" rule can never produce a 422 from the UI.

### Tests

- Backend **174 pass** (was 133). `tests/test_suit_quality.py` is the important
  one: `.total` pinned against **brute-force enumeration** (incl. a pool
  containing the constrained ten), `good + poor == unconstrained total`,
  sampled frequencies vs exact per-outcome counts, plus the predicate truth
  table and the plumbing/validation errors. A DP bug here would not raise — it
  would silently skew every simulated deal — so these stay.
- Frontend: `tsc -b` + `vite build` clean, existing **12 vitest pass**.

### Browser verification ✅ (Playwright MCP, `.mcp.json`)

All five open UI items pass. Setup is `.mcp.json` (npx `@playwright/mcp`);
`.playwright-mcp/` is gitignored.

1. **Layout** at 1280 / 420 / 320 px — no page or row overflow at any width, no
   text clipping. The `min-width: 0` on the inputs is what carries it: at 320 px
   they shrink 102 → 52 px while the select holds its `4.6rem`.
2. **Radio group** — same-seat-other-suit clears, cross-seat clears, `—` clears.
   Never more than 1 of the 12 selects set, so the 422 stays unreachable.
3. **End-to-end** — payload carries `"quality":{"S":{"H":"good"}}` → 200, full
   results render. Also checked `poor` (`{"S":{"D":"poor"}}` → 200).
4. **Infeasibility** — seat capped at 2 HCP + `good` → 422 rendered as the
   specific banner ("no arrangement of the unseen honor cards gives N a good S
   suit…"), no crash, recovers on the next successful run.
5. **Preset switch / Manual reset** — both clear quality and reset HCP.

Two checks worth more than pass/fail, both on the `good ♥` run (leader holds
♥K, so declarer's only route to *good* is ♥AQ):

- Pulled the 300-deal matrix back: **0 violations**, and South never holds ♥K.
  Every holding is AQ-based (`AQ`, `AQ6`, `AQJ`…). That is the known-card ×
  quality interaction in the DP — the case most likely to skew silently.
- Rankings react correctly: ♥K ranks **dead last** (−1.117 IMPs, 16.3 MP%), the
  underlead-into-AQ disaster. A broken sampler's failure mode is rankings that
  *don't* move; these move the right way.

### Not done — pick up here

1. **A vitest for `applyQuality` was drafted but not written** — cover: sets
   one, clears another seat's, clears another suit of the same seat, never more
   than one in the table, `''` clears, no mutation. Playwright covered the
   behaviour, but there is no cheap regression guard.
2. Not built (explicitly out of scope this session): a `solid` (AKQ) third
   rung — one line in `suit_quality.py`; exposing the engine's existing
   `fixed_cards` ("partner holds the ♥K").
3. Still carried over: push + deploy (compare-leads from 2026-07-25 and this
   suit-quality work are committed but **not deployed**), then verify prod
   timing.

# Previous handoff (2026-07-29)

### Native libdds build: attempted, measured, dropped ❌ (2026-07-29)

Tried the agreed plan (compile dds 2.9.0 with `-O3 -march=x86-64-v3` in a
Dockerfile builder stage, overwrite endplay's bundled `libdds.so` — endplay
loads `endplay/_dds/libdds.so` on Linux, `dds.dll` on Windows). A/B benchmark
in the container (300 deals, seed 0, best of 3; result fingerprints identical
in all runs, so the native build was output-correct):

| build                     | 4 threads | 1 thread |
|---------------------------|-----------|----------|
| bundled (endplay wheel)   | **4.10s** | 12.86s   |
| native `-march=x86-64-v3` | 13.48s    | 13.44s   |

Two findings, both fatal to the idea:

1. **`-march` buys nothing single-threaded** (13.4 vs 12.9s — slightly
   *worse*). DDS is branchy integer search; AVX2 codegen doesn't help, and the
   wheel is already `-O3`. The 10–25% estimate was wrong.
2. Our OpenMP-only build (`-DDDS_THREADS_OPENMP`) didn't parallelise
   `SolveAllBoardsBin` at all (same time at 1 and 4 threads); the bundled
   build scales ~3.1×. Fixable (`-DDDS_THREADS_STL`), but best case is parity
   with the bundled wheel — no reason to ship it.

Keep the bundled solver. Don't revisit unless upstream dds (restructured
`develop` branch) ships algorithmic improvements worth benchmarking.
Gotchas recorded for any future attempt: dds 2.9.0's Linux memory detection
shells out to `free` (needs `procps` in slim images) and aborts on import
without it; v2.9.0 tag has the old flat `src/` + Makefiles layout, `develop`
is fully restructured.

# Previous handoff (2026-07-25)

Session goal: the **Compare leads** feature — pick 2 opening leads, see
win/draw/lose across the simulated deals, filter the deal diagrams by outcome.
Done, tested, verified in the browser; committed on `main` this session.

## 1. Per-deal matrix on `/api/simulate` ✅

The engine always solved every candidate lead on every deal but discarded the
per-deal data after MP/IMP aggregation. `simulate_opening_lead` now also
returns it, compact and index-aligned:

```
'deals': { 'cards': ['♥Q', ...],             # fixed candidate order
           'records': [ {layout: {seat: 'S.H.D.C'},
                         tricks: [decl tricks per card],
                         scores: [leader score per card]}, ... ] }  # 1/deal
```

- Built in `engine/lead_simulator.py` from the existing `leader_scores` +
  `deal_layouts` (plus a new `tricks_by_card`); a length assertion fails loudly
  if DDS ever returns a misaligned column.
- Additive `DealRecord`/`DealsMatrix` models in `app/schemas.py`; no
  routes/service wiring needed.
- **Cache**: entries now carry the matrix (~1–2 MB at 1000 deals), so
  `service._CACHE_MAX` dropped 256 → 64.
- **Payload**: ~105 KB raw at 300 deals; added `gzip on` for JSON to
  `frontend/nginx.conf` (prod only — takes effect on next deploy).

## 2. Compare-leads UI ✅ (pure client-side, like the mode toggle)

New `frontend/src/components/CompareLeads.tsx` between ResultsTable and
SampleDeals; helpers `imps()` (ported IMP scale — keep identical to
`engine/scoring.py`) and `compareLeads()` in `lib/bridge.ts`.

- **Compare** button opens two chip rows (Lead A / Lead B), ordered like the
  results table (best first by active metric); picking the other row's card
  swaps them. Default: best lead vs best *non-tied* rival (top-2 are often
  touching cards that draw every deal).
- Banner: `♥2 vs ♥9 over 300 deals: 11 win / 275 draw / 14 lose` + avg IMP
  swing (IMPs mode) or head-to-head MP% (MP mode). W/D/L is per-deal score
  comparison, so counts are mode-independent.
- All/Win/Draw/Lose filter buttons over the deal diagrams; each diagram gets a
  caption `decl 8 with ♥9 vs 10 with ♥2 · +10 IMPs`.
- Zero refetch: verified one `/api/simulate` request through the whole flow.

## 3. Tests ✅

- Backend **133 pass** (was 128): matrix alignment, consistency with the
  aggregate table, scoring-oracle spot-check, score-vs-tricks monotonicity,
  samples ⊂ matrix, API shape.
- Frontend **12 vitest pass**: IMP-scale boundaries, compareLeads fixture,
  swap antisymmetry. `tsc -b` + build clean.
- Browser (Playwright): full flow on the 1NT preset — counts sum to the deal
  total, buckets filter, swap inverts win/lose, MP% matches hand computation,
  mode flip re-ranks without refetch.

## State at session end

- Everything committed on `main`, **not pushed/deployed**. Deploy recipe:
  push (build runs) then manual `workflow_dispatch` (deploy job).
- The nginx gzip change ships with the frontend image on that deploy.

## Next session (carried over)

1. ~~Native libdds build~~ — attempted 2026-07-29, no gain, dropped (see top
   of this file).
2. Push + deploy + verify prod timing (1NT preset, hands `T.KT932.Q2.T9843` /
   `AK872.Q95.J98.Q4` / `Q84.A72.T653.K92` / `J9743.86.AQ2.J85`, 500+1000).
3. Declined for now: adaptive early stopping, VPS resize, persistent cache
   warming.
