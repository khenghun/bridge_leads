# Regression runs

Appended by `scripts/regression.py log` (see the `test-deployed` skill). SHA is what `origin/main` pointed at for prod runs (the deploy tags images with `github.sha`), `HEAD` for local runs.

| Date | Product | Version | Target | SHA | Tier | Result | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | play | v1.2 | prod | `b5f34d1` | smoke+v1.2 | pass | P-1.0-1, P-1.2-1, P-1.2-2 on prod after the v1.2 deploy; What's new still showed In development (flags flipped locally afterwards) |
| 2026-09-01 | lead | v2.2 | prod | `b5f34d1` | smoke | pass | L-1.0-1, L-1.0-2, L-2.0-1, L-2.2-1, L-2.2-2 — baseline pins captured on this run |
