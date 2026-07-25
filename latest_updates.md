# Latest updates — session handoff (2026-07-25)

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

1. **Native libdds build (agreed, not started)** — compile dds 2.9.0 with
   `-O3 -march=x86-64-v3` in the backend Dockerfile, replace endplay's bundled
   `.so`. Expected 10–25% DDS speedup. `libgomp1` already in the image.
2. Push + deploy + verify prod timing (1NT preset, hands `T.KT932.Q2.T9843` /
   `AK872.Q95.J98.Q4` / `Q84.A72.T653.K92` / `J9743.86.AQ2.J85`, 500+1000).
3. Declined for now: adaptive early stopping, VPS resize, persistent cache
   warming.
