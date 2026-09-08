---
name: run-apps
description: Boot the bridge apps locally (lead/contract app + play solver — two APIs, two Vite servers) and verify them end to end. Use when asked to run, start, restart, or check the apps, before any browser (Playwright) verification, or when a dev server is blank / 504 / "port in use".
---

# Running and checking the apps locally

Two products, one repo, **four dev processes**. Each product is an API + a Vite
entry; the pairs must not share ports or Vite's dependency cache.

| Product | API (from `backend/`) | UI (from `frontend/`) | Open |
| --- | --- | --- | --- |
| Lead / contract | `../.venv/Scripts/uvicorn app.main:app --reload --port 8000` | `npm run dev` (:5173, proxies `/api` → :8000) | http://localhost:5173/ |
| Play solver | `../.venv/Scripts/uvicorn app_play.main:app --reload --port 8001` | `npm run dev:play` (:5174, proxies `/api` → :8001) | http://localhost:5174/play.html |

(macOS/Linux: `../.venv/bin/uvicorn`.) **Local performance:** for expert-mode
or benchmark work, start the play API with `BRIDGE_DDS_THREADS=16` (or the
machine's core count) — the default caps DDS at 4 threads for the 2-core prod
box. Plain grades are bit-identical either way, only faster; expert-mode
verdicts follow a thread-dependent inner schedule (`max(5, threads)`), so
replay expert pins at `BRIDGE_DDS_THREADS=4`. The deterministic
numbers below don't change. Benchmark through `127.0.0.1`, never `localhost`
(Windows' IPv6 fallback adds ~2 s per request).

Both dev scripts use `--strictPort`:
if the port is taken they **fail loudly** instead of silently moving to :5175
and leaving you testing the wrong server. Run each as its own background
process with its output redirected to a log file in the scratchpad.

## Boot sequence

1. Start the two APIs, then the two Vite servers (order between pairs does not
   matter; the UI only needs its API at request time).
2. Wait ~3 s, then health-check all four **through the proxies**, which proves
   the Vite proxy target is right, not just that uvicorn is alive:
   ```
   curl -s http://localhost:8000/api/health            # lead API
   curl -s http://localhost:8001/api/play/health       # play API
   curl -s http://localhost:5173/api/health            # lead UI → proxy → API
   curl -s http://localhost:5174/api/play/health       # play UI → proxy → API
   ```
   All four must print `{"status":"ok"}`. A 500 from a `:517x/api/...` URL with
   nothing in the uvicorn log means the proxy points at a port with nothing
   on it (check `vite.config.ts` / `vite.play.config.ts`).
3. Check the Vite log for `Port … is already in use` (see *Stale processes*).

## Verify in the browser (Playwright MCP)

Lead / contract app — http://localhost:5173/
- Console: only the `favicon.ico` 404 is acceptable.
- Pick a demo auction, Simulate; a results table appears and
  `/api/simulate` returns 200.
- `#contract` tab simulates; `#changelog` lists v2.2 "Latest" down to v1.0.

Play solver — http://localhost:5174/play.html
- Console: only the `favicon.ico` 404 is acceptable. **A blank page with
  `504 (Outdated Optimize Dep)` is the shared-cache clash** (see below).
- Click the first example, **Board 17 · 1NT by West** (six are listed) → pick
  **E/W** (declaring 1NT — one grade, of West) →
  **Analyze** (single dummy, 40 deals — the default since the 2× scaling).
  Expect the deterministic result under the "West" section: **13 ✓ / 2 ~ /
  0 ✗ of 15 graded, 3 forced · 4 marginal**, `40 deals (×3 when in
  doubt)`, tricks given up 0.44 · **0.69 IMPs (23 points)**; one
  `/api/play/analyze` 200 in ~1 s with `seat: "W"`, `num_deals: 40` and
  `escalation: {factor: 3}`. Four rows carry a dashed `… ?` badge whose
  tooltip reads `120 deals (extended: …)`. Every decisions/options table
  has an IMPs column. (v1.0–v1.3 read 0.45 · 0.82 IMPs (27 points); so
  does this build with *Spend more deals on doubtful grades* unticked.)
- **Whole table** → Analyze: three sequential `/api/play/analyze` requests
  (W, then N, then S), sections filling in as each lands, a *Biggest swings*
  panel on top, **ranked by IMPs**: `1 N ♠9 −0.69 IMPs / −0.46 tricks`,
  `7 W ♥4 −0.42 / −0.15`, `8 S ♣3 −0.35 / −0.17`, `6 N ♠8 −0.34 / −0.38`,
  … ; pair lines read `E/W … 0.44 · 0.69 IMPs` and `N/S … 12✓ 2~ 2✗ of 16
  graded · 3 marginal · 1.19 · 1.76 IMPs`. Clicking a swing
  row jumps the viewer to that card, highlights the row in its seat's table
  and opens the options list (Score and IMPs columns present).
- Constraint slicing: set North HCP min 8 and West HCP max 12, run the whole
  table, and read the three request bodies — W's carries only `hcp.N`, N's
  only `hcp.W`, S's both. Set West HCP min 12 → an amber "rule out the hand
  actually held" note (non-blocking); pin ♥A on North → Analyze disabled.
- **Expert opponents** (v1.3): Board 17 → E/W → tick *Expert opponents*
  (the deal slider jumps 40 → 60; *Advanced* shows Strict / Margin 0.1 /
  Confidence 2 / Inner sample ratio 0.5 and "about 0.32 tricks") → Analyze.
  **Eighteen** `/api/play/analyze` requests, one per decision (forced ones
  included), each with `expert_opponents: true`, the default `expert` block,
  `expert_constraints` and a one-element `decisions` (`[1]`, `[3]`, …); the
  West heading reads *solving… decision 4 of 18 done* while they arrive
  (~80 s in all on a 4-thread laptop). Kill the API mid-run: the seat
  shows the error with "what was graded is kept; press Resume", and
  **Resume** continues from the first missing decision (the finished ones
  come straight back from the server cache). Deterministic result: header
  `60 deals (×3 when in doubt) · saw W + E · expert opponents`, seat line
  **Graded on 1380 of 1943 sampled deals … ≥ 0.32 tricks worse**, **13 ✓ /
  2 ~ / 0 ✗ of 15 graded (3 forced) · 2 marginal**, tricks given up
  **0.41 · 0.76 IMPs (25 points)**; every graded row shows `c/s deals`
  under its badge (60/60 early, `180/322` on the four re-graded
  decisions). Expert pins are thread-dependent: replay at
  `BRIDGE_DDS_THREADS=4`; `scripts/pin_example.py` prints both runs.
- Header **What's new · vX.Y** opens the play changelog panel.
- Screenshots land in the repo root — delete them when done.

## Known failure modes

- **Blank play page, `504 Outdated Optimize Dep`.** The two Vite servers were
  sharing `node_modules/.vite` and invalidating each other's pre-bundled
  React. `vite.play.config.ts` sets `cacheDir: 'node_modules/.vite-play'` to
  prevent it; if it recurs, stop both servers, `rm -rf node_modules/.vite
  node_modules/.vite-play`, start again.
- **Stale processes.** Stopping a backgrounded `npx vite` / `uvicorn` shell
  can leave the node/python child alive and still bound to the port (with the
  *old* config). Find and kill it before restarting:
  ```
  netstat -ano | grep -E ":(5173|5174|8000|8001) .*LISTENING"
  taskkill //F //PID <pid>          # Git Bash; PowerShell: taskkill /F /PID <pid>
  ```
  Never kill a port holder you cannot identify as a dev server of this repo
  without saying so — it may be the user's own session.
- **`npm run dev:play` opens the browser** (`--open /play.html`); from a
  sandboxed shell run `npx vite -c vite.play.config.ts --port 5174 --strictPort`
  instead.
- **`/api/validate/shape` 404 in the play app** means the play API is not the
  one behind the proxy — that route exists on both APIs.

## Before declaring it working

```
cd backend  && ../.venv/Scripts/python.exe -m pytest -q      # 385 as of play v1.3
cd frontend && npm run test && npm run build:lead && npm run build:play   # 135 vitest as of play v1.3
```
`build:play` must emit `dist/index.html` referencing `assets/play-*.js`; the
lead CSS bundle must contain no Tailwind (`grep -c tailwind dist/assets/index-*.css` → 0).
