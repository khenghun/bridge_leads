# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A web app that simulates the **opening lead** in contract bridge. Given the opening leader's hand, the contract, and optional constraints on the three unseen hands, it Monte-Carlo generates consistent deals, double-dummy solves each candidate lead, and ranks leads by **matchpoints** or **IMPs**.

Since **v4** it is a client/server app: a **FastAPI** backend (`backend/`) wrapping the simulation engine, and a **React + Vite + TypeScript** frontend (`frontend/`), containerised with `docker-compose`. (v1–v3 were a single Streamlit script; that UI has been removed.)

**No AI / LLM integration.** This is pure simulation. Do not add model calls, embeddings, or agent code.

## Stack & running

### Backend (`backend/`)

Python deps live in a project venv at `.venv/` (gitignored). The engine is pure Python; FastAPI is the HTTP layer.

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt   # Windows
cd backend && ../.venv/Scripts/uvicorn app.main:app --reload              # dev server on :8000
```

- `fastapi` / `uvicorn` — HTTP layer (`backend/app/`).
- `endplay` (0.5.x) — provides `Deal`, `Player`, `Denom`, `Contract`, and the double-dummy solver (`endplay.dds.solve_board` / `solve_all_boards`). DDS is the trick-count oracle and `Contract.score()` is the scoring oracle; do not reimplement either.

### Frontend (`frontend/`)

```
cd frontend
npm install
npm run dev        # Vite dev server; proxies /api → http://localhost:8000
npm run build      # tsc -b && vite build (typecheck + production bundle)
npm run test       # vitest (pure helpers in src/lib/bridge.ts)
```

### Docker (whole stack)

```
docker compose up --build     # frontend on http://localhost, backend proxied at /api
```

## Architecture

The **engine** is framework-agnostic and unchanged from v3 — it has no HTTP/UI imports.

- `backend/engine/deal_generator.py` — `generate_deal(known_hands, hcp_constraints, suit_constraints, acceptors=None)` builds constrained random deals (known cards + per-player HCP and per-suit length bounds; `acceptors` reject finished hands, used for disjunctive shapes). Vendored from `bridge_ai/solver/deal_generator_v2.py`. **Keyed by player letter** `'N'/'E'/'S'/'W'`.
- `backend/engine/lead_simulator.py` — `simulate_opening_lead(leader_hand, level, strain, declarer, vul, penalty, constraints, num_simulations, seed=None, max_samples=10)` is the entry point. Generates deals (leader's hand fixed, others constrained), batch-DDS solves, scores each candidate lead, returns leads ranked by IMPs with MP%/defeat-rate + contract-setting sample deals. Adapted from `bridge_ai/solver/mce_defense_sim.py`.
- `backend/engine/scoring.py` — `declarer_score()` wraps `endplay`'s `Contract.score()`; `aggregate()` does the MP/IMP rollup; `imps()` is the standard IMP scale. **Don't hand-roll the score tables** — `endplay` computes the duplicate-bridge score; we only aggregate.
- `backend/engine/shapes.py` / `shape_parser.py` — disjunctive `(A or B or C)` shape constraints: text mini-language → terms → (envelope box + acceptor predicate).
- `backend/engine/auctions.py` — predefined demo auctions (contract + constraint presets).

The **backend HTTP layer** (`backend/app/`) is a thin wrapper — no simulation logic:

- `app/schemas.py` — Pydantic request/response models mirroring the engine's dict contracts (seat/strain/vul enums, HCP 0–40, level 1–7, deals 100–1000).
- `app/service.py` — ports the glue that used to live in `app.py`: leader-hand validation, shape-text parsing, constraint assembly, and a deterministic result cache (in-process LRU+TTL, `seed=0`, replacing the old `@st.cache_data`).
- `app/routes.py` — `/api/health`, `/api/auctions`, `/api/validate/shape`, `/api/simulate`. `POST /api/simulate` is a **plain `def`** so Starlette runs the blocking DDS solve in a threadpool.
- `app/main.py` — FastAPI instance + CORS (dev only; prod is same-origin behind nginx).

The **frontend** (`frontend/src/`): `api/` (typed client + types mirroring the schemas), `lib/bridge.ts` (pure helpers ported from the old `app.py` — suit colours/symbols, contract/PBN parse, `leaderSeat`, random hand), `components/` (one per old UI block), `App.tsx` (state + sidebar).

`endplay` scoring recipe (used in `scoring.py`): `Contract(f"{level}{denom}{declarer}")` where denom is `NT/S/H/D/C`; set `.penalty` (`Penalty.doubled` etc.) and `.result = declarer_tricks - (6 + level)` (signed over/undertricks), then `.score(Vul.<x>)` returns the **declarer's** points. The leader is a defender, so leader score = `-declarer_score`.

Source material lives at `C:\kh\bridge_ai\solver\` — reuse the v2 modules (`deal_generator_v2`, `mce_defense_sim`). Ignore everything under `bridge_ai/ai/` and `bridge_ai/ben/` (AI/neural-net, out of scope).

## Conventions (easy to get wrong)

- **Card format is endplay's `suit+rank`**: `SA`, `HK`, `DT`, `C2`. Suit first, rank second. Ranks use `T` for ten (not `10`).
- **PBN hand strings** are `spades.hearts.diamonds.clubs`, suits high-to-low (e.g. `AK8.Q95.J982.Q43`). PBN deal order is `N:` then N E S W.
- **The simulator returns candidate-lead cards with the unicode suit symbol** (`♥Q`), not the `HQ` input form — the frontend maps the leading symbol to a suit colour/letter (`SYMBOL_COLOR` / `SYMBOL_LETTER` in `lib/bridge.ts`).
- **Opening leader is LHO of declarer.** At lead time only the leader's 13 cards are known — **dummy is NOT visible yet**, so the leader's hand is the only fixed hand. Declarer, dummy, and partner are all simulated under the user's constraints.
- Engine constraint dict (passed to `simulate_opening_lead`) is **keyed by player letter**, not endplay `Player` objects: `{'hcp': {'S': (min,max)}, 'suit_length': {'S': {'H': (min,max)}}, 'shapes': {'S': [ {suit:(min,max)}, ... ]}, 'fixed_cards': {'N': ['SA', ...]}}`. Either HCP/length bound may be `None` for unbounded. Only the three non-leader seats are constrainable. The API accepts shapes as **text** (the mini-language) and `service.py` parses them to terms.
- DDS `solve_board` returns tricks for the side **on lead**; convert to declarer tricks → contract result → score with care about whose perspective you're in.

## Performance & determinism (easy to get wrong)

DDS is ~99% of runtime; deal generation is negligible (~0.06s / 500 deals). Don't try to parallelize the Python generator — optimize/seed it instead.

- **Batch the DDS solve in chunks of `_dds.MAXNOOFBOARDS` (200).** `solve_all_boards` multithreads internally (`SolveAllBoardsBin`), but its board array caps at 200 — passing more **raises**, which previously fell back to a single-threaded `solve_board` loop (~5× slower). `lead_simulator._solve_all()` chunks to keep the parallel path; don't call `solve_all_boards` on >200 deals directly.
- **DDS thread cap:** `lead_simulator` calls `_dds.SetMaxThreads(min(cpu, 4))` at import. DDS otherwise grabs every core and allocates memory per thread — bad under concurrent public load. Override with env var `BRIDGE_DDS_THREADS` (`0` = auto-detect all cores); `docker-compose.yml` sets it per container.
- **Docker gotcha:** endplay's bundled DDS `.so` links against the OpenMP runtime, so the backend image (`python:3.12-slim`) must `apt-get install libgomp1` — the one non-obvious container dependency.
- **Determinism:** `generate_deal(..., rng=)` takes a `random.Random` instance. `simulate_opening_lead(..., seed=)` builds a private `random.Random(seed)` — reproducible and thread-safe. `service.run_simulation()` calls it with `seed=0` behind an in-process LRU+TTL cache keyed on the canonical request, so identical inputs reuse the cached result (same contract the old `@st.cache_data` provided).

## Tests

- **Backend:** pytest in `backend/tests/` covers `engine/` (deal generation, scoring, simulator, shapes) and the API (`test_api.py`, via FastAPI `TestClient`). `backend/pytest.ini` sets `pythonpath = .` so tests import `engine` and `app` without an install. Run from `backend/`:
  ```
  .venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
  cd backend && ../.venv/Scripts/python.exe -m pytest
  ```
- **Frontend:** vitest covers the pure helpers in `src/lib/bridge.ts` (`npm run test`). React components are not unit-tested; verify the UI by running the app.

## Matchpoints vs IMPs

Both modes start from the same per-deal raw score (from the leader's/defense perspective; better = more) that `endplay` computes from tricks + vulnerability. They differ only in how candidate leads are **aggregated** across the simulated deals:

- **Matchpoints (MP):** frequency-based, comparing leads head-to-head per deal. For each simulated deal, rank each candidate lead's score against the other candidates; a lead scores a "matchpoint" for every alternative it beats (half for a tie). Report each lead's average MP% across deals. The size of a gain doesn't matter — only how often one lead beats another. Favors the lead that is best *most often*.
- **IMPs:** magnitude-based. Convert score differences to IMPs via the standard IMP scale, then average each lead's IMPs across deals (vs the per-deal datum = mean of all candidate leads). A single large swing (setting a game/slam) outweighs many small ones. Favors the lead with the best *expected* result, accepting more variance.

The scoring-mode toggle is **frontend-only** — it re-ranks the same `/api/simulate` response (both MP% and IMPs are always returned), it does not re-run the simulation.
