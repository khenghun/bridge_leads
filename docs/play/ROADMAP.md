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
seat's decisions (`grade_play`). v1.1 composes it, v1.2 changes how it prices,
v1.3 changes what it samples, v1.4 says how sure it is, v1.5 moves the
slow part off the VPS, then drives it from new places. The
order is value-per-effort: v1.1 and v1.2 are small and land quickly; v1.3 is
the one deep engine feature and the thing no free tool does.

## v1.1 — Analyze a pair, or the whole table ✅ (built and deployed 2026-09-01)

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
see; because the real deal is known, the editor warns when a constraint rules
out the hand a player actually held, and blocks a pinned card they did not
hold. Built as planned — no backend change; `frontend/src/apps/play/analysis.ts`
holds the pure parts (23 vitest cases) and the UI was verified with Playwright
(request bodies carry exactly the per-view constraint slice; E/W on the example
reproduces v1.0's West result).

## v1.2 — Cost in points and IMPs, and more example hands ✅ (built and deployed 2026-09-01)

Every decision's cost is a trick count today, so losing an overtrick in 3NT
and letting 4♠ make both read "−1". Price each option through
`engine/scoring.py` (contract, vulnerability, doubling) and show the swing in
points and IMPs beside the tricks; rank v1.1's biggest-swings list by IMPs.
Small and engine-ready. Moved ahead of *Expert opponents* (2026-09-01) so the
swings list means something in points before the slow mode lands. Built: the
grader keeps each sampled deal's trick count per card and prices it through
`engine/scoring.py` (vulnerability and doubling now reach the engine from the
request), so every option carries a mean `score` and a per-deal-converted
`imps` against the trick-best card, every decision an `imp_diff` /
`score_diff`, and the summary a `total_imp_loss`. Ranking by tricks is
unchanged, but the badge is then **demoted by the IMP cost** (≥ 0.5 IMPs
given up caps it at *good*, ≥ 2 makes it *suboptimal*; the trick-best card
stays optimal) — the 7NT example's ♦Q, 0.05 tricks but a full IMP, was the
case that decided it. The UI adds an IMPs column to every table, points in
the tooltip, and the swings list and pair summaries rank by IMPs.

Alongside it, **more built-in example hands**: the upload screen offers a
short list instead of one board — real hands from the user's own BBO
sessions with the player names replaced by seats, chosen to cover different
stories (a grand slam played out to the last card, a 1NT partscore defended
to the end, a competitive 2♠ after a weak two, a 3NT from a teams practice)
so a first-time visitor can see the grader at work without a `.lin` of
their own.

## v1.3 — Expert opponents ✅ (built 2026-09-01, deployed 2026-09-03)

Design: [`v1.3-expert-opponents-plan.md`](v1.3-expert-opponents-plan.md).

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

Deployed 2026-09-03 together with the v1.4 performance steps 0–3 (DDS batch
aggregation, below), and verified on prod against the `test-deployed`
checklist — smoke plus the whole v1.3 section, strict included
(`docs/testing/REGRESSION-LOG.md`). Two things that surfaced: the header's
version line used to take the newest changelog entry whether or not it was
flagged unreleased (fixed in the release commit), and the expert seat line's
sampled count moved from 1371 to 1406 with the batching change — same
consistent count, identical grades — so the checks are re-pinned.

## v1.4 — How sure is that grade? ✅ (built and deployed 2026-09-08, closed 2026-09-09)

Design: [`v1.4-sample-size-plan.md`](v1.4-sample-size-plan.md) and
[`v1.4-performance-plan.md`](v1.4-performance-plan.md). Released 2026-09-08
and verified on prod the same day against the `test-deployed` checklist
(`docs/testing/REGRESSION-LOG.md`). Closed 2026-09-09: the two items that
were still open — the traced optimal line and guess-aware grading — moved
to v1.5 unchanged.

1. **Accuracy: a standard error on every grade, and ×3 deals where the
   grade is in doubt.** The seed spread the timing work exposed (at 100
   deals a big-swing decision's status flipped with the seed alone — c7 T9
   ♦6: −0.03 to −0.43 tricks over five seeds) is ordinary sampling noise,
   and the grader can quote a standard error for free. So every grade
   carries a ± and a *marginal* flag (its status is not firm within ±2σ),
   and a decision that does not read clearly optimal — or is marginal — is
   re-graded on **×3** deals (caps 600 plain / 300 expert), extending its
   sample from a per-decision stream so nothing else moves, with the expert
   filter's inner cap held at the base count so the verdict does not
   change. On by default in both modes, a checkbox turns it off. Plain runs
   cost the same; strict expert runs cost more on the decisions in doubt.
   A third trigger — the cheap unfiltered grade as a second opinion under
   expert opponents — was built, measured (every extension it caused ended
   firm optimal, at ~70 % of the added time) and **dropped** the same day.
   Truth stays truth: the closed room's T9 ♦6 reads −0.16 ± 0.08 tricks on
   300 deals and is still marked marginal, because its true cost sits
   between the two status lines.
2. **Faster local computation, same accuracy** (2026-09-03/04). Strict mode
   cost 60–105 s/decision; batch aggregation (2.2×), then memo-first
   priority ordering of the opponents' suspect plays and direct DDS struct
   building (a further 1.2–1.3×, bit-identical grades), exempting the
   opening lead from the filter (declarer seats 2.8–4.3×), carrying each
   seat's consistent pool forward between its decisions (declarer seats a
   further 1.2–1.5×) and drawing the inner sample lazily (~5 %) bring it to
   ~6 s per declarer decision and ~20–40 s per defender decision on a
   16-core laptop (board 7 rooms: 1 077 → 535 s and 1 569 → 814 s; board
   14's 2♥x room 384 s; strict benches re-baselined after the trigger drop
   at 801 / 817 / 496 s). Worker processes were **measured and rejected**:
   one process with 16 DDS threads already saturates the 8 physical cores,
   every multi-process split is equal or slower. DDS is now 97 % of the time
   and the judgement count is at its floor, so the rest is a faster solver
   or a different verdict — neither planned.
3. **A v1.3 accuracy bug found and fixed on the way:** a play from dummy
   was memoised on dummy's public cards instead of declarer's hidden hand,
   so one layout's verdict decided every layout; defenders' expert grades
   are now genuinely filtered (three board-7 open room defender calls moved
   from suboptimal to good/optimal).
4. **Benchmarks to test against** (added 2026-09-03). Board 7 of a real
   team match is pinned as the accuracy/timing benchmark:
   `docs/play/board7.lin` (both rooms, player names replaced by seats) plus
   `scripts/bench_play.py`, which grades a board one decision per request
   (the UI's pattern) and writes `docs/play/bench/*.{json,md}` pinning every
   grade, option list and timing; board 14 joined it for the strict run.
   seed=0 end to end — a fresh process reproduces the numbers exactly.
   Laptop reference: plain ≈ 0.17 s/decision (benchmark through
   `127.0.0.1`, never `localhost` — Windows' IPv6 fallback adds a flat ~2 s
   to every request).

Two rulings recorded for this work, still in force:

- **The opening lead is exempt from accuracy judgements.** Leads are the
  Opening Lead Simulator's problem and are made with dummy unseen; the play
  solver's defense grading must be accurate from trick 1, card 2 onward
  (so West's "suboptimal" ♥2 lead in the o7 benchmark is expected noise,
  not a target). **Extended 2026-09-04: the expert filter does not judge the
  lead either.** Measured, it was the filter's weakest inference at the
  highest price — a full-deal solve over three hidden hands, about half the
  cost of every declarer decision, rejecting one layout in twenty — so
  `opponent_decisions` skips index 0 (numbers in `v1.4-performance-plan.md`).
- **Sample size before strategy fusion.** The accuracy problem the timing
  work exposed was noise, not clairvoyance, so the ± band shipped first and
  guess-aware grading (below, v1.5) is judged against the band.

## v1.5 — Strict mode on the website, through AWS Lambda ⚪

Design: [`v1.5-lambda-strict-plan.md`](v1.5-lambda-strict-plan.md)
(architecture drafted 2026-09-09, decisions listed at its end; nothing built.
AWS account provisioning started 2026-09-10: quota, ECR repo, deploy and
execution roles exist — see the plan's *Provisioning progress* table).

**The headline.** Strict *Expert opponents* is unusable on prod: measured
2026-09-09, a declarer seat takes 593 s on the deployed app against 162 s on
the laptop (a whole table ≈ 50 min), because the `vhp-2c-4gb` VPS is one
physical core. Bigger boxes were priced and rejected — DDS's batch solver
flattens after four cores, so the 8-vCPU plan is the last step that pays
(≈ 3×) and it idles between a handful of sittings a week. Instead the
judgements are fanned out to **AWS Lambda**: the play API on the VPS keeps
every piece of state (the verdict memo, the carried pools, the result cache,
the query log) and sends each wave's memo misses to a worker Lambda in
groups, which runs today's `_judge_batch` on them and returns the verdicts —
bit-identical to the local ones by construction, since a verdict is a pure
function of its memo key. The default mode's double-dummy trace goes the
same way. Any group that fails is judged locally, so an outage is slow,
never wrong. Estimates before the spike: a strict seat from ~10 min to 2–4
min (about 1 min with 3 decisions in flight), a table from ~50 min to 4–15
min, at cents per table and $0 a month inside the free tier at today's
traffic; the VPS stays on its plan. Steps: a measurement spike, the judge
backend seam in the engine, the worker image (a target of the backend
Dockerfile, deployed by `deploy-play`), the client with fallback, bench and
gate against the laptop baselines, ship.

After it, in order, the three items v1.4 left open:

1. **Guess-aware grading** (moved from v1.4). **DD continuations are
   clairvoyant (strategy fusion):** a card that merely defers a guess can
   read "makes 100%" because each sampled layout is continued double-dummy.
   The board-7 benchmark's T7 options list shows it: ♦7 (a genuine
   guess-free squeeze) and ♣A both read make 1.00. The ladder to build:
   detect candidates whose DD-best continuation diverges across layouts at
   the same information set ("relies on a later guess"), then price flagged
   guesses by max-of-means at that node. Tested against the benchmark's T7
   ♣A-vs-♦7 case, and judged against v1.4's ± band — a change only counts
   if it moves a grade by more than its own noise.
2. **Trace the optimal line** (moved from v1.4). From any position, play
   the best card for every seat a few tricks ahead (depth ≤ 5) and step the
   table through the traced line — "here is what should have happened
   next", not just "not that card". The source's `trace_optimal_line` has
   the engine shape; it becomes a `/api/play/trace` endpoint over repeated
   `grade_position` solves. Replaces the source's *compare two lines*, which
   the expandable options table already covers.
3. **Play it from here.** Interactive play from any position on the same
   table: click a card, the other seats answer with their best play, undo,
   and see the trick count move. The `/api/play/position` primitive already
   exists; this is the UI and the turn loop around it. Also the natural
   home for a per-decision manual re-grade button, which v1.4's ± band
   makes the case for.

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
