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
  forced**; `Tricks given up: 0.45` · **0.82 IMPs (27 points)**.
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
  `1 N ♠9 −0.55 IMPs / −0.50 tricks`, `7 W ♥4 −0.50 / −0.20`,
  `8 S ♣3 −0.40 / −0.20`, `4 N ♦5 −0.40 / −0.17`; pair lines `E/W …
  tricks given up 0.45 · 0.82 IMPs` and `N/S … defensive tricks given up
  1.32 · 1.83 IMPs`. The
  explanatory line says dummy (East) makes no decisions.
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
  → 200 (~60 s on prod). Pinned (40 deals): *Biggest swings* has two rows,
  `4 · E (decl) · ♦Q · −3.00 IMPs · −0.15 tricks · ✗ suboptimal` — a card
  that costs almost no tricks but three IMPs is **demoted to suboptimal** —
  and `10 · E (decl) · ♠5 · −1.00 · −0.05 · ~ good`; pair lines `E/W …
  tricks given up 0.20 · 4.00 IMPs` with the East footer `4.00 IMPs (464
  points)`; `N/S … 0.00 · 0.38 IMPs`.
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
  carries a small `c/s deals` count under its badge (60/60 early, more examined later). Pinned (local, v1.3 build, 2026-09-01): **Graded on 900 of
  1371**, West **13 ✓ / 2 ~ / 0 ✗ of 15 graded (3 forced)**, tricks given
  up **0.48 · 0.96 IMPs (32 points)** — against the plain 40-deal run's
  13/2/0 and 0.45 · 0.82 IMPs. Eighteen requests, ~70 s on a 4-thread
  laptop, ~3–4 min on prod.
- **P-1.3-6 [full] Interrupted runs resume.** Start the run above, then
  stop the play API (or go offline) after a few decisions: the West section
  keeps the decisions it has, shows the error with *press Resume*, and a
  **Resume** button appears under Analyze. Bring the API back, press it:
  the run continues from the first missing decision — the finished ones
  return within a second each (server cache) — and finishes with the same
  pinned numbers as an uninterrupted run.
- **P-1.3-3 [full] Strict.** Same again with *Strict* ticked: the request
  carries `strict: true`, the header says `expert opponents (strict)`, and
  the run is several times slower.
- **P-1.3-4 [full] Off means off.** Untick the toggle, Analyze: one request
  per seat, no `expert_opponents` field, no seat line, no per-row counts;
  the plain v1.0 numbers (P-1.0-2) come back exactly.
- **P-1.3-5 [full] What's new.** The panel lists v1.3 *Expert opponents*
  with four entries above v1.2.
