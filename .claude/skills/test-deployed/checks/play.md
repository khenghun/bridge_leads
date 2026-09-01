# Play solver — regression checks

Site: https://bridge-play.icycookie.xyz (local: http://localhost:5174/play.html).
One section per release of `frontend/src/apps/play/changelog/releases.ts`,
oldest first; IDs are `P-<version>-<n>`. Tags: `[smoke]` always, `[full]` on
the release under test or after an engine change. Every check uses the
built-in example hands (`frontend/src/apps/play/examples.ts`) at the default
**20 deals per decision, single dummy**, so the numbers are reproducible.

Pinned values: Board 17 numbers were pinned locally at v1.2 (2026-09-01,
the same figures the `run-apps` skill expects); Board 6 · 7NT numbers were
pinned on prod at v1.2 (SHA `b5f34d1`) on 2026-09-01.

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
  ~1 s with `seat: "W"`, `method: "single_dummy"`, `num_deals: 20`. Under
  the **West** section, pinned: **12 ✓ / 2 ~ / 1 ✗ of 15 graded, 3
  forced**; `Tricks given up: 0.70` · **1.00 IMPs (32 points)**.
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
  `8 S ♣3 −0.60 IMPs / −0.30 tricks`, `2 S ♠T −0.45 / −0.35`,
  `5 W ♥2 −0.35 / −0.35`; pair lines `E/W … tricks given up 0.70 · 1.00
  IMPs` and `N/S … defensive tricks given up 1.25 · 1.45 IMPs`. The
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
  → 200 (~30 s on prod). Pinned: *Biggest swings* has one row,
  `4 · E (decl) · ♦Q · −1.00 IMPs · −0.05 tricks · ~ good` — a card that
  costs almost no tricks but an IMP is **good, not optimal**; pair lines
  `E/W … tricks given up 0.05 · 1.00 IMPs` with the East footer `1.00 IMPs
  (116 points)`; `N/S … 0.00 · 0.00 IMPs`.
- **P-1.2-3 [full] IMPs everywhere.** In every decisions table the headers
  are `Card · Act · Best · IMPs · Grade`; every options list has *Score*
  and *IMPs* columns; hovering an IMPs cell shows the points in its tooltip;
  the pair summary states the IMP total beside the tricks.
- **P-1.2-4 [full] What's new.** The header button opens the panel with
  v1.2 (`What it cost in IMPs, and more example hands`), v1.1 and v1.0
  entries; none reads *In development* once deployed.
