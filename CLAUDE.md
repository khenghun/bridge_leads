# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two Monte-Carlo + double-dummy bridge tools sharing one engine, shown as tabs of one web app (plus a third, static **What's new** tab), and a third tool that is a **separate web app** on the same engine (see 3. below):

1. **Opening Lead Simulator** (v1–v6). Given the opening leader's hand, the contract, and optional constraints on the three unseen hands, generate consistent deals, double-dummy solve each candidate lead, and rank leads by **matchpoints** or **IMPs**.
2. **Optimal Contract Calculator** (v7). Given *your own* hand and the same style of constraints on partner's and the opponents' hands, rank the **contracts your side could be in** — where do these two hands belong?

Both sample deals the same way and score with the same tables; they differ only in the DDS call (`solve_all_boards` per lead vs one DD **table** per deal) and in what gets ranked.

3. **Play Solver** (`docs/play/v1.0-play-solver-plan.md`). Load a completed hand (a BBO `.lin` file), step through the play, and grade every decision one seat made: at each of that seat's turns the two hands it could not see are sampled under the play-so-far and the user's constraints, and every legal card is DD-solved. **A second product, not a fourth tab** — its own FastAPI app (`backend/app_play/`, same image, own container), its own frontend entry (`frontend/play.html` → `src/apps/play/`, Tailwind scoped to that entry), its own domain and deploy stack. The API is stateless: LIN is parsed in the browser (`lib/lin.ts`) and each request carries the four hands, the contract and the play so far.

It is a client/server app: a **FastAPI** backend (`backend/`) wrapping the simulation engine, and a **React + Vite + TypeScript** frontend (`frontend/`), containerised with `docker-compose`. (It began as a single Streamlit script; that UI has been removed.)

**The two products are versioned, documented and released separately** — think of the repo as shared only for the libraries. Each has its own line: the lead/contract app is `v1.0, v1.1, … v2.2`, the play solver starts again at `v1.0`. The source of truth for each is its in-app changelog data — `frontend/src/apps/changelog/releases.ts` (lead, the *What's new* tab) and `frontend/src/apps/play/changelog/releases.ts` (play, the *What's new* panel) — and the roadmaps follow it: `docs/lead/ROADMAP.md` and `docs/play/ROADMAP.md`, with plan docs beside them as `docs/<product>/<version>-<topic>-plan.md` (root `ROADMAP.md` is just the index; `docs/two-products-one-repo.md` is the repo-level architecture). Everything in the lead app through 2026-07-16 is v1.0, so it has three `v1.0-*` plan docs; the six *development milestones* inside the lead ROADMAP's v1.0 section are an older internal numbering that survives only there — don't confuse "milestone 4" with "v1.1". **Shipping something a player would notice means adding an entry to that product's `releases.ts`** — keep it plain-language, no module names or test counts.

**No AI / LLM integration.** This is pure simulation. Do not add model calls, embeddings, or agent code.

## Stack & running

### Backend (`backend/`)

Python deps live in a project venv at `.venv/` (gitignored). The engine is pure Python; FastAPI is the HTTP layer.

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt   # Windows
cd backend && ../.venv/Scripts/uvicorn app.main:app --reload              # dev server on :8000
cd backend && ../.venv/Scripts/uvicorn app_play.main:app --reload --port 8001   # play solver API (its own app), beside the lead API
```

- `fastapi` / `uvicorn` — HTTP layer (`backend/app/`).
- `endplay` (0.5.x) — provides `Deal`, `Player`, `Denom`, `Contract`, and the double-dummy solver (`endplay.dds.solve_board` / `solve_all_boards`). DDS is the trick-count oracle and `Contract.score()` is the scoring oracle; do not reimplement either.

### Frontend (`frontend/`)

```
cd frontend
npm install
npm run dev        # Vite dev server; proxies /api → http://localhost:8000
npm run dev:play   # the play solver on :5174 (open /play.html); proxies /api → :8001
npm run build      # = build:lead — tsc -b && vite build (typecheck + production bundle)
npm run build:play # the play app via vite.play.config.ts
npm run test       # vitest (pure helpers in src/lib/*.ts, contract ranking)
```

### Docker (whole stack)

```
docker compose up --build     # frontend on http://localhost, backend proxied at /api
```

### Running & checking both apps locally

Two products = **four dev processes**, each pair on its own ports: lead API `:8000` + `npm run dev` (`:5173`), play API `:8001` (`uvicorn app_play.main:app --port 8001`) + `npm run dev:play` (`:5174`, open `/play.html`). Health-check **through the Vite proxies** (`:5173/api/health`, `:5174/api/play/health`), not just the APIs. Both dev scripts are `--strictPort` so a taken port fails loudly. Two gotchas: the play Vite config has its own `cacheDir` (`node_modules/.vite-play`) — without it the two dev servers invalidate each other's pre-bundled React and the play page goes blank with `504 Outdated Optimize Dep`; and stopping a backgrounded dev-server shell can leave the node/python child bound to the port with the old config (`netstat -ano | grep :5174`, then `taskkill`). The full boot-and-verify runbook, including the expected deterministic result for the play example, is the project skill **`.claude/skills/run-apps/SKILL.md`** (tracked) — use it before any browser verification.

## Architecture

Both tools are split the same way at every layer: **shared core, then one package per tool.**

```
backend/engine/            shared: sampling, constraints, scoring, DDS runtime
backend/engine/lead/       opening-lead simulator + demo auctions
backend/engine/contract/   optimal-contract calculator
backend/engine/play/       play solver: replay state + the per-decision grader
backend/app/common/        shared: result cache, constraint parsing, base schemas, query log
backend/app/lead/          /api/simulate, /api/auctions, /api/validate/shape, /api/health
backend/app/contract/      /api/contract/simulate
backend/app_play/          the play solver's OWN FastAPI app: /api/play/analyze, /api/play/position
frontend/src/components/   shared UI (HandEntry, ConstraintsEditor, DealDiagram, Changelog)
frontend/src/lib/          shared pure helpers (bridge.ts, share.ts, lin.ts)
frontend/src/apps/lead/    lead tab
frontend/src/apps/contract/ contract tab
frontend/src/apps/changelog/ What's new tab — releases.ts is the version source of truth
frontend/src/apps/play/    the play solver app (own entry play.html / play-main.tsx, own Tailwind css, own changelog/releases.ts)
```

Two frontend entries, one source tree: `npm run build:lead` (→ `index.html`) and `npm run build:play` (`vite.play.config.ts` → `play.html`, emitted as `index.html`); the Docker build arg `APP` picks one and the matching `nginx.${APP}.conf`. `dev:play` serves the play app on :5174. Tailwind's `content` is limited to the play files, so the lead bundle carries none of it.

Put anything a second tool could want in the shared layer, not in a tool package — that is how `sampling.py` and `dds_runtime.py` came to exist.

The **engine** is framework-agnostic — it has no HTTP/UI imports.

- `backend/engine/dds_runtime.py` — **the only place that touches DDS.** Owns the thread cap, the global re-entrancy lock, and the two batch entry points (`solve_all`, `calc_tables`). See the performance section below; calling DDS from anywhere else is a bug.
- `backend/engine/sampling.py` — constrained deal generation shared by both tools: `build_known_and_constraints` (public constraint dict → generator format, incl. shape compilation, the single suit-quality tuple, and `resolve_fixed_cards`), `check_hcp_feasibility` / `check_length_feasibility`, and `generate_layouts` (exact sampler first, legacy fallback). Parameterised by **own seat** — the one hand the user knows (the leader's hand, or your own). Pinned `fixed_cards` are merged straight into `known_hands`, so every downstream consumer — both samplers, the HCP check, the quality DP's base counts — treats them exactly like the user's own 13 cards rather than as a constraint to test afterwards.
- `backend/engine/honor_sampler.py` — `ExactDealSampler`: the primary deal source. Samples **exactly uniformly** over deals consistent with known cards + per-seat HCP bounds via an integer-count DP over honor value classes (A/K/Q/J), then enforces suit-length/shape constraints by rejection. Tight HCP bands cost nothing (no HCP rejection at all). `.total` is the exact count of HCP-consistent deals (0 = infeasible). Build once per constraint set (~10–30 ms, ~15–45 ms with a suit-quality constraint), then `sample(rng)` per draw.
- `backend/engine/suit_quality.py` — the one suit-quality constraint: **good** = 2 of AKQ *or* 3 of AKQJT, **poor** = anything worse (a plain complement, so it matches ~70% of holdings and filters weakly). Exactly one `(seat, suit, level)` per simulation — it models the single player who described a suit in the auction, and that ceiling is what keeps the sampler's DP small. Enforced **inside** the DP, not by rejection: honor classes split by the constrained suit (`[SA]` + `[HA,DA,CA]`), the constrained suit's ten joins as a zero-value class (`HONORS` is A/K/Q/J, so `T` is a spot card everywhere else), and two state dimensions carry the seat's running top-3 / J-T counts. So quality honors are dealt in the same pass that satisfies HCP and the two constraints prune each other — `.total` then counts HCP- **and** quality-consistent deals, giving exact feasibility. The module's `predicate()` is only for the legacy fallback generator.
- `backend/engine/deal_generator.py` — `generate_deal(known_hands, hcp_constraints, suit_constraints, acceptors=None)` is the legacy rejection sampler (steered placement, *approximately* uniform), kept as the fallback for pathologically tight shape constraints where the exact sampler's rejection step starves. Vendored from `bridge_ai/solver/deal_generator_v2.py`. **Keyed by player letter** `'N'/'E'/'S'/'W'`.
- `backend/engine/lead/simulator.py` — `simulate_opening_lead(leader_hand, level, strain, declarer, vul, penalty, constraints, num_simulations, seed=None, max_samples=10)` is the entry point. Generates deals (leader's hand fixed, others constrained; `ExactDealSampler` first, legacy fallback after 3000 rejected draws with zero accepts), batch-DDS solves, scores each candidate lead, returns leads ranked by IMPs with MP%/defeat-rate + contract-setting sample deals + a per-deal `deals` matrix (`cards` + one record per deal with layout/tricks/scores per candidate lead, index-aligned — powers the frontend's compare-leads feature). Raises `ValueError` on infeasible HCP constraints (pre-checked: seat minimums vs the deck's 40 HCP, and the sampler's exact count). Adapted from `bridge_ai/solver/mce_defense_sim.py`.
- `backend/engine/scoring.py` — `declarer_score()` wraps `endplay`'s `Contract.score()`; `aggregate()` does the MP/IMP rollup; `imps()` is the standard IMP scale. **Don't hand-roll the score tables** — `endplay` computes the duplicate-bridge score; we only aggregate.
- `backend/engine/shapes.py` / `shape_parser.py` — disjunctive `(A or B or C)` shape constraints: text mini-language → terms → (envelope box + acceptor predicate).
- `backend/engine/lead/auctions.py` — predefined demo auctions (contract + constraint presets).
- `backend/engine/contract/candidates.py` — the **20-contract** candidate set and its labels. Undoubled, every partscore level in a strain scores the same for a given trick count and the lowest never scores less, so per strain there are exactly four decisions: `partscore (1-level) | game (3NT/4M/5m) | 6 | 7`. That pruning is a scoring argument, not a display convenience — it is also why the ranked table never fills with 4♠/3♠/2♠ near-duplicates. Partscores are labelled `♠ partscore`, not `1♠`.
- `backend/engine/play/state.py` — pure replay: `replay(hands, strain, declarer, play)` validates the play (right hand, follows suit) and returns the position (tricks + winners, current partial trick, who is on play, remaining cards, tricks per side); `legal_cards`, `trick_winner`. Raises `ValueError` naming the offending play index.
- `backend/engine/play/grader.py` — one Monte-Carlo grader parameterised by the **view** seat. `grade_position` samples the two hands that seat cannot see (declarer sees dummy; a defender sees dummy except at the opening lead), consistent with the play so far — cards an unseen seat already played are pinned via `fixed_cards`, a seat that showed out has that suit capped — replays each sample to the position and solves all samples in one `dds_runtime.solve_all` batch (`solve_board` prices every legal card of the player on play at once). `grade_play` walks the play and grades every decision of one seat (declarer's include dummy's cards); single-legal-card positions are `forced`, not solved. Method `double_dummy` solves the actual deal instead of sampling. Tricks are reported for the graded side; status thresholds on `diff = actual − best`: optimal (<0.1), good (≥ −0.3), else suboptimal.
- `backend/engine/contract/simulator.py` — `simulate_contracts(hand, seat, vul, constraints, num_deals, strains, seed=None)`. Samples deals with *our* hand fixed, gets one DD table per deal (`dds_runtime.calc_tables`), then scores all 20 contracts × both declarers from that table (pure arithmetic — the candidate space is free, deal count is the only cost driver). Returns per-candidate `make_rate` / `mean_tricks` / `mean_score` / `fail_mean_score` / `seat_delta`, opponent context (`opps_game_rate`, `par_competitive_rate` via `endplay.dds.par` on the same table), and the per-deal `deals` matrix. **We declare here, so the declarer score IS our score** — no sign flip, unlike the lead simulator where we defend. It deliberately does **not** rank: the frontend does that from the matrix so switching mode or benchmark is instant.

The **backend HTTP layer** (`backend/app/`) is a thin wrapper — no simulation logic:

- `app/common/schemas.py` — shared Pydantic vocabulary (seat/strain/vul enums, HCP 0–40, `Constraints`, `DealRecord`); `app/lead/schemas.py` and `app/contract/schemas.py` add each tool's payloads (lead deals 100–1000; contract deals 50–500, because a DD table costs ~5× a lead solve).
- `app/common/cache.py` — `ResultCache`: in-process LRU+TTL with dogpile protection (`get_or_compute`). Each service owns an instance; every run uses `seed=0`, which is what makes results cacheable.
- `app/common/constraints.py` — `validate_hand`, `build_constraints` (shape *text* → terms), `build_fixed_cards` (card syntax + no card claimed twice), `validate_shape`. The checks that need the user's own hand live in the engine instead, so calling it directly is still safe.
- `app/common/querylog.py` — one SQLite row per simulation: timestamp, tool, request body. Nothing else — no IP, no session, no response. **Off unless `BRIDGE_QUERY_LOG` names a file**, so dev and tests write nothing; prod sets it in `deploy/lead/docker-compose.prod.yml` against a bind-mounted `./data`. Both simulate routes call it *before* running, so an infeasible query (422) is logged too. Every write is best-effort and swallows its own errors — a full disk must cost you the log, not the app. Routes read it through the module (`querylog.QUERY_LOG`) so tests can swap the singleton. There is deliberately **no endpoint** to read it: `scripts/view_queries.py` copies the file down over scp and decodes each row (`--summary` for counts, `--json` to pipe). An empty result means nobody has used the app since logging started — that is an answer, not a failure.
- `app/lead/routes.py` — `/api/health`, `/api/auctions`, `/api/validate/shape`, `/api/simulate`.
- `app/contract/routes.py` — `/api/contract/simulate`.
- `app_play/` — the play solver's own app (`main.py`, `routes.py`, `schemas.py`, `service.py`), importing `app.common` for schemas, cache, constraints and the query log (tool `'play'`). It also serves `/api/validate/shape`, which the shared `ConstraintsEditor` calls. It runs as a second container from the same image (`uvicorn app_play.main:app`, set by `deploy/play/docker-compose.prod.yml`'s `command:`). Keeping it out of `app/main.py` is what makes the two products deployable independently.
- All simulate/analyze handlers are **plain `def`** so Starlette runs the blocking DDS solve in a threadpool.
- `app/main.py` — FastAPI instance + CORS (dev only; prod is same-origin behind nginx) + both routers.

The **frontend** (`frontend/src/`):

- `App.tsx` — shell only: the tab bar, the light-mode toggle, and the shared MP/IMP mode. All tabs stay **mounted** (inactive ones are `hidden`) so switching never discards a simulation that took ten seconds. The active tab lives in the URL hash (`#lead` / `#contract` / `#changelog`); no router dependency.
- `api/` — `http.ts` (fetch helpers + FastAPI `detail` unwrapping), `lead.ts` / `contract.ts` (one call per endpoint), `types.ts` (shared vocabulary + the generic `CandidateMatrix`), `leadTypes.ts` / `contractTypes.ts` (per-tool payloads, mirroring the Pydantic schemas by hand).
- `lib/bridge.ts` — pure helpers shared by both tools: suit colours/symbols, contract/PBN parse, seat maths, `imps()`, `compareCandidates()` (generic over the per-deal matrix; `compareLeads()` is a thin alias) and `rankVsBenchmark()`.
- `components/` — the UI both tools use: `HandEntry` (takes `seat` + `role`), `ConstraintsEditor` (takes `seats: [Seat, label][]` and `cardIssues` — it does **not** derive seats itself, nor validate pinned cards, since the clash may be with the one hand it never sees), `DealDiagram`.
- `apps/lead/`, `apps/contract/` — one folder per tool: its own `*App.tsx` (state + sidebar) and its own result views. `apps/contract/ranking.ts` holds the pure ranking logic (best declarer per contract, benchmark options, the thin-edge flag) and is unit-tested.
- `apps/changelog/` — the *What's new* tab: `releases.ts` (data + the public version numbers) and `ChangelogApp.tsx` (presentation). No API call, no state.

`endplay` scoring recipe (used in `scoring.py`): `Contract(f"{level}{denom}{declarer}")` where denom is `NT/S/H/D/C`; set `.penalty` (`Penalty.doubled` etc.) and `.result = declarer_tricks - (6 + level)` (signed over/undertricks), then `.score(Vul.<x>)` returns the **declarer's** points. The leader is a defender, so leader score = `-declarer_score`.

Source material lives at `C:\kh\bridge_ai\solver\` — reuse the v2 modules (`deal_generator_v2`, `mce_defense_sim`). Ignore everything under `bridge_ai/ai/` and `bridge_ai/ben/` (AI/neural-net, out of scope).

## Conventions (easy to get wrong)

- **Card format is endplay's `suit+rank`**: `SA`, `HK`, `DT`, `C2`. Suit first, rank second. Ranks use `T` for ten (not `10`).
- **PBN hand strings** are `spades.hearts.diamonds.clubs`, suits high-to-low (e.g. `AK8.Q95.J982.Q43`). PBN deal order is `N:` then N E S W.
- **The simulator returns candidate-lead cards with the unicode suit symbol** (`♥Q`), not the `HQ` input form — the frontend maps the leading symbol to a suit colour/letter (`SYMBOL_COLOR` / `SYMBOL_LETTER` in `lib/bridge.ts`).
- **Opening leader is LHO of declarer.** At lead time only the leader's 13 cards are known — **dummy is NOT visible yet**, so the leader's hand is the only fixed hand. Declarer, dummy, and partner are all simulated under the user's constraints.
- **In the play solver all four hands are known** (a LIN file has them) but the grader deliberately hides two of them per decision — grading is "best card given what this player could see". `method: 'double_dummy'` is the hindsight answer. The DDS perspective trap applies at every mid-trick position: `solve_board` returns future tricks for the side **on play**, so graded-side tricks = tricks already won + future (flipped when the other side is on play).
- **In the contract calculator only your own hand is fixed**; partner *and* both opponents are simulated under the constraints (the editor shows partner / LHO / RHO). Candidate declarers are you and partner, and the DD table prices both.
- Engine constraint dict (same for both tools) is **keyed by player letter**, not endplay `Player` objects: `{'hcp': {'S': (min,max)}, 'suit_length': {'S': {'H': (min,max)}}, 'shapes': {'S': [ {suit:(min,max)}, ... ]}, 'quality': {'S': {'H': 'good'}}, 'fixed_cards': {'N': ['SA', ...]}}`. Either HCP/length bound may be `None` for unbounded. Only the three seats the user cannot see are constrainable. The API accepts shapes as **text** (the mini-language) and `app/common/constraints.py` parses them to terms. `quality` accepts **at most one entry in total** across every seat and suit; more raises (→ 422), and the frontend enforces it by clearing the previous pick (`applyQuality` in `lib/bridge.ts`), so users never hit that error.
- **`fixed_cards` is the escape hatch for what the vocabulary cannot say** ("East holds ♥AK"). Cards are endplay form (`HA`, `DT`) and a card may be claimed once across the whole table and never from the user's own hand — the UI (`fixedCardIssues` in `lib/bridge.ts`) checks that while typing and disables Simulate, so the matching 422 is a backstop, not the normal path. It composes with everything else rather than layering on top: pinned honours count toward the seat's HCP band and are seen by the quality DP, so `{fixed_cards: {N: ['HA','HQ']}, quality: {N: {H: 'poor'}}}` is correctly reported infeasible.
- **A seat can attract more than one acceptor predicate** (a shape *and* a suit quality). `sampling.build_known_and_constraints` collects them per seat and ANDs them via `_all_of` — don't go back to `acceptors[p] = predicate`, which silently drops one.
- DDS `solve_board` returns tricks for the side **on lead**; convert to declarer tricks → contract result → score with care about whose perspective you're in. `calc_all_tables` has no such trap — it is indexed `table[Denom, Player]` and already gives *declarer* tricks.

## Performance & determinism (easy to get wrong)

DDS is ~95-99% of runtime; deal generation via `ExactDealSampler` is ~0.1-0.3s / 500 deals even under tight auction constraints (the legacy rejection sampler was up to 10x that). Don't try to parallelize the Python generator — optimize/seed it instead.

- **Two batch caps, two batch functions, both in `dds_runtime`.** `solve_all_boards` multithreads internally but its board array caps at `MAXNOOFBOARDS` (200); `calc_all_tables` caps at `MAXNOOFTABLES` (40). Passing more **raises**, which falls back to a single-board loop (~5x slower). Use `dds_runtime.solve_all()` / `dds_runtime.calc_tables()`; never call the endplay functions directly.
- **A DD table costs ~5x a lead solve** (~45-70 ms/deal on 4 threads vs ~14 ms; ~160 ms on a 2-core box) — that is why the contract tool defaults to 150 deals where the lead tool defaults to 300. `calc_tables(deals, exclude=[Denom...])` skips strains the user unchecked, worth roughly 20% each. **`endplay.dds.par` needs a complete table**, so `par_competitive_rate` is withheld (None) when strains were excluded — do not "fix" that by passing a partial table.
- **DDS thread cap:** `dds_runtime` calls `_dds.SetMaxThreads(min(cpu, 4))` at import. DDS otherwise grabs every core and allocates memory per thread — bad under concurrent public load. Override with env var `BRIDGE_DDS_THREADS` (`0` = auto-detect all cores); `docker-compose.yml` sets it per container.
- **libdds is not re-entrant.** Its multi-board functions (`SolveAllBoards*`, `CalcAllTables*`) share global state and must be entered by one caller at a time — but requests run concurrently in Starlette's threadpool, and there are now **two** endpoints solving. `dds_runtime.DDS_LOCK` is therefore process-global and both entry points take it; concurrent requests queue there (each still gets the full DDS thread allowance). A per-tool lock would protect nothing.
- **Docker gotcha:** endplay's bundled DDS `.so` links against the OpenMP runtime, so the backend image (`python:3.12-slim`) must `apt-get install libgomp1` — the one non-obvious container dependency.
- **Determinism:** `generate_deal(..., rng=)` takes a `random.Random` instance; both simulators build a private `random.Random(seed)` — reproducible and thread-safe. Each service calls its engine with `seed=0` behind an `app/common/cache.ResultCache` keyed on the canonical request, so identical inputs reuse the cached result (the contract the old `@st.cache_data` provided). The cache holds a lock with dogpile protection: simultaneous identical requests simulate once — the first thread computes, the rest wait on its `Event` (covered by `tests/test_service_concurrency.py`).

## Tests

- **Backend:** pytest in `backend/tests/` covers `engine/` (deal generation, scoring, simulator, shapes) and the API (`test_api.py`, via FastAPI `TestClient`). `backend/pytest.ini` sets `pythonpath = .` so tests import `engine` and `app` without an install. Run from `backend/`:
  ```
  .venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
  cd backend && ../.venv/Scripts/python.exe -m pytest
  ```
- **Frontend:** vitest covers the pure helpers in `src/lib/bridge.ts` and the contract ranking in `src/apps/contract/ranking.ts` (`npm run test`). React components are not unit-tested; verify the UI by running the app.
- **Browser:** the Playwright MCP server is how the React components actually get verified. It is configured per-machine in `.mcp.json`, which is **gitignored** — a fresh clone must create it: `{"mcpServers": {"playwright": {"command": "cmd", "args": ["/c", "npx", "-y", "@playwright/mcp@latest"]}}}` (drop the `cmd /c` wrapper off Windows) — run both dev servers (`:8000`, `:5173`) and drive the real UI. Useful beyond clicking: read the `/api/simulate` request body to confirm what the UI *sent*, and pull the response's `deals` matrix back to check a constraint truly bound. `.playwright-mcp/` is gitignored; screenshots default to the repo root, so clean them up.
- **Deployed / regression:** the project skill **`.claude/skills/test-deployed/SKILL.md`** tests a live site (prod by default, a local build via `run-apps`) against `checks/lead.md` and `checks/play.md` — one `## vX.Y` section per release of that product's `releases.ts`, each check pinning exact seed=0 numbers (share-link vectors in `vectors/*.json` for the lead app, the built-in example hands for play). `python scripts/regression.py coverage` fails when a release has no section, so **adding an entry to `releases.ts` means adding its checks in the same commit**; `… log` appends the run to `docs/testing/REGRESSION-LOG.md`.
- **The sampler's exactness tests are load-bearing.** `tests/test_suit_quality.py` pins `ExactDealSampler.total` against brute-force enumeration of a heavily-fixed position, and checks sampled frequencies against the exact per-outcome counts. A bug in the honor-class splitting or the spot-pool multinomial would not raise — it would silently skew every deal the app simulates, corrupting all lead rankings. Keep these tests if you touch the DP.

## Matchpoints vs IMPs

Both modes start from the same per-deal raw score (from the leader's/defense perspective; better = more) that `endplay` computes from tricks + vulnerability. They differ only in how candidate leads are **aggregated** across the simulated deals:

- **Matchpoints (MP):** frequency-based, comparing leads head-to-head per deal. For each simulated deal, rank each candidate lead's score against the other candidates; a lead scores a "matchpoint" for every alternative it beats (half for a tie). Report each lead's average MP% across deals. The size of a gain doesn't matter — only how often one lead beats another. Favors the lead that is best *most often*.
- **IMPs:** magnitude-based. Convert score differences to IMPs via the standard IMP scale, then average each lead's IMPs across deals (vs the per-deal datum = mean of all candidate leads). A single large swing (setting a game/slam) outweighs many small ones. Favors the lead with the best *expected* result, accepting more variance.

The scoring-mode toggle is **frontend-only** — it re-ranks the same `/api/simulate` response (both MP% and IMPs are always returned), it does not re-run the simulation. The **compare-leads feature is frontend-only the same way**: `CompareLeads.tsx` computes win/draw/lose + IMP swing / head-to-head MP% from the response's per-deal `deals` matrix via `compareLeads()`/`imps()` in `lib/bridge.ts` (the `imps()` threshold table is a port of `engine/scoring.py` — keep them identical).

### Contract calculator: ranked against a benchmark, not against the field

Contracts are **not** aggregated the way leads are. Head-to-head against all 20 candidates would make every number depend on which contracts happen to be in the list (adding 7NT would move everything), and at matchpoints it would reward a 30% grand slam for winning outright on the deals it comes home.

Instead both modes compare **pairwise against one benchmark contract** — the one you would otherwise be in — which is how bidding decisions are actually framed ("is 6♠ worth it over 4♠?"):

- **IMPs:** mean `imps(score_candidate − score_benchmark)` per deal. The benchmark reads 0.00.
- **MP:** `win% + ½·ties` against the benchmark. Above 50% means bid it.

The backend picks the default benchmark (**highest EV** — the best mean raw score over every candidate, which is the one candidate-set-independent number available, so the zero point does not drift as the candidate list changes) and the user can change it; `rankVsBenchmark()` in `lib/bridge.ts` recomputes instantly from the per-deal matrix, so neither the mode toggle nor the benchmark selector re-runs the simulation.

Because the ranking is expected-score-shaped, the table always carries the trust columns beside it — make %, mean tricks vs tricks needed, mean raw score (the only candidate-set-independent number), mean score when it fails — plus two flags: *play it from X* when the declarer choice is worth ≥ 0.3 tricks, and *thin edge* when a positive IMP edge (≥ 0.5) is concentrated in the best 15% of deals. Double-dummy flatters lie-dependent slams, so those numbers are the caveat the UI states rather than something to correct with a fudge factor.
