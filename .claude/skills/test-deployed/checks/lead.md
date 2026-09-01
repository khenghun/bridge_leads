# Lead / contract app — regression checks

Site: https://bridge-leads.icycookie.xyz (local: http://localhost:5173/).
One section per release of `frontend/src/apps/changelog/releases.ts`, oldest
first; IDs are `L-<version>-<n>`. Tags: `[smoke]` always, `[full]` on the
release under test or after an engine change. Vectors are the share payloads
in `../vectors/`; print their URLs with `python scripts/regression.py urls`.

Pinned values were captured on prod at v2.2 (SHA `b5f34d1`) on 2026-09-01
unless a check says otherwise.

## v1.0 — Opening Lead Simulator

- **L-1.0-1 [smoke] API alive.** `curl /api/health` → `{"status":"ok"}`;
  `curl /api/auctions` → 200, JSON listing the two demo auctions
  `1NT (S) – 3NT (N)` and `2NT (S) – 3NT (N)`.
- **L-1.0-2 [smoke] A constrained simulation, end to end.** Open vector
  `lead-1nt-3nt` on a fresh document (West holds `KJ973.A5.T82.J64` vs 3NT
  by South, 1NT–3NT constraints, 300 deals, IMPs). One `POST /api/simulate`
  → 200, ~5 s. Ranked table has **11 rows**, headers
  `Lead · Decl. tricks · Defeat % · MP% · IMPs`. Pinned rows:

  | Lead | Decl. tricks | Defeat % | MP% | IMPs |
  | --- | --- | --- | --- | --- |
  | ♥A | 10.18 | 14.3% | 51.83 | +0.437 |
  | ♠73 | 10.27 | 13.0% | 48.31 | +0.330 |
  | ♠9 | 10.27 | 12.7% | 48.24 | +0.293 |
  | ♠J | 10.38 | 9.7% | 45.42 | −0.080 |
  | ♣64 | 10.28 | 9.7% | 53.32 | −0.090 |
  | … | | | | |
  | ♥5 | 10.53 | 3.3% | 42.42 | −0.897 |

  Console: 0 errors, 0 warnings.
- **L-1.0-3 [full] Demo auction fills the constraints.** Fresh load of `/`,
  pick `1NT (S) – 3NT (N)` in the auction dropdown: contract becomes 3NT by
  South, South's HCP reads 15–17 and North's 10–14, both seats' *Advanced
  shape* boxes carry the preset text (South's starts
  `(2-4s,2-4h,2-5d,2-5c) or (5h,…`). Enter `KJ973.A5.T82.J64`, Simulate →
  200 and the request body carries `hcp.S = [15,17]`, `hcp.N = [10,14]` and
  both `shapes` strings.
- **L-1.0-4 [full] Infeasible constraints are a message, not a crash.** With
  the demo above set North's HCP min to 30 (30 + 15 + West's 11 > 40):
  Simulate returns 422 and the UI shows the backend's `detail` text inline;
  the previous result (if any) is still displayed.
- **L-1.0-5 [full] Scoring toggle is local.** On the L-1.0-2 result click
  *Matchpoints*: the table re-ranks by MP% (♦8 54.54 first, ♦2 54.50, ♦T
  54.44) with **no new request**; *IMPs* restores ♥A first.

## v1.1 — Compare two opening leads

- **L-1.1-1 [full] Head-to-head.** On the L-1.0-2 result open *Compare
  leads* → *Compare*, pick ♥A vs ♠73. Wins + draws + losses = **300**; the
  panel shows an average IMP swing and a head-to-head MP%. No request.
- **L-1.1-2 [full] Sample deals by outcome.** Under *Sample deals* click
  `★ ♥A`: deal diagrams appear, each a full four-hand deal with West =
  `KJ973.A5.T82.J64`; the outcome buckets (deals where the lead wins /
  draws / loses against the compared lead) each show a count and the three
  counts sum to 300.

## v1.2 — Suit quality constraint

- **L-1.2-1 [full] One quality in the whole table.** Fresh load, demo
  `1NT (S) – 3NT (N)`, hand `KJ973.A5.T82.J64`. Set North ♥ quality
  *good*, then East ♠ quality *poor*: the North pick clears itself (only one
  quality select is not `—`). Simulate → 200, request body
  `quality = {"E": {"S": "poor"}}` and nothing else under `quality`.
- **L-1.2-2 [full] Quality is fast.** The run above completes in the same
  ~5 s as L-1.0-2 — a quality constraint must not fall back to the
  rejection sampler (which would take tens of seconds).

## v2.0 — Optimal Contract Calculator

- **L-2.0-1 [smoke] A contract ranking, end to end.** Open vector
  `contract-1s-raise` on a fresh document (South `AKJ73.K5.Q82.J64`, partner
  10–14 HCP with 3+ spades, none vul, 150 deals, all strains, IMPs). One
  `POST /api/contract/simulate` → 200, ~10 s. Pinned:
  - conclusion: **Stay in 4♠** by South · `makes 64% · 9.9 of 10 tricks ·
    150 deals` · `Next best 3NT trails by 1.61 ±0.47 IMPs.`
  - context line: `opponents make a game on 2% · par is theirs or a save on 18%`
  - benchmark dropdown has **20** options, `4♠ by South` selected;
  - top rows (`# · Contract · By · Make % · Tricks · IMPs vs 4♠ · Mean score
    · When it fails`):

    | # | Contract | By | Make % | Tricks | IMPs | Mean | Fails |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | 1 | 4♠ baseline | S | 64% | 9.9 / 10 | +0.00 | 256 | −62 |
    | 2 | 3NT | S | 53% | 8.6 / 9 | −1.61 | 186 | −91 |
    | 3 | ♠ partscore | S | 100% | 9.9 / 7 | −2.03 | 166 | — |
    | 4 | NT partscore | S | 89% | 8.6 / 7 | −2.91 | 127 | −75 |
    | 5 | ♣ partscore | S | 65% | 7.6 / 7 | −4.69 | 42 | −76 |

  - a *Show all 20 contracts* button; console clean.
- **L-2.0-2 [full] Benchmark and mode are local.** Change *Compare against*
  to `3NT by South`: the 3NT row reads `+0.00` and 4♠ reads `+1.61`, column
  header `IMPs vs 3NT`, **no new request**. Switch to *Matchpoints*: the
  column becomes MP% vs the benchmark and the baseline row reads 50.0.
- **L-2.0-3 [full] The three companion views.** *Every contract at a
  glance* is a 5×4 grid (NT ♠ ♥ ♦ ♣ × Partscore / Game / Slam (6) / Grand
  (7)) with IMPs and a small make %; *Compare two contracts* takes two picks
  and shows win / draw / lose over 150 deals; sample deals split into
  *makes* and *fails* with counts that sum to 150 for the chosen contract.
- **L-2.0-4 [full] Tabs keep results.** With both L-1.0-2 and L-2.0-1
  results on screen, switch `#lead` ↔ `#contract` ↔ `#changelog` and back:
  both results are still there and the network log shows no new POST.
- **L-2.0-5 [full] Par needs the whole table.** Untick ♣ and re-run: the
  request's `strains` has four entries, the result comes back faster, and
  the `par is theirs or a save on` figure is **absent** (withheld, not 0%).

## v2.1 — Specific cards, and a phone-friendly app

- **L-2.1-1 [full] Pin cards into an unseen hand.** Demo `1NT (S) – 3NT
  (N)`, hand `KJ973.A5.T82.J64`, open ➕ *Specific cards* on North and type
  `AK` in the ♥ row → Simulate → 200 with `fixed_cards = {"N": ["HA","HK"]}`.
  Type `A` in North's ♥ row *and* South's ♥ row: an inline clash message
  appears and Simulate is **disabled** — no request is made. Type `K` in
  North's ♠ row (West holds ♠K): same — flagged, disabled.
- **L-2.1-2 [full] What's new tab.** `#changelog` lists every release newest
  first with the newest marked *Latest*; the top version equals the newest
  non-`unreleased` entry of `releases.ts` (`coverage` prints it), and an
  entry that is still `unreleased` reads *In development*.
- **L-2.1-3 [full] Phone layout.** `browser_resize` to 390×844, fresh load:
  `document.documentElement.scrollWidth <= window.innerWidth` (no sideways
  page scroll — results tables scroll inside their own box); the *Simulate*
  button is inside the viewport without scrolling (pinned to the bottom);
  hand-entry inputs have `font-size >= 16px` (no iOS zoom) and
  `inputmode="numeric"` on the number fields; the tab bar and the light-mode
  switch are both visible. Contract tab: strain buttons carry their suit
  colour and dim when toggled off, in dark mode too.

## v2.2 — Results worth sharing

- **L-2.2-1 [smoke] Share links reproduce the result.** L-1.0-2 and L-2.0-1
  *are* this check — each opens from a `#tool?s=…` link on a fresh load and
  reproduces the pinned numbers. Additionally each conclusion card has a
  `🔗 Copy link` button.
- **L-2.2-2 [smoke] The conclusion card and its noise.** On L-1.0-2 the card
  reads `♥A vs 3NT by South` · `+0.44 IMPs · defeats the contract 14% · 300
  deals` and, because the top two sit inside the noise:
  `⚖ Too close to call at 300 deals — the 0.11 IMPs gap over ♠73 is within
  sampling noise (±0.30).` with a **Re-run with 1000 deals** button.
  On L-2.0-1 it reads the margin with its ±: `trails by 1.61 ±0.47 IMPs`.
- **L-2.2-3 [full] Re-run and the run history.** Click *Re-run with 1000
  deals*: a new `POST /api/simulate` with `num_simulations = 1000`, ~15 s;
  the earlier-runs strip now lists two runs; clicking the first restores the
  300-deal result (♥A +0.437) with **no request**; clicking the second
  restores the 1000-deal one the same way.
- **L-2.2-4 [full] The question is echoed.** L-2.0-1's card is followed by
  `you sit South: AKJ73.K5.Q82.J64` · `none vul` · `150 deals` and the
  constraint summary `North (your partner): 10–14 HCP · ♠ 3+` · `West
  (LHO): any hand` · `East (RHO): any hand`. L-1.0-2 shows the equivalent
  for West's lead problem (contract, hand, South 15–17 / North 10–14 and
  their shapes).
- **L-2.2-5 [full] Filter deals by a hidden hand.** Under sample deals set
  the filter to *only deals where North (partner) has 4+ spades*: the deal
  count drops, every shown deal satisfies it, and the ranking table above
  is unchanged (browsing only). *Exclude* shows the complement; the two
  counts sum to the unfiltered count.
- **L-2.2-6 [full] Equivalent leads share a row.** In L-1.0-2 the ranked
  table lists `♠73` and `♣64` as single rows (from `KJ973` the 7 and 3 are
  the same lead; from `J64` the 6 and 4 are) and the note under the table
  explains it; 11 rows total, not 13.
- **L-2.2-7 [full] Every defeating deal is browsable.** Click `★ ♥A` under
  sample deals: the number of deals offered equals `round(14.3% × 300) =
  43`, not a capped sample of a larger set.
