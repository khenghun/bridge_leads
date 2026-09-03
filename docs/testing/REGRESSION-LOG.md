# Regression runs

Appended by `scripts/regression.py log` (see the `test-deployed` skill). SHA is what `origin/main` pointed at for prod runs (the deploy tags images with `github.sha`), `HEAD` for local runs.

| Date | Product | Version | Target | SHA | Tier | Result | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | play | v1.2 | prod | `b5f34d1` | smoke+v1.2 | pass | P-1.0-1, P-1.2-1, P-1.2-2 on prod after the v1.2 deploy; What's new still showed In development (flags flipped locally afterwards) |
| 2026-09-01 | lead | v2.2 | prod | `b5f34d1` | smoke | pass | L-1.0-1, L-1.0-2, L-2.0-1, L-2.2-1, L-2.2-2 — baseline pins captured on this run |
| 2026-09-03 | play | v1.3 | prod | `210ff34` | smoke+v1.3 | pass | Scripted Playwright run on prod after the v1.3 + v1.4-perf deploy: smoke (P-1.0-1/2, P-1.1-1, P-1.2-1/2, P-1.3-1/2) and full v1.3 (P-1.3-3 strict ~20 min, P-1.3-4/5/6) all pass; header showed v1.3 while still flagged unreleased (fixed) and the expert sampled count read 1406 vs the 1371 pin (engine change, re-pinned) |
