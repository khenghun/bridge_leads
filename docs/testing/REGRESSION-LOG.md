# Regression runs

Appended by `scripts/regression.py log` (see the `test-deployed` skill). SHA is what `origin/main` pointed at for prod runs (the deploy tags images with `github.sha`), `HEAD` for local runs.

| Date | Product | Version | Target | SHA | Tier | Result | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | play | v1.2 | prod | `b5f34d1` | smoke+v1.2 | pass | P-1.0-1, P-1.2-1, P-1.2-2 on prod after the v1.2 deploy; What's new still showed In development (flags flipped locally afterwards) |
| 2026-09-01 | lead | v2.2 | prod | `b5f34d1` | smoke | pass | L-1.0-1, L-1.0-2, L-2.0-1, L-2.2-1, L-2.2-2 — baseline pins captured on this run |
| 2026-09-03 | play | v1.3 | prod | `210ff34` | smoke+v1.3 | pass | Scripted Playwright run on prod after the v1.3 + v1.4-perf deploy: smoke (P-1.0-1/2, P-1.1-1, P-1.2-1/2, P-1.3-1/2) and full v1.3 (P-1.3-3 strict ~20 min, P-1.3-4/5/6) all pass; header showed v1.3 while still flagged unreleased (fixed) and the expert sampled count read 1406 vs the 1371 pin (engine change, re-pinned) |
| 2026-09-08 | play | v1.3 | prod | `4d672ad` | smoke+v1.4-smoke | pass | Post-deploy sanity on prod at 4d672ad: play smoke P-1.0-1/2, P-1.1-1, P-1.2-1/2, P-1.3-1/2, P-1.4-3/5/7 all match the v1.4 pins (escalation on; expert run 1380 of 1943, 0.41 · 0.76 IMPs, 18 requests ~2 min); What's new shows v1.3 with v1.4 In development; console clean |
| 2026-09-08 | lead | v2.2 | prod | `4d672ad` | smoke | pass | L-1.0-1/2, L-2.0-1, L-2.2-1/2 on prod after the play v1.4 deploy: every pinned row and the too-close-to-call card unchanged; console clean |
| 2026-09-08 | play | v1.4 | local | `4d672ad` | full-v1.4-bench | pass | P-1.4-1/2 re-baselined: strict bench o7/c7/c14 at 100 deals on a fresh 16-thread API after dropping the unfiltered trigger; compare_bench passes on all three against the trigger-B baselines (statuses identical), 936/1013/665 s -> 801/817/496 s; new docs/play/bench/*-strict100 committed |
