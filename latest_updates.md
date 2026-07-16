# Latest updates — session handoff (2026-07-16)

Session goals: (1) diagnose why pushing to `main` didn't update the live
site — resolved, v6 is now deployed; (2) harden the backend for concurrent
users; (3) small UI improvements. All committed on `main` this session.

## 0. v6 deployed ✅

The previous session's v6 work (`158856b`, exact-distribution sampler +
infeasible-HCP 422) was pushed, but the site still served v5. Cause: by
design, a push only runs the **build** job — the **deploy** job in
`.github/workflows/deploy.yml` is gated on `workflow_dispatch` (the manual
"Run workflow" button). Ran the dispatch; **v6 is live and verified** at
<https://bridge-leads.icycookie.xyz>. Remember: every deploy needs that
manual click after the push-triggered build.

## 1. Thread-safety for concurrent users ✅

`/api/simulate` is a sync handler, so concurrent requests run in Starlette's
threadpool inside the single uvicorn process. Two races fixed:

- **DDS serialization** (`engine/lead_simulator.py`): libdds's multi-board
  functions (`SolveAllBoards*`) are **not re-entrant** — global internal
  state, one caller at a time. `_solve_all()` now wraps the batch loop in a
  global `_DDS_LOCK`. Concurrent simulations queue at the solve; each still
  uses its full `BRIDGE_DDS_THREADS` allowance, so total throughput is
  unchanged. Any future DDS call site must take the same lock.
- **Cache lock + dogpile protection** (`app/service.py`): the LRU+TTL result
  cache is now guarded by `_cache_lock`, and an `_inflight` map of
  `threading.Event`s makes simultaneous identical requests simulate **once**
  (first thread computes, the rest wait, a failed leader hands off to a
  waiter instead of wedging them).
- **Tests**: new `backend/tests/test_service_concurrency.py` (8 identical
  concurrent requests → 1 simulation; crashing leader releases waiters, no
  leaked in-flight entries). Full backend suite: **128 pass**. Also
  smoke-tested live: 6 simultaneous requests (4 identical + 2 different)
  against the dev server — all 200, identical bodies for identical requests,
  no crashes.

## 2. UI improvements ✅ (all verified in the browser via Playwright)

- **Results table sorts by the active metric, best first** — MP% descending
  in Matchpoints mode, IMPs descending in IMPs mode (default); ties break by
  fewer declarer tricks. Was: always declarer-tricks ascending.
- **One more decimal** in the table: Defeat % 1 dp, MP% 2 dp, IMPs 3 dp.
- **Sample-deal ★ marks all tied-best leads**, computed with the same
  rounding as the banner (1 dp MP / 2 dp IMPs) so the starred set always
  matches the "(n tied)" count. Was: only the single backend-reported best.
- **Default deal count 300** (was 500).

## State at session end

- Everything above committed on `main`. Production runs v6 + these changes
  once the next push + manual `workflow_dispatch` deploy happens (the
  thread-safety/UI work was committed after the v6 deploy).
- Backend: 128 tests pass. Frontend: `tsc -b` clean; UI flows verified live
  (demo auction fill, PBN entry, simulate, mode toggle re-rank, infeasible
  422 banner).

## Next session

1. **Native libdds build (agreed, not started)** — compile dds 2.9.0 with
   `-O3 -march=x86-64-v3` in the backend Dockerfile and replace endplay's
   bundled generic `.so`. Expected 10–25% DDS speedup; DDS is ~95%+ of
   runtime. `libgomp1` is already in the image.
2. Push + deploy (build runs on push; deploy needs the manual
   `workflow_dispatch`), then verify prod timing (recipe: 1NT preset, hands
   `T.KT932.Q2.T9843` / `AK872.Q95.J98.Q4` / `Q84.A72.T653.K92` /
   `J9743.86.AQ2.J85`, 500+1000 deals).
3. Declined for now: adaptive early stopping, VPS resize, persistent cache
   warming.
