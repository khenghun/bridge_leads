# Roadmap — Play Solver

Version history and planned work for the play solver, the second product in
this repo. Releases are numbered **v1.0, v1.1, …** on the play solver's own
line — `frontend/src/apps/play/changelog/releases.ts` is the source of truth
(it is what the app's *What's new* panel shows) and this file follows it. The
lead/contract app has its own line in [`../lead/ROADMAP.md`](../lead/ROADMAP.md);
what the two share and why is in
[`../two-products-one-repo.md`](../two-products-one-repo.md).

## v1.0 — Replay and grade a hand 🟡 (built 2026-08-27, not yet deployed)

Design: [`v1.0-play-solver-plan.md`](v1.0-play-solver-plan.md).

A port of the earlier `bridge_ai` play solver with its AI/RAG layers removed.
Load a completed hand (a BBO `.lin` file), step through the play trick by
trick, and have every decision one seat made graded by Monte-Carlo +
double-dummy: what was the best card given what that player could see?

- **Engine** `backend/engine/play/`: `state.py` (pure replay + validation)
  and `grader.py` (one Monte-Carlo grader parameterised by the viewing seat;
  dummy hidden at the opening lead, played cards pinned, show-outs cap suit
  length, everything through the shared sampler and `dds_runtime`).
- **API** `backend/app_play/` — its own FastAPI app, stateless:
  `/api/play/analyze`, `/api/play/position` (the interactive primitive),
  `/api/play/health`, plus `/api/validate/shape` for the shared constraints
  editor. Query log tool `play`.
- **Frontend** `frontend/src/apps/play/` on its own entry (`play.html`,
  Tailwind scoped to it): browser-side LIN parser (`lib/lin.ts`), trick
  navigator with keyboard steps, table with the current trick and
  struck-through played cards, auction grid, decisions table with expandable
  options and a *What's new* panel.
- Left behind from the source: the double-run analyze, dropped doubled
  contracts, defense constraints on the known hands, unlocked/unbatched DDS,
  the rejection sampler, a session token in a tracked file.
- Tests: 91 backend (state, grader, API) + 33 frontend (LIN grammar,
  declarer inference, trick winners, request builder); verified in the real
  UI with Playwright.

**To ship:** `deploy/play/` stack + `deploy-play` job (in repo), a domain,
its DNS record, and the edge vhost in the FBO repo.

## Planned

- **BBO import by username** — a server-side fetch (`bridge_ai/bbo_hands.py`
  has the Python), token from the environment; then the HTML→LIN parse.
- **Play it from here** — interactive play from any position on the same
  table, on `/api/play/position`.
- **Compare two lines / trace the optimal line / grade all four seats** —
  engine bodies exist in the source's `bridge_tools.py`, never had a UI.
- **Scoring in points/IMPs** rather than tricks; `engine/scoring.py` is ready.
