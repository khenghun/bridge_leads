# End-to-end regression tests

Browser tests (Playwright) that drive the real UI against a **running stack**.
Unlike the vitest unit tests (`src/lib/bridge.ts` pure helpers), these exercise
the full path — React → nginx → FastAPI → DDS — so they also catch container /
proxy / engine-load regressions.

Assertions are **structural** (the flow works, results are well-formed: 13
ranked leads, a recommendation banner, sample deals, the MP↔IMP toggle
re-ranks). They intentionally do **not** pin exact numbers, so routine engine
tuning won't turn them red.

## One-time setup

```
cd frontend
npm install
npx playwright install chromium     # downloads the browser binary
```

## Running

The stack must already be up. Point `E2E_BASE_URL` at it (default `http://localhost`):

```
# against the Docker stack (docker compose up -d)
npm run test:e2e

# against the Vite dev server (npm run dev, proxies /api -> :8000)
E2E_BASE_URL=http://localhost:5173 npm run test:e2e
```

`npm run test:e2e:report` opens the last HTML report.

## Adding cases

Drop new `*.spec.ts` files in this folder. Reuse the fixed leader hand
(`T.KT932.Q2.T9843`, deterministic under the engine's `seed=0`) or a demo
auction for reproducibility. When testing a new feature or a bug fix, add a spec
that would have failed before the change.
