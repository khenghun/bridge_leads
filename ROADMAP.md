# Roadmap

Version history and planned work for the Opening Lead Simulator.

> **Session handoff:** the latest work-in-progress state (what changed, what's
> uncommitted, and the agreed next steps) is documented in
> [`latest_updates.md`](latest_updates.md).

## v1 — Opening lead Monte-Carlo simulator ✅

The initial Streamlit app.

- Monte-Carlo deal generation with the leader's hand fixed and the three unseen
  hands constrained.
- Double-dummy solve of every candidate lead via `endplay`.
- Ranking of leads by **Matchpoints** or **IMPs**.
- Hand entry, contract / declarer / vulnerability inputs, and a constraint
  editor in the UI.

## v2 — UI polish, backend tests, and DDS performance fixes ✅

- **UI:** contract as a text box (e.g. `3NT`) + vulnerability checkbox; compact
  4-line hand entry; constraint panels ordered declarer / dummy / partner;
  four-colour suit scheme; results sorted by declarer tricks with recommended
  lead(s) highlighted and ties shown together; dark theme by default with a
  light-mode toggle; deals slider 100–1000 (default 500).
- **Performance:** DDS solved in ≤200-board batches to stay on the multithreaded
  path; thread cap at `min(cpu, 4)` via `BRIDGE_DDS_THREADS`; seeded /
  thread-safe deal generation with `st.cache_data` reuse.
- **Tests:** 57 backend regression tests across the deal generator, scoring, and
  lead simulator; `pytest.ini` and `requirements-dev.txt` added.

## v3 — Flexible constraints, auction demo, and sample deals 🚧

Detailed design: [`docs/v3-plan.md`](docs/v3-plan.md).

### 1. More flexible hand constraints ✅

Disjunctive shape constraints expressed in text — some set of **(A or B or C)**,
where each term ANDs per-suit length bounds and terms are joined by `or`; HCP
stays a plain range. Implemented as an envelope + predicate (rejection) in the
deal generator so shapes appear at their natural frequency. New modules
`engine/shapes.py` and `engine/shape_parser.py`; `generate_deal` gained an
`acceptors=` hook; `app.py` has a per-seat "Shape (advanced)" box. *Done.*
See `docs/v3-plan.md` §1.

### 2. Basic auction demo (1NT–3NT) with predefined constraints ✅

A registry of named auctions (`engine/auctions.py`), each mapping to a contract +
predefined constraint set (built on feature 1's shapes). A "Demo → Sample
auction" selector in `app.py` auto-fills the contract, declarer, and constraints
via an `on_change` callback so the user just enters the leader's hand and hits
Simulate. Presets: **1NT(S)–3NT(N)** and **2NT(S)–3NT(N)** (same shapes, HCP
20–21 / 4–10). *Done — verified end to end.* See `docs/v3-plan.md` §2.

### 3. Sample dealt hands showcasing the lead engine ✅

After a simulation, a "Sample deals" section shows up to **10 example deals**
(fewer if there aren't that many) in which the selected lead *defeats* the
contract — full 4-hand cross diagrams with the contract result. The engine
(`simulate_opening_lead`) returns these via a `samples` field, capped at
`max_samples` (10) per lead. *Done — verified end to end.* (Lead selection is
interactive — see feature 5.)

### 4. Faster leader-hand entry ✅

Two shortcuts for filling the leader's hand, alongside per-suit typing: a
**🎲 Random hand** button (`randomize_leader_hand`) and a **"…or paste PBN"** box
that parses `spades.hearts.diamonds.clubs` (e.g. `T.KT932.Q2.T9843`, `10`→`T`)
into the four boxes via an `on_change` callback, with inline validation.
*Done — verified.* See `docs/v3-plan.md` §4.

### 5. Sample-deal interactivity ✅

The "Sample deals" lead follows the **recommended lead for the active scoring
mode** (toggling Matchpoints ↔ IMPs re-points the samples), and the dropdown is
replaced by clickable, suit-labelled **lead chips** (recommended marked ★,
selected highlighted `primary`). Clicks persist across reruns and stick until the
next mode flip / run. *Done — verified.* See `docs/v3-plan.md` §5.

## v4 — Architecture migration: FastAPI + React/Vite + Docker 🚧

Detailed design: [`docs/v4-plan.md`](docs/v4-plan.md).

Retire Streamlit and split into a proper client/server app, keeping the
simulation `engine/` **unchanged**:

- **Backend** — a **FastAPI** service (`backend/app/`) wrapping
  `engine.simulate_opening_lead`, plus the parsing / validation / caching glue
  that used to live in `app.py`. Endpoints: `/api/health`, `/api/auctions`,
  `/api/validate/shape`, `/api/simulate` (a sync handler, so Starlette runs the
  blocking DDS solve in a threadpool). Determinism preserved via `seed=0` behind
  an in-process LRU+TTL cache (replacing `@st.cache_data`). Engine + API covered
  by pytest.
- **Frontend** — **React + Vite + TypeScript** (`frontend/`) re-implementing the
  Streamlit UI at full parity: demo-auction auto-fill, contract/scoring/sim
  controls, hand entry (per-suit / PBN paste / random), constraints editor with
  live shape validation, ranked results table, and clickable sample-deal cross
  diagrams. Pure helpers ported to `src/lib/bridge.ts` (vitest-covered).
- **Docker** — a Python API image (`python:3.12-slim` + `libgomp1` for the DDS
  OpenMP runtime) and an nginx-served static frontend image (multi-stage Node
  build), wired together by `docker-compose.yml`; nginx proxies `/api` to the
  backend (same-origin, no CORS in prod).
- **Cut** — `app.py`, `.streamlit/`, and the `streamlit` dependency removed;
  `engine/` + `tests/` moved under `backend/`.

## v5 — Production deployment: Vultr VPS + Caddy + GHCR CI/CD ✅

Detailed design: [`docs/v5-deploy-plan.md`](docs/v5-deploy-plan.md).

Stand the **unchanged** v4 container stack up on a public host with automatic
TLS and a push-button deploy. **No application code changes** — only new infra
files and a one-time VPS provisioning procedure.

**Live at <https://bridge-leads.icycookie.xyz>** (deployed 2026-07-06).

- **Host** — a **Vultr High Performance (`vhp-2c-4gb`) VPS** (2 vCPU / 4 GB;
  DDS is CPU- and single-thread-sensitive) running Docker + the compose plugin.
- **Edge / TLS** — a **Caddy** container terminates HTTPS with auto-issued /
  renewed Let's Encrypt certs and routes `/api/*` → `backend`, everything else →
  the static `frontend`. Only Caddy publishes 80/443; the app services stay on
  the internal network.
- **Registry** — CI builds both images and pushes them to **GitHub Container
  Registry** (`ghcr.io`); the VPS only **pulls**, never compiles.
- **CI/CD** — a GitHub Actions workflow: **build+push on every `main` commit**,
  with a **manual (`workflow_dispatch`) deploy** job that SSHes to the VPS and
  runs `docker compose -f docker-compose.prod.yml pull && up -d`. SHA image tags
  give one-step rollback.
- **Cut-in files** (written) — `docker-compose.prod.yml` (image refs, Caddy, no
  public app ports), `Caddyfile`, `.github/workflows/deploy.yml`, and a VPS
  provisioning checklist ([`deploy/provision.md`](deploy/provision.md): `deploy`
  user, `ufw`/`fail2ban`, Docker, GHCR access).
- **Deployed & verified (2026-07-06)** — VPS provisioned per the checklist
  (deploy user, hardened sshd, `ufw`/`fail2ban`, Docker); GHCR images public
  (anonymous pull, no registry login on the box); domain `icycookie.xyz`
  (Porkbun) with the app on the **`bridge-leads` subdomain** via `DOMAIN` in
  the VPS `.env`. Verified end to end: Let's Encrypt cert issued, `/api/health`
  ok, a real simulation solved over the public API, stack self-restarts after
  reboot (~55 s), and a green `workflow_dispatch` CI deploy.

## v6 — Engine robustness & performance: exact dealing 🚧

Work log / handoff: [`latest_updates.md`](latest_updates.md).

- **Infeasible-constraint handling ✅** — HCP constraint sets that can't sum
  to the deck's 40 HCP now return a clear 422 ("No way to meet the HCP
  constraints…") instead of hanging the solver; static per-suit
  infeasibility pre-checks in the deal generator.
- **Exact deal sampling ✅** — new `engine/honor_sampler.py`
  (`ExactDealSampler`): exactly-uniform deals under HCP constraints via an
  integer-count DP over honor value classes; shapes by rejection; legacy
  steered sampler kept as fallback. Generation up to 24.7× faster on tight
  HCP presets and now distribution-correct (verified vs shuffle-and-reject
  ground truth at N=20k).
- **Deployed 2026-07-16** — the two items above are live in production
  (pushed to `main`, images built by CI, manual `workflow_dispatch` deploy,
  verified on the live site).
- **Concurrency hardening ✅** (2026-07-16) — libdds's multi-board functions
  are not re-entrant, so `_solve_all()` now serializes the DDS solve behind a
  global lock (concurrent requests queue; each solve keeps its full thread
  allowance). The service result cache gained a lock + dogpile protection:
  simultaneous identical requests simulate once and share the result. Covered
  by `backend/tests/test_service_concurrency.py`.
- **UI polish ✅** (2026-07-16) — results table sorts by the active scoring
  metric, best first (MP% desc in Matchpoints, IMPs desc in IMPs mode);
  Defeat %/MP%/IMPs columns show one more decimal (1/2/3 dp); the sample-deal
  ★ marks *all* leads tied for best (matching the banner's "(n tied)" count);
  default deal count is now 300.
- **Native libdds build ⏳** — compile DDS with `-O3 -march=x86-64-v3` in the
  backend image to replace endplay's generic bundled `.so` (expected 10–25%;
  DDS is ~95%+ of runtime). Not started.
