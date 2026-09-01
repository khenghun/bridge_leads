# Roadmap — Play Solver

Version history and planned work for the play solver, the second product in
this repo. Releases are numbered **v1.0, v1.1, …** on the play solver's own
line — `frontend/src/apps/play/changelog/releases.ts` is the source of truth
(it is what the app's *What's new* panel shows) and this file follows it. The
lead/contract app has its own line in [`../lead/ROADMAP.md`](../lead/ROADMAP.md);
what the two share and why is in
[`../two-products-one-repo.md`](../two-products-one-repo.md).

## v1.0 — Replay and grade a hand ✅ (built 2026-08-27, deployed 2026-09-01)

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

## Planned — the order and why

Everything below grades from the same primitive: one Monte-Carlo grade of one
seat's decisions (`grade_play`). v1.1 composes it, v1.2 changes what it
samples, v1.3 changes how it prices, v1.4 and v1.5 drive it from new places.
The order is value-per-effort: v1.1 is a frontend composition of what exists,
v1.2 is the one deep engine feature and the thing no free tool does.

## v1.1 — Analyze a pair, or the whole table ⚪

Design: [`v1.1-pair-analysis-plan.md`](v1.1-pair-analysis-plan.md).

Replace the single-seat picker with three actions — **Analyze N/S**,
**Analyze E/W**, **Analyze the whole table**. A pair is always graded as a
pair: the declaring side is one grade of declarer (which already covers
dummy's cards); the defending side is one grade per defender. Whole table is
both. The frontend issues the per-seat requests **sequentially** and renders
each seat as it lands, so a three-seat analysis shows its first results at the
same time a single seat does today and the per-seat result cache still applies.
Results are grouped by pair with a pair summary (role, decisions graded,
mistakes, tricks lost) and, for the whole table, one ranked list of the
biggest swings across all seats — the "whose fault was it" view. Constraints
become **per seat, for all four seats** ("what the auction revealed about this
hand"), and each request carries the entries for the seats that request cannot
see; today's editor only knows the two seats hidden from one graded seat.

## v1.2 — Expert opponents ⚪

Design: [`v1.2-expert-opponents-plan.md`](v1.2-expert-opponents-plan.md).

A toggle that assumes the opponents play as well as possible **and lets their
earlier plays shape the deals that are sampled**. Today a sampled layout only
has to be consistent with which cards were played; under *Expert opponents*
it must also be a layout on which every earlier play by an opponent was a
best play **given what that opponent could see** — a defender who did not
give partner a ruff when, from their seat, the ruff was there to find is
taken not to hold that card on that layout. So the sample tightens the way a
good player's inference does, and the graded best card moves with it.

Judging "what they could see" is a **Monte-Carlo inside the Monte-Carlo**:
each earlier opponent decision is re-solved on an inner sample of the hands
hidden from *that* opponent, at a configurable fraction of the main deal
count (default half), with a tolerance for the inner noise. It is slow by
design — two orders of magnitude more solves before memoisation, which is the
load-bearing optimisation (an opponent's judgement depends only on their
holding at that point, and late holdings repeat) — so it defaults to fewer
deals, exposes the ratios, and reports how many layouts survived. Partner is
deliberately **not** judged: partner's cards are signals, not trick-maximising
plays (see *Partnership signalling* under Later).

## v1.3 — Cost in points and IMPs ⚪

Every decision's cost is a trick count today, so losing an overtrick in 3NT
and letting 4♠ make both read "−1". Price each option through
`engine/scoring.py` (contract, vulnerability, doubling) and show the swing in
points and IMPs beside the tricks; rank v1.1's biggest-swings list by IMPs.
Small, engine-ready, deliberately after v1.2 so both grading modes get it at
once.

## v1.4 — Trace the optimal line ⚪

From any position, play the best card for every seat a few tricks ahead
(depth ≤ 5) and step the table through the traced line — "here is what should
have happened next", not just "not that card". The source's
`trace_optimal_line` has the engine shape; it becomes a `/api/play/trace`
endpoint over repeated `grade_position` solves. Replaces the source's
*compare two lines*, which the expandable options table already covers.

## v1.5 — Play it from here ⚪

Interactive play from any position on the same table: click a card, the other
seats answer with their best play, undo, and see the trick count move. The
`/api/play/position` primitive already exists; this is the UI and the turn
loop around it.

## Later

- **BBO import by username** — a server-side fetch (`bridge_ai/bbo_hands.py`
  has the Python) with a BBO session token from the environment; needs a check
  of whether public hands work without one. Not a local-development item.
- **Partnership signalling — far out.** Declare the defenders' carding
  agreements (attitude and count, standard or UDCA; suit preference; lead
  conventions) and let *partner's* spot cards constrain the sample the way a
  real partner reads them — a low card under UDCA says "I like this", so
  layouts where partner holds nothing there become unlikely. Deliberately
  last: signals are conditional (attitude *or* count depending on the
  situation), falsecarded on purpose, and agreed differently by every
  partnership, so capturing them faithfully is a modelling problem, not a
  sampler flag. It is also the only route to judging partner's plays in
  *Expert opponents*, which v1.2 leaves out for exactly this reason.
- **A health-check step in `deploy-play`** — `curl` the domain's
  `/api/play/health` after `up -d`, so a green deploy means a serving site
  (2026-09-01 taught this: the stack was up four days behind a dark domain).
