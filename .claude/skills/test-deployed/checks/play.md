# Play solver — regression checks

Site: https://bridge-play.icycookie.xyz (local: http://localhost:5174/play.html).
One section per release of `frontend/src/apps/play/changelog/releases.ts`,
oldest first; IDs are `P-<version>-<n>`. Tags: `[smoke]` always, `[full]` on
the release under test or after an engine change. Every check uses the
built-in example hands (`frontend/src/apps/play/examples.ts`) at the default
**40 deals per decision, single dummy** (v1.3 doubled every deal count: the
default was 20 through v1.2), so the numbers are reproducible.

Pinned values: all re-pinned locally at the v1.3 build (2026-09-01) at 40
deals; the same figures the `run-apps` skill expects. (The v1.2 prod pins at
20 deals were 12/2/1 · 0.70 · 1.00 IMPs for Board 17 West and ♦Q −1.00 IMPs
/ −0.05 tricks for the 7NT hand — superseded.)

## v1.0 — Replay a hand and grade every card

- **P-1.0-1 [smoke] API and shell.** `curl /api/play/health` →
  `{"status":"ok"}`. Fresh load: title `Bridge Play Solver`, header link
  `Opening lead & optimal contract →` to the lead site, a `What's new ·
  vX.Y` button whose version is the newest non-`unreleased` entry of
  `releases.ts`, a *Light mode* switch, the drop zone (`Drop a .lin file
  here`), the paste box with **Load this hand disabled** while empty, and
  the privacy line `The file is parsed in your browser … never the player
  names`. Console: 0 errors, 0 warnings.
- **P-1.0-2 [smoke] Grade one seat.** Click **Board 17 · 1NT by West** →
  the table shows the deal, contract 1NT by West, a `… cards played`
  counter, and *Analyze* offers three actions. Pick **E/W** (declaring 1NT —
  one grade, of West) → *Analyze*. One `POST /api/play/analyze` → 200 in
  ~1 s with `seat: "W"`, `method: "single_dummy"`, `num_deals: 40`. Under
  the **West** section, pinned: **13 ✓ / 2 ~ / 0 ✗ of 15 graded, 3
  forced**; `Tricks given up: 0.44` · **0.69 IMPs (23 points)** — since
  v1.4 the four doubtful decisions are re-graded on 120 deals and the seat
  line adds `· 4 marginal` and `(×3 when in doubt)`; the v1.0–v1.3 build
  read 0.45 · 0.82 IMPs (27 points), and still does with *Spend more deals
  on doubtful grades* unticked.
- **P-1.0-3 [full] Step through the play.** With the hand loaded, press
  `ArrowRight` → the played-card counter advances by one and that card is
  struck through in its hand; `Shift+ArrowRight` advances a whole trick and
  the four cards of the finished trick are laid on the table with the winner
  marked; `ArrowLeft` / `Shift+ArrowLeft` go back; the buttons do the same
  as the keys.
- **P-1.0-4 [full] Every decision expands.** In the West table click a graded
  row: an options list opens with **every legal card** at that moment,
  ranked, each with its tricks (the row's `Act`/`Best` columns agree with
  it); the viewer jumps to that trick (counter and table change). A
  *forced* row (one legal card) has no grade and nothing to expand.
- **P-1.0-5 [full] Paste path.** Fresh load, paste the LIN text of Board 17
  (the `lin` field of the first entry in `examples.ts`) into the box: *Load
  this hand* enables; loading gives the same deal and contract as P-1.0-2,
  and the seat labels read N/E/S/W, never the file's player names.
- **P-1.0-6 [full] Bad input is a message.** Paste `garbage|` → an error
  under the box, nothing loads, **no request**. Paste a LIN whose play
  revokes (edit one `pc|` to a card from the wrong hand) → Analyze returns
  422 naming the offending play index and the UI shows that text.
- **P-1.0-7 [full] Double dummy and constraints.** Method *Double dummy* +
  E/W → Analyze: one request with `method: "double_dummy"`, a result whose
  numbers differ from P-1.0-2 (hindsight grades, typically fewer ✓). Set
  North's ♠ length min to 5 and type `(5s)` into North's *Advanced shape*:
  `POST /api/validate/shape` → 200 (proves the play API serves it too); the
  next analyze request carries `constraints` for North.

## v1.1 — Analyze a pair, or the whole table

- **P-1.1-1 [smoke] Whole table, three grades.** Board 17 → **Whole table
  (3 grades)** → Analyze. **Three** sequential `POST /api/play/analyze`
  (seats W, then N, then S), sections appearing one by one. Pinned:
  *Biggest swings* on top, `Ranked by IMPs`, first rows
  `1 N ♠9 −0.69 IMPs / −0.46 tricks · ✗ suboptimal ?`, `7 W ♥4 −0.42 /
  −0.15 · ~ good ?`, `8 S ♣3 −0.35 / −0.17 · ~ good`, `6 N ♠8 −0.34 /
  −0.38 · ✗ suboptimal ?`; pair lines `E/W … tricks given up 0.44 · 0.69
  IMPs` and `N/S … 12✓ 2~ 2✗ of 16 graded · 3 marginal · defensive tricks
  given up 1.19 · 1.76 IMPs` (v1.4 numbers, every swing row re-graded on
  120 deals; before v1.4: `1 N ♠9 −0.55 / −0.50`, `7 W ♥4 −0.50 / −0.20`,
  `8 S ♣3 −0.40 / −0.20`, `4 N ♦5 −0.40 / −0.17`, E/W 0.45 · 0.82, N/S
  1.32 · 1.83). The explanatory line says dummy (East) makes no decisions.
- **P-1.1-2 [full] N/S alone.** Board 17 → **N/S** → Analyze: exactly two
  requests (N, S), no West section, the N/S pair summary equals the one in
  P-1.1-1.
- **P-1.1-3 [full] Constraints are per hand and sliced per view.** Set
  North HCP min 8 and West HCP max 12, run *Whole table*, read the three
  request bodies: W's carries only `hcp.N`, N's only `hcp.W`, S's both. Set
  West HCP min 12 (West holds fewer) → an amber *rules out the hand actually
  held* note, Analyze still enabled. Pin ♥A on North (♥A is elsewhere) →
  Analyze **disabled**, no request.
- **P-1.1-4 [full] Swing rows navigate.** Click the `8 S ♣3` swing row: the
  viewer jumps to trick 8, the South table highlights that row and its
  options list opens with *Score* and *IMPs* columns.
- **P-1.1-5 [full] The felt follows the theme.** Default (dark) table has the
  dark felt (`--felt-*` tokens); toggling *Light mode* changes the table's
  background to the light felt and back.

## v1.2 — What it cost in IMPs, and more example hands

- **P-1.2-1 [smoke] Six examples.** The upload screen lists, in order:
  `Board 17 · 1NT by West`, `Board 6 · 7NT by East, played to the last card`,
  `Board 6 · 3NT by North, down three`, `Board 14 · 1NT by West, made`,
  `Board 5 · 2♠ by South over a weak two`, `Board 17 · 6♣ by South, from a
  teams championship`, each with its blurb; every one loads.
- **P-1.2-2 [smoke] IMP pricing and the demoted badge.** Click **Board 6 ·
  7NT by East** (52 cards played) → **Whole table** → Analyze: three POSTs
  → 200 (~60 s on prod). Pinned (40 deals, v1.4): *Biggest swings* has two
  rows, `4 · E (decl) · ♦Q · −2.50 IMPs · −0.13 tricks · ✗ suboptimal ?` —
  a card that costs almost no tricks but IMPs is **demoted to suboptimal**
  — and `10 · E (decl) · ♠5 · −0.50 · −0.03 · ~ good ?`; pair lines `E/W …
  19✓ 1~ 1✗ of 21 graded · 2 marginal · tricks given up 0.15 · 3.00 IMPs`
  with the East footer `3.00 IMPs (348 points)`; `N/S … 0.00 · 0.00 IMPs`
  (both East swings re-graded on 120 deals; before v1.4 they read −3.00 /
  −0.15 and −1.00 / −0.05, E/W 0.20 · 4.00 IMPs (464 points), N/S 0.38).
- **P-1.2-3 [full] IMPs everywhere.** In every decisions table the headers
  are `Card · Act · Best · IMPs · Grade`; every options list has *Score*
  and *IMPs* columns; hovering an IMPs cell shows the points in its tooltip;
  the pair summary states the IMP total beside the tricks.
- **P-1.2-4 [full] What's new.** The header button opens the panel with
  v1.2 (`What it cost in IMPs, and more example hands`), v1.1 and v1.0
  entries; none reads *In development* once deployed.

## v1.3 — Expert opponents

- **P-1.3-1 [smoke] The toggle and its default swap.** Board 17 loaded,
  *Single dummy*: an **Expert opponents** checkbox sits under the deal
  slider with its one-paragraph explanation. Ticking it moves *Deals per
  decision* from 40 to **60**; unticking moves it back; a count set to
  anything else is left alone. With it on, an **Advanced** disclosure
  opens *Strict*, *Margin (tricks)* 0.10, *Confidence (σ)* 2, *Inner
  sample ratio* 0.5 and a sentence naming the effective bar (≈ 0.32 tricks
  at 60 deals).
- **P-1.3-2 [smoke] A filtered grade, trick by trick.** Board 17 → **E/W**
  → Expert opponents on (60 deals) → Analyze. The West section reads
  *solving… decision 1 of 18 done* and fills in a decision at a time; the
  requests are `POST /api/play/analyze` with `expert_opponents: true`,
  `expert: {inner_ratio: 0.5, tolerance: 0.1, confidence: 2, budget: 20,
  strict: false, depth: 1}`, `expert_constraints: {…}` and a one-element
  `decisions` list (`[1]`, `[3]`, …), all 200. When done the header
  line says `60 deals · saw W + E · expert opponents` and the seat line
  `Graded on N of M sampled deals consistent with expert play by the
  opponents · rejects a play shown ≥ 0.32 tricks worse`; every graded row
  carries a small `c/s deals` count under its badge (60/60 early, more
  examined later). Pinned (v1.4, escalation on): **Graded on 1380 of
  1943**, West **13 ✓ / 2 ~ / 0 ✗ of 15 graded (3 forced) · 2 marginal**,
  `60 deals (×3 when in doubt)`, tricks given up **0.41 · 0.76 IMPs (25
  points)** — four decisions re-graded on 180 deals (`180/181`, `180/322`,
  `180/332`, `180/270` under their badges) — against the plain 40-deal
  run's 13/2/0 and 0.44 · 0.69 IMPs. Eighteen requests, ~80 s on a
  4-thread laptop, ~2–3 min on prod. With *Spend more deals on doubtful
  grades* unticked the v1.3 pins come back: graded on 900 of 1406, 0.48 ·
  0.96 IMPs (32 points). (The sampled count was 1371 at the v1.3 build;
  the v1.4 batch-aggregation change of 2026-09-03 draws the outer deficit
  in different rounds, so it reads 1406 — same 900 consistent, identical
  grades.) **Expert pins are thread-dependent:** the inner sample schedule
  starts at the DDS thread count, so replay this locally with
  `BRIDGE_DDS_THREADS=4` (prod runs 2; both give the pinned numbers) — at
  16 threads the counts and grades hold but the totals move a few
  hundredths. Plain grades do not depend on it. `scripts/pin_example.py`
  replays both runs against a local API and prints every number here.
- **P-1.3-6 [full] Interrupted runs resume.** Start the run above, then
  stop the play API (or go offline) after a few decisions: the West section
  keeps the decisions it has, shows the error with *press Resume*, and a
  **Resume** button appears under Analyze. Bring the API back, press it:
  the run continues from the first missing decision — the finished ones
  return within a second each (server cache) — and finishes with the same
  pinned numbers as an uninterrupted run.
- **P-1.3-3 [full] Strict.** Same again with *Strict* ticked: the request
  carries `strict: true`, the header says `expert opponents (strict)`, and
  the run is several times slower. Not pinned (strict verdicts move with
  the draw order); for orientation, prod on 2026-09-03 took ~20 min for
  the 18 requests and read 13/2/0 · 0.45 · 0.74 IMPs, graded on 900 of
  4770.
- **P-1.3-4 [full] Off means off.** Untick the toggle, Analyze: one request
  per seat, no `expert_opponents` field, no seat line, no per-row counts;
  the plain numbers (P-1.0-2) come back exactly.
- **P-1.3-5 [full] What's new.** The panel lists v1.3 *Expert opponents*
  with four entries above v1.2.

## v1.4 — Expert opponents: faster, and right about dummy (unreleased)

- **P-1.4-1 [full] A defender's grade is filtered on declarer's plays from
  dummy.** Local, scripted: `scripts/bench_play.py docs/play/board7.lin --qx
  o7 --strict --deals 100 --seats E` against a fresh play API started with
  `BRIDGE_DDS_THREADS=16`, then `scripts/compare_bench.py
  docs/play/bench/board7-o7-strict100.json <run>.json` must pass for East.
  Pinned in that file (2026-09-08, escalation on, **taken before the
  unfiltered trigger was dropped** — its two `‡` rows, T6 ♥9 and T8 ♠T,
  now stay at 100 deals, same status, and the seat is ~90 s faster; the
  file is due a re-baseline on the next strict run): East **8 ✓ / 2 ~ /
  0 ✗ of 10 · 3 marginal**, 0.48 tricks · 1.41 IMPs, `sampled 14956,
  consistent 2000` over the seat (five decisions extended to 300 deals);
  the trick-4 ♥J reads *good* (−0.17 ± 0.06) and the trick-6 ♥9 *optimal*
  — the v1.3 build graded both *suboptimal* on unfiltered pools
  (`2000→0`, inference `none`) because every layout shared one memoised
  verdict on declarer's ♦A from dummy. Declarer (N): 18/0/2, 5.72 IMPs,
  the opening lead no longer judged by the filter and each decision
  starting from the previous one's pool (`carried` > 0 from the second
  decision on; that seat took 209 s, 110 s before escalation). Decisions
  must be requested in index order for the pins to hold — the UI and this
  script do. (2026-09-04 pins, escalation off: E 8/2/0 · 0.53 · 1.45,
  `10672 / 991`; N 17/2/1 · 5.82.)
- **P-1.4-2 [full] Same verdicts, faster.** The closed room,
  `--qx c7 --strict --deals 100`, all seats: `compare_bench.py` against the
  committed `board7-c7-strict100.json` passes except on its former `‡`
  rows (19/0/1 · 11/0/0 · 10/0/0, 2.21 · 0 · 0.07 IMPs; S T9 ♦6 −0.16 ±
  0.08 tricks / −2.03 IMPs, suboptimal and marginal). **The committed
  strict baselines were taken with the unfiltered trigger still in**
  (dropped 2026-09-08 without a re-run): their `‡` rows — c7 E T3 ♥9, W
  T6 ♥3, W T9 ♥T; o7 S T5 ♣2, N T6 ♠4, E T6 ♥9, E T8 ♠T; c14 W T2 ♣2, S
  T6 ♣8 — now stay at 100 deals with the same status, and the totals
  drop by about those rows' time (c7 1 013 → ~670 s, o7 936 → ~780 s,
  c14 665 → ~520 s expected; 814 / 535 / 384 s with escalation off,
  1 569 s for c7 at the v1.3 build). Re-baseline on the next strict run
  and re-pin here. This laptop's DDS rate drifts ±15 % with temperature,
  so compare the `dds` counters too.
- **P-1.4-3 [smoke] Plain grading untouched.** P-1.0-2 and P-1.3-2 still
  read their pinned numbers (P-1.3-2 at 4 threads).
- **P-1.4-4 [full] What's new.** The panel lists v1.4 *How sure is that
  grade?* with a *new*, a *fixed* and an *improved* entry above v1.3; *In
  development* until deployed.
- **P-1.4-5 [smoke] Every grade says how sure it is.** Board 17 → E/W →
  Analyze (defaults). The sidebar has a ticked **Spend more deals on
  doubtful grades (×3)** checkbox under the deal slider with its
  explanation; the request carries `escalation: {factor: 3}`. The seat
  line reads `13✓ 2~ of 15 graded (3 forced) · 4 marginal · 40 deals (×3
  when in doubt) · saw W + E`. Four rows — T1 W ♠5, T5 E ♥2, T7 W ♥4, T7 E
  ♥3 — carry a **dashed badge ending in `?`** whose tooltip starts `120
  deals (extended: …)` and ends `the grade could read differently on
  another sample of this size`; every other graded row's tooltip reads
  `40 deals — firm within ±2σ`. The IMPs cell of an escalated row shows a
  small `±0.1` / `±0.2` beside the value, and hovering the *Best* cell
  gives `vs best: −0.15 ± 0.04 tricks over 120 deals` (T5 E ♥2). The
  response's decisions carry `sample: {deals, se_tricks, se_imps, firm,
  escalated, trigger}` (forced ones `null`) and `summary.marginal: 4`.
- **P-1.4-6 [full] Escalation off reproduces the earlier pins.** Untick
  the checkbox → Analyze: the request carries `escalation: null`, no row
  shows `?` or `±`, and the seat reads exactly the v1.0–v1.3 pins — 13/2/0,
  0.45 · 0.82 IMPs (27 points); with Expert opponents on, graded on 900 of
  1406, 0.48 · 0.96 IMPs (32 points) at 4 threads. Re-tick it: the v1.4
  pins (P-1.0-2, P-1.3-2) come back from the server cache at once.
- **P-1.4-7 [full] Two triggers only.** No decision in any response
  carries a `trigger` other than `"status"`, `"band"` or `null`; the
  strict bench reports mark extensions `*` / `†` only. (An unfiltered
  second-opinion trigger was built and dropped the same day.)
