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

(macOS/Linux: `../.venv/bin/uvicorn`.) Both dev scripts use `--strictPort`:
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
- **Load example** → **Analyze** (West, single dummy, 20 deals). Expect the
  deterministic result: **12 ✓ / 2 ~ / 1 ✗ of 15 graded, 3 forced**, total
  loss 0.70; `/api/play/analyze` 200 in ~1 s.
- Click the `5E ♥2` suboptimal row: the viewer jumps to 17/37 and the options
  list opens with ♥K best at 7.80.
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
cd backend  && ../.venv/Scripts/python.exe -m pytest -q      # 342 as of play v1.0
cd frontend && npm run test && npm run build:lead && npm run build:play
```
`build:play` must emit `dist/index.html` referencing `assets/play-*.js`; the
lead CSS bundle must contain no Tailwind (`grep -c tailwind dist/assets/index-*.css` → 0).
