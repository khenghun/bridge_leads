# Bridge Simulator — Opening Lead & Optimal Contract

Two Monte-Carlo + double-dummy bridge tools, as tabs of one web app.

**Opening Lead Simulator.** Enter the leader's hand and the contract, optionally
constrain the three unseen hands, and the app generates consistent deals,
double-dummy solves every candidate lead, and ranks them by **Matchpoints** or
**IMPs**.

**Optimal Contract Calculator.** Enter *your own* hand and what the auction
told you about partner's (and the opponents') hands, and the app ranks the
contracts your side could be in — 3NT, 4♠, ♠ partscore … — each with its make
rate, mean tricks, and score against the contract you'd otherwise be in.

A third tab, **What's new**, carries the release notes.

Pure simulation — **no AI / LLM**.

A **FastAPI** backend + **React/Vite/TypeScript** frontend, containerised with
Docker. Current release **v2.1**; see [`ROADMAP.md`](ROADMAP.md) for the full
version history. (It began as a single Streamlit app.)

## Quick start (Docker)

Requires Docker. From the repo root:

```bash
docker compose up --build
```

Then open <http://localhost>. The frontend is served by nginx, which proxies
`/api` to the backend.

## Local development

### Backend (Python 3.10+)

```bash
python -m venv .venv
# Windows:
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
cd backend && ../.venv/Scripts/uvicorn app.main:app --reload
# macOS / Linux:
# .venv/bin/python -m pip install -r backend/requirements-dev.txt
# cd backend && ../.venv/bin/uvicorn app.main:app --reload
```

The API runs on <http://localhost:8000> (interactive docs at `/docs`).

### Frontend (Node 18+)

```bash
cd frontend
npm install
npm run dev
```

Vite serves the UI on <http://localhost:5173> and proxies `/api` to the backend
on `:8000`, so run both together in dev.

### Using the app

1. Set the **contract** (e.g. `3NT`), **declarer**, **penalty**, and **vulnerability** in the sidebar — or pick a **demo auction** to auto-fill them.
2. Pick the **scoring mode** (Matchpoints or IMPs) and the number of deals to simulate.
3. Enter the **opening leader's 13 cards** (the leader sits to declarer's left) — type per suit, paste a PBN hand, or hit 🎲 for a random hand.
4. Optionally add **constraints** on the three unseen hands to reflect the bidding: HCP range, suit lengths, an advanced disjunctive shape, one suit's **quality** (*good* = 2 of AKQ or 3 of AKQJT), and **specific cards** a hand is known to hold (type `AK` in the ♥ row to pin ♥A and ♥K — the rest of the hand is still simulated around them).
5. Click **Simulate** for a ranked table of leads plus sample deals each lead defeats.
6. The **Optimal Contract** tab asks the other question — where do your and partner's hands belong? — from your own hand and the same style of constraints.

## Tests

```bash
# Backend (engine + API)
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
cd backend && ../.venv/Scripts/python.exe -m pytest

# Frontend (pure helpers)
cd frontend && npm run test
```

## How it works

- `backend/engine/sampling.py` + `honor_sampler.py` — build random full deals consistent with the known cards and constraints.
- `backend/engine/lead/simulator.py` — for each candidate lead, double-dummy solves the generated deals and scores the outcome.
- `backend/engine/contract/simulator.py` — the second tool: one double-dummy table per deal, scoring every candidate contract at once.
- `backend/engine/scoring.py` — turns tricks into a duplicate-bridge score (via `endplay`) and aggregates leads as Matchpoints or IMPs.
- `backend/app/` — FastAPI HTTP layer (validation, caching, routes) over the engine.
- `frontend/src/` — React UI (hand entry, constraints, results, sample-deal diagrams).

The double-dummy solve is the bottleneck and runs multithreaded in ≤200-board
batches; results are cached per (hand, contract, constraints, deal-count) so
repeated queries are instant. Cap solver threads with the `BRIDGE_DDS_THREADS`
env var (defaults to `min(cpu_count, 4)`; `0` = use all cores).

### Matchpoints vs IMPs

Both start from the same per-deal score; they differ in aggregation:

- **Matchpoints** — frequency-based. Rewards the lead that is best *most often*, regardless of margin.
- **IMPs** — magnitude-based. Rewards the lead with the best *expected* result; a single big swing (setting a game/slam) outweighs many small ones.

The mode toggle is frontend-only — it re-ranks the same simulation result.

## Card notation

Cards use suit-then-rank with `T` for ten: `SA`, `HK`, `DT`, `C2`. Hands are
shown in PBN form `spades.hearts.diamonds.clubs`, suits high-to-low, e.g.
`AK8.Q95.J982.Q43`.
