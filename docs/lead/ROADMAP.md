# Roadmap — Opening Lead Simulator & Optimal Contract Calculator

Version history and planned work for the lead/contract app. The play
solver has its own line in [`../play/ROADMAP.md`](../play/ROADMAP.md);
the repo-level story is [`../two-products-one-repo.md`](../two-products-one-repo.md).

Releases are numbered **v1.0, v1.1, … v2.2** — the same numbers the app's
**What's new** tab shows players. `frontend/src/apps/changelog/releases.ts` is
the source of truth for them; this file follows it and adds the engineering
detail.

> **Session handoff:** the latest work-in-progress state (what changed, what's
> uncommitted, and the agreed next steps) is kept in `latest_updates.md` — a
> **local, gitignored** scratch file, so it will not be in a fresh clone.
> Anything worth keeping belongs in this file instead.

## v1.0 — Opening Lead Simulator ✅ (released 2026-07-16)

Everything up to 2026-07-16 shipped as the first release. It was built in six
development milestones, kept below as the engineering record. (The plan docs
under `docs/` were once named after the milestones; they now carry the public
version numbers, so three of them share the `v1.0` prefix.)

### Milestone 1 — Opening lead Monte-Carlo simulator ✅

The initial Streamlit app.

- Monte-Carlo deal generation with the leader's hand fixed and the three unseen
  hands constrained.
- Double-dummy solve of every candidate lead via `endplay`.
- Ranking of leads by **Matchpoints** or **IMPs**.
- Hand entry, contract / declarer / vulnerability inputs, and a constraint
  editor in the UI.

### Milestone 2 — UI polish, backend tests, and DDS performance fixes ✅

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

### Milestone 3 — Flexible constraints, auction demo, and sample deals ✅

Detailed design: [`v1.0-constraints-plan.md`](v1.0-constraints-plan.md).

#### 1. More flexible hand constraints ✅

Disjunctive shape constraints expressed in text — some set of **(A or B or C)**,
where each term ANDs per-suit length bounds and terms are joined by `or`; HCP
stays a plain range. Implemented as an envelope + predicate (rejection) in the
deal generator so shapes appear at their natural frequency. New modules
`engine/shapes.py` and `engine/shape_parser.py`; `generate_deal` gained an
`acceptors=` hook; `app.py` has a per-seat "Shape (advanced)" box. *Done.*
See `v1.0-constraints-plan.md` §1.

#### 2. Basic auction demo (1NT–3NT) with predefined constraints ✅

A registry of named auctions (`engine/auctions.py`), each mapping to a contract +
predefined constraint set (built on feature 1's shapes). A "Demo → Sample
auction" selector in `app.py` auto-fills the contract, declarer, and constraints
via an `on_change` callback so the user just enters the leader's hand and hits
Simulate. Presets: **1NT(S)–3NT(N)** and **2NT(S)–3NT(N)** (same shapes, HCP
20–21 / 4–10). *Done — verified end to end.* See `v1.0-constraints-plan.md` §2.

#### 3. Sample dealt hands showcasing the lead engine ✅

After a simulation, a "Sample deals" section shows up to **10 example deals**
(fewer if there aren't that many) in which the selected lead *defeats* the
contract — full 4-hand cross diagrams with the contract result. The engine
(`simulate_opening_lead`) returns these via a `samples` field, capped at
`max_samples` (10) per lead. *Done — verified end to end.* (Lead selection is
interactive — see feature 5.)

#### 4. Faster leader-hand entry ✅

Two shortcuts for filling the leader's hand, alongside per-suit typing: a
**🎲 Random hand** button (`randomize_leader_hand`) and a **"…or paste PBN"** box
that parses `spades.hearts.diamonds.clubs` (e.g. `T.KT932.Q2.T9843`, `10`→`T`)
into the four boxes via an `on_change` callback, with inline validation.
*Done — verified.* See `v1.0-constraints-plan.md` §4.

#### 5. Sample-deal interactivity ✅

The "Sample deals" lead follows the **recommended lead for the active scoring
mode** (toggling Matchpoints ↔ IMPs re-points the samples), and the dropdown is
replaced by clickable, suit-labelled **lead chips** (recommended marked ★,
selected highlighted `primary`). Clicks persist across reruns and stick until the
next mode flip / run. *Done — verified.* See `v1.0-constraints-plan.md` §5.

### Milestone 4 — Architecture migration: FastAPI + React/Vite + Docker ✅

Detailed design: [`v1.0-webapp-plan.md`](v1.0-webapp-plan.md).

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

### Milestone 5 — Production deployment: Vultr VPS + Caddy + GHCR CI/CD ✅

Detailed design: [`v1.0-deploy-plan.md`](v1.0-deploy-plan.md).

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

### Milestone 6 — Engine robustness & performance: exact dealing ✅

Work log / handoff: `latest_updates.md`.

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
  DDS is ~95%+ of runtime). **Attempted 2026-07-29, no measurable gain,
  dropped.**

## v1.1 — Compare two opening leads ✅ (2026-07-25)

`/api/simulate` gained a compact per-deal `deals` matrix (cards + layout /
tricks / scores per record, index-aligned) built from what the engine already
computed, and the frontend turned it into a **CompareLeads** section: pick two
leads, see win/draw/lose with the average IMP swing or head-to-head MP%, and
filter the sample deals by outcome. Pure client-side over the one cached
response, like the MP/IMP toggle. Cache shrunk 256 -> 64 entries (they now carry
the matrix) and nginx gzips JSON.

## v1.2 — Suit quality constraint ✅ (2026-08-03)

One table-wide `(seat, suit, level)` constraint on the unseen hands: **good** =
2 of AKQ or 3 of AKQJT (what a preempt or overcall promises), **poor** =
anything worse. Exactly one per simulation, modelling the single player who
described a suit in the auction — that ceiling is what keeps the sampler's DP
small.

Enforced **inside** the DP rather than by rejection, so quality honours are
dealt in the same pass that satisfies HCP: the draw stays exactly uniform, the
two constraints prune each other, and `.total` counts HCP- *and*
quality-consistent deals, giving exact feasibility instead of a silent empty
result. It also made things faster — adding "good hearts" to a weak-two auction
went 2.897s -> 0.332s per 500 deals, because conditioning on a good suit raises
P(6 cards) and length rejection was the bottleneck.

## v2.0 — Optimal Contract Calculator ✅ (2026-08-03)

Detailed design: [`v2.0-contract-plan.md`](v2.0-contract-plan.md).
Work log / handoff: `latest_updates.md`.

The mirror image of the lead simulator: enter **your own** hand plus what the
auction told you about partner's (and the opponents') hands, and rank the
**contracts your side could be in**.

- **Shared core, per-tool packages ✅** — `engine/dds_runtime.py` (thread cap,
  the one process-global DDS lock, both batch entry points) and
  `engine/sampling.py` (constraint building + deal generation, parameterised by
  *own seat*) were extracted from the lead simulator, which moved to
  `engine/lead/`. Same split in the HTTP layer (`app/common`, `app/lead`,
  `app/contract`) and the frontend (`components/` shared, `apps/lead`,
  `apps/contract`). Lead endpoints and behaviour unchanged.
- **Contract engine ✅** — `engine/contract/`: one double-dummy **table** per
  deal (`calc_all_tables`, ~5× a lead solve) prices every contract at once, so
  the candidate space is free and deal count is the only cost driver. The
  candidate set is **20**, not 70: undoubled, every partscore level in a strain
  scores the same for a given trick count and the lowest never scores less, so
  per strain the decisions are `partscore | game | 6 | 7`. Both declarers are
  evaluated; the better one is shown with a "play it from X" flag.
- **Ranked against a benchmark ✅** — both scoring modes compare pairwise
  against the contract you would otherwise be in (default: the highest-EV
  candidate by mean score, user-changeable), which is how bidding decisions are
  framed and what stops a 30% grand slam from looking good at matchpoints.
  Reported beside it: make %, mean tricks, mean score, mean score when it fails,
  and flags for a declarer-dependent contract or a thin (tail-driven) edge.
  Ranking is frontend-only over the per-deal matrix, so mode and benchmark
  changes are instant.
- **Free opponent context ✅** — the same DD tables give *opponents make a game
  on X%* and *par is theirs or a save on Y%* (via `endplay.dds.par`), the flag
  that a constructive ranking is standing on a competitive deal.
- **UI ✅** — new tab (hash-routed, both tabs stay mounted): ranked table with
  benchmark selector, strain × decision-level heatmap, compare-two-contracts
  (win/draw/lose + IMP swing, same pattern as compare-leads), and sample deals
  split into makes/fails. Sidebar: seat, we/they vulnerable, deals (50–500,
  default 150) with a time estimate, and per-strain checkboxes that skip strains
  in the DDS solve.
- **Not in v2.0, deliberately** — the opponents never compete or double (their
  best contract is reported, not bid), and trick counts stay pure double-dummy
  with the caveat stated rather than corrected by a fudge factor. Candidates
  for a later release: a "they compete to X" toggle, auto-doubling large sets,
  and a realistic (single-dummy) opening lead before solving.

## v2.1 — Specific cards, and a changelog tab ✅ (2026-08-04)

Work log: `latest_updates.md`.

Named cards pinned into an unseen hand ("partner holds ♥AK") — the one thing
the HCP / length / shape / quality vocabulary cannot express. The engine had
supported `fixed_cards` since before the tool split but nothing could reach it;
this exposed it end to end, in **both** tools.

- **Composes rather than layers ✅** — pinned cards are merged into
  `known_hands`, so they are *dealt*, not tested: the HCP bounds count them and
  `ExactDealSampler`'s quality DP seeds its base counts from them. A
  contradictory set (`♥AK` + `poor` hearts) is reported infeasible instead of
  sampling forever.
- **Validation split by what each layer knows ✅** — card syntax and
  claimed-twice in `app/common/constraints.build_fixed_cards`; own-seat and
  own-hand collisions in `engine.sampling.resolve_fixed_cards` (they need the
  hand, and keeping them in the engine leaves it safe to call directly); a new
  `check_length_feasibility` catches pinned cards that cannot fit the seat's
  suit bounds, which would otherwise reject every draw and surface as "no deals
  could be generated".
- **UI ✅** — a collapsible *Specific cards* box per seat with four per-suit
  rank inputs (`AK` in the ♥ row), a count on the button so a collapsed box
  cannot hide a live constraint, and `fixedCardIssues` mirroring every rule
  client-side so the matching 422 is a backstop, not the normal path.
- **Also fixed ✅** — `.constraint-grid` was `repeat(3, 1fr)`, so an expanded
  box widened its own column and squeezed the other two seats' inputs into
  unreadable slivers (the shape box already did this).

### Mobile UI pass ✅

Reviewed at 390×844 against the real app. The two real bugs were both flexbox
axis confusion in the 780px media query, and both only bit once `.layout` went
`flex-direction: column`:

- `.sidebar` kept `flex: 0 0 300px`, and in a column that basis is the **height**
  — so every control sat in a 300px inner scroller with a second scrollbar
  nobody notices (the deal slider and the strain chips were unreachable).
  `flex: none` fixes it.
- `.layout`'s `align-items: flex-start` (there to stop the sticky sidebar
  stretching in *row* mode) becomes the **horizontal** axis in a column, so
  `.content` shrink-wrapped to its widest child. A wide results table then
  inflated the whole page sideways instead of scrolling in its own wrapper —
  dragging the constraint panels and the sticky button off-screen with it.
  `align-items: stretch` in the media query fixes it, and is what makes
  `.content { min-width: 0 }` + `.table-scroll` work at all.

Also: `font-size: 16px` on mobile inputs (Safari zooms the page below that, and
the constraints editor has ~27 of them); a sticky bottom `.btn-primary`, since
the stacked sidebar otherwise pushed Simulate ~2000px down; 40px minimum tap
targets; `inputMode="numeric"` on every number field and
`autoCapitalize`/`autoCorrect` off on every card field; a scrolling tab strip;
and the column/flag explanations written out as text, since they lived only in
`title` tooltips that touch devices cannot reach.

### Query logging ✅

`app/common/querylog.py`: one SQLite row per simulation — timestamp, tool,
request body, nothing else. Off unless `BRIDGE_QUERY_LOG` names a file, so only
production writes; the prod compose file points it at a bind-mounted
`/opt/bridge_leads/data/queries.db` (bind, not a named volume, so it survives
image pulls and can be read with the host's `sqlite3`). Deliberately not
user-facing, so no changelog entry. Reading it: see the routine-operations table
in [`deploy/provision.md`](deploy/provision.md).

### Changelog tab ✅

Shipped in the same release: a third tab, **What's new** — user-facing
release notes, newest first, in `frontend/src/apps/changelog/`. `releases.ts` is the data (version, date,
title, New/Improved/Fixed entries) and is the source of truth for the **public**
version numbers this file now follows. It is static content, so it costs nothing
to keep mounted beside the two tools. Add an entry there whenever a release
changes something a player would notice — and keep it free of module names and
test counts, which belong here.

## v2.2 — Results worth sharing ✅ (built 2026-08-12, deployed 2026-08-27)

Detailed design: [`v2.2-share-plan.md`](v2.2-share-plan.md).
Work log: `latest_updates.md`.

Five presentation features taken from a review of the commercial competitor
<https://bridgesolver.com/> (whose flagship is shareable saved results), plus
three drawn from week-one production query-log usage patterns — all
frontend-only as designed; the backend, API, and engine did not change:

1. **Share links ✅** — the frozen request + view state (`lib/share.ts`:
   versioned JSON, empties stripped, base64url) in the URL hash
   (`#lead?s=…`, ~250 chars); opening a link restores the form and
   auto-runs (`seed=0` determinism + the result cache make recomputation a
   substitute for server-side storage and accounts). Decode is fully
   defensive — garbage, wrong versions, missing fields → a dismissible
   banner over the plain app; out-of-range deal counts clamp. 🔗 Copy link
   sits on both conclusion cards and builds the URL at click time.
2. **Conclusion card ✅** — results open with the answer: recommended
   lead / contract (both framings: "Bid 3NT instead of 4♥" and "Stay in
   4♥"), metric, defeat/make rate, and the margin over the next-best
   distinct candidate.
3. **Scenario recap ✅** — context + per-seat constraint chips
   (`ScenarioRecap` + `describeSeatConstraints`), rendered from the request
   frozen at simulate time, never the live form.
4. **Equivalent-lead grouping ✅** — same-suit cards with identical per-deal
   trick vectors collapse into one row/chip (♦T9) across the results table,
   sample deals, and compare pickers; the recommendation banner's tie count
   now counts distinct groups. (bridgesolver's own example page shows this
   done wrong — two rows with identical numbers; ours groups from data.)
5. **Deal filter (browse-only) ✅** — one criterion row (seat, HCP window,
   optional suit-length window, include/exclude) over the browsable deals in
   all four browsing surfaces, composing with the outcome buckets; every
   live filter shows "N of M, rankings stay full-run". Prerequisite landed
   too: the lead tool's sample deals now render from the full
   `deals.records` matrix instead of the server-capped `samples` field
   (which stays in the API, unused).
6. **"Too close to call" ✅** — paired per-deal metric differences
   (replicating the backend aggregation exactly, so margin = difference of
   the displayed columns) give the margin a `±sd/√n`; within 2·SEM the card
   says "too close to call" and offers a one-click re-run at the deal cap
   using the frozen request.
7. **Session run history ✅** — last 10 runs per tool in memory as chips
   (time · setup · answer); clicking restores result + frozen request +
   form together, so recap/share/re-run stay consistent. Identical re-runs
   replace their entry. Deliberately not persisted.
8. **Restore last setup ✅** — the share payload written to localStorage
   (one slot per tool, best-effort) on every simulate; an explicit
   "↩ Restore last setup" offer on load fills the form without running.
   Suppressed when a share link brings its own setup.

Deliberately not taken: their 10k–50k-deal paid tier (accounts + job queue on
2-core hardware, no demand), and re-ranking on a deal filter.

Frontend tests grew 30 → 60 (grouping, paired-SEM and metric-diff helpers,
constraint/criterion describers, share codec round-trip + rejection cases,
localStorage slots); every feature was also driven in the real app via
Playwright, including a share-link round trip and a malformed link.
