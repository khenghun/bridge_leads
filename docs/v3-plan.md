# v3 detailed plan

Detailed design for the v3 features. High-level status lives in `../ROADMAP.md`.

Status: **features 1, 2 & 3 implemented.** The text syntax (§1.3) is finalized.
Feature 2 ships a single preset (1NT–3NT) for now. Feature 3 shows up to 10
contract-setting sample deals per lead (see §"Open items" note 3).

---

## Feature 1 — Flexible hand constraints `(A or B or C)`

### 1.1 Motivation / the gap

Today a player's shape constraint is a single `{suit: (min,max)}` box — a pure
**AND** of per-suit bounds (`engine/deal_generator.py`, `suit_constraints`).
There's no way to express a **disjunction** of shapes, which real bidding needs.

Worked example — South opens a 15–17 1NT. HCP is a neat range; shape is a
disjunction of five terms (balanced, a 5-card major, or a 6-card minor 6322):

| Term | Meaning | S | H | D | C |
|------|---------|---|---|---|---|
| A | balanced, no 5-card major | 2–4 | 2–4 | 2–5 | 2–5 |
| B | 5 hearts | 2–3 | 5 | 2–4 | 2–4 |
| C | 5 spades | 5 | 2–3 | 2–4 | 2–4 |
| D | 6 clubs (6322) | 2–3 | 2–3 | 2–3 | 6 |
| E | 6 diamonds (6322) | 2–3 | 2–3 | 6 | 2–3 |

A hand is valid if it matches **any one** term (each term ANDs its suit bounds).
HCP `(15,17)` applies on top of whichever term matches. (With a 6-card minor and
≥2 in every suit, the other seven cards split 3-2-2, so the majors cap at 3.)

### 1.2 Data model

Extend the public constraint dict with a new `shapes` key (additive, optional;
the existing `suit_length` / `hcp` / `fixed_cards` keep working):

```python
constraints = {
    'hcp': {'S': (15, 17)},
    'shapes': {                       # NEW — disjunction per player
        'S': [
            {'S': (2,4), 'H': (2,4), 'D': (2,5), 'C': (2,5)},   # A balanced
            {'S': (2,3), 'H': (5,5), 'D': (2,4), 'C': (2,4)},   # B 5 hearts
            {'S': (5,5), 'H': (2,3), 'D': (2,4), 'C': (2,4)},   # C 5 spades
            {'S': (2,3), 'H': (2,3), 'D': (2,3), 'C': (6,6)},   # D 6 clubs
            {'S': (2,3), 'H': (2,3), 'D': (6,6), 'C': (2,3)},   # E 6 diamonds
        ],
    },
    'suit_length': {...},             # still supported (pure AND)
    'fixed_cards': {...},
}
```

- A `shapes[player]` value is a **list of terms** (the OR). Each term is a
  `{suit: (min,max)}` dict (the AND); a missing suit or `None` bound = unbounded.
- A player's hand is valid iff it matches ≥1 term **and** satisfies any
  `suit_length[player]` AND-box (the two compose; usually only one is used).
- HCP is independent and unchanged.

### 1.3 Text syntax

Number-first, suit ∈ {s,h,d,c} (case-insensitive). Inclusive forms are the
recommended primary; strict `<`/`>` kept for compatibility with the user's
original notation.

- **Atom** — a length spec attached to a suit:
  - `n-m s` → range, inclusive (e.g. `2-4h` = 2–4 hearts)
  - `n s`   → exactly n      (e.g. `5s`)
  - `>=n s` / `<=n s` → open-ended inclusive bound
  - `<n s` / `>n s` → strict (`<5h`=≤4, `>1c`=≥2) — compat shorthand
- **Term:** comma-separated atoms inside `( … )`, ANDed. Unmentioned suits =
  unbounded (0–13). Repeated suit → intersect bounds.
- **Expression:** terms joined by the keyword `or`.
- Parser lives in a new `engine/shape_parser.py` → returns the `shapes[player]`
  list above. Pure function, fully unit-tested. Raises a clear error on bad
  tokens / contradictory bounds; warns if a term can't total 13 cards.

**Canonical examples**

South (15–17 1NT — balanced / 5-card major / 6-card minor):

```
(2-4s, 2-4h, 2-5d, 2-5c) or (5h, 2-3s, 2-4d, 2-4c) or (5s, 2-3h, 2-4d, 2-4c)
or (6c, 2-3s, 2-3h, 2-3d) or (6d, 2-3s, 2-3h, 2-3c)
```

North (10–14 3NT raise — §2.3):

```
(2-3s, 2-3h, 2-6d, 2-6c) or (4s, 3h, 3d, 3c) or (4h, 3s, 3d, 3c)
```

### 1.4 Generator strategy — envelope + predicate (rejection)

Chosen approach (simplest *and* most statistically faithful):

1. **Envelope:** for each player with `shapes`, compute the bounding box across
   its terms — `min(min_i)` and `max(max_i)` per suit. Feed that to the existing
   fast `suit_constraints` path so distribution still respects per-suit max
   (keeps the multithreaded-friendly, low-waste generator intact).
2. **Predicate:** after a deal is built, check each constrained player's hand
   against its disjunction — valid iff it matches ≥1 term. Reject & retry on miss.

Why not "pick one term per attempt and generate to its tight bounds": uniform
term selection distorts shape frequencies (5-card-major openings are far rarer
than balanced). Random fill within the envelope reproduces each shape at its
**natural combinatorial frequency** — which is exactly what an unbiased
Monte-Carlo wants. Bonus: the predicate composes cleanly across multiple
constrained players, where per-term selection would need a term cross-product.

Acceptance rate for the 1NT example is high (the envelope is "2–5 in every suit,
no singletons"; the main rejects are 5-5 majors and the like), so the extra
rejection is cheap.

### 1.5 Code changes

- `engine/deal_generator.py`: add an optional `acceptors=None` param — a
  `dict player -> callable(cards)->bool`. Checked just before returning a deal
  (alongside the existing `suit_min` end-check); on failure, continue the retry
  loop. Backward compatible (default `None` = today's behaviour).
- `engine/shapes.py` (new): `compile_shapes(terms)` → `(envelope_box, predicate)`;
  `matches(cards, terms)` helper. `envelope_box` merges into the `suit_length`
  passed to the generator; `predicate` goes into `acceptors`.
- `engine/shape_parser.py` (new): the §1.3 text → terms parser.
- `engine/lead_simulator.py` (`_build_known_and_constraints`): translate
  `constraints['shapes']` into the envelope (merged into `suit_length`) and into
  `acceptors`, then pass `acceptors=` through to `generate_deal`.
- `app.py`: add a free-text shape box per constrained seat (declarer / dummy /
  partner), parsed via `shape_parser`, with inline validation errors. Coexists
  with the existing numeric suit-length inputs.

### 1.6 Tests

- `shape_parser`: token cases (`<5h`, `>1c`, `5h`), AND within term, `or` across
  terms, whitespace, errors, contradiction/can't-make-13 warnings.
- `shapes`: envelope = elementwise min/max; `matches()` truth table for A/B/C;
  a hand matching no term rejected, each matching term accepted.
- `deal_generator` with `acceptors`: over many seeded deals, every generated
  South hand satisfies ≥1 term **and** 15–17 HCP; `acceptors=None` unchanged.
- Invariant: observed shape-class frequencies are non-degenerate (term A ≫ B,C),
  confirming we didn't flatten the distribution.

---

## Feature 2 — Basic auction demo (1NT–3NT) with predefined constraints

### 2.1 Idea

A small registry of named auctions, each mapping to a contract + a predefined
constraint set (built on feature 1's `shapes`). Selecting one auto-fills the
contract/declarer and the constraint editor, so a user sees the simulator
respond to a standard sequence without hand-entering constraints. The 1NT–3NT
example *is* the first preset — which is why it covers both features.

### 2.2 Preset model

`engine/auctions.py` (new) — pure data, no UI:

```python
AUCTIONS = {
    '1NT(S) – 3NT(N)': {
        'level': 3, 'strain': 'N', 'declarer': 'S',   # leader = W (LHO)
        'constraints': {
            'hcp': {'S': (15, 17), 'N': (10, 15)},
            'shapes': {
                'S': [term_A, term_B, term_C],          # the 15–17 1NT spec above
                'N': [responder_3NT_terms...],          # see 2.3 — sensible default
            },
        },
        'note': 'Standard 15–17 1NT, direct raise to game.',
    },
    # more auctions added over time
}
```

### 2.3 Responder (North) constraints

HCP `(10, 14)`. Shape: always ≥2 in each suit, minors ≤6, majors ≤3 — **except**
an exact 4333 with a 4-card major is allowed. Because the 4-card-major case
breaks the majors-≤3 rule, it needs its own term:

| Term | Meaning | S | H | D | C |
|------|---------|---|---|---|---|
| A | no 4-card major | 2–3 | 2–3 | 2–6 | 2–6 |
| B | 4333, 4 spades | 4 | 3 | 3 | 3 |
| C | 4333, 4 hearts | 3 | 4 | 3 | 3 |

```python
'N': [
    {'S': (2,3), 'H': (2,3), 'D': (2,6), 'C': (2,6)},   # A: no 4-card major
    {'S': (4,4), 'H': (3,3), 'D': (3,3), 'C': (3,3)},   # B: 4=spades, 4333
    {'S': (3,3), 'H': (4,4), 'D': (3,3), 'C': (3,3)},   # C: 4=hearts, 4333
]
```

Text form:

```
(>1s, >1h, >1d, >1c, <4h, <4s, <7c, <7d) or (4s, 3h, 3d, 3c) or (4h, 3s, 3d, 3c)
```

### 2.4 Code changes

- `engine/auctions.py` (new): the registry above + a `get_auction(name)` helper.
- `app.py`: a "Demo auction" selector in the sidebar; on selection, populate
  contract / declarer / constraints from the preset (leaving the leader hand for
  the user, or for feature 3's sample deals). A "clear / back to manual" option.
- No engine changes beyond feature 1 — presets are just constraint dicts.

### 2.5 Tests

- Each preset's constraints are well-formed (parse/compile without error; terms
  can make 13 cards; HCP ranges valid).
- `simulate_opening_lead` runs end-to-end on the 1NT–3NT preset with a fixed
  leader hand + seed and returns a ranked, non-empty lead table.

Two presets shipped: **1NT(S)–3NT(N)** (HCP 15–17 / 10–14) and **2NT(S)–3NT(N)**
(same shapes, HCP 20–21 / 4–10).

---

## Feature 3 — Sample dealt hands showcasing the lead engine

Implemented as **live samples from the user's own run**, not a canned gallery:
`simulate_opening_lead` returns a `samples` field — per candidate lead, up to
`max_samples` (10) example deals in which that lead *defeats* the contract
(layout + declarer/defense tricks), collected during the existing solve loop.
The UI renders them as 4-hand cross diagrams under a "Sample deals" section. This
shows the engine working on whatever contract/constraints the user set up
(including the auction presets). Tests assert the cap, that every sample is
genuinely defeated, tricks sum to 13, and the leader's hand is fixed.

---

## Feature 4 — Faster leader-hand entry

Two shortcuts for filling the leader's 13-card hand (all in `app.py`, before any
solving), in addition to per-suit typing:

- **🎲 Random hand** — `randomize_leader_hand()` deals a random 13 cards into the
  `lead_<suit>` boxes (high-to-low), via the button's `on_click`.
- **Paste PBN** — `apply_pbn()` parses `spades.hearts.diamonds.clubs`
  (e.g. `T.KT932.Q2.T9843`; `10`→`T`, case-insensitive) into the four boxes via
  `on_change`. Validation: exactly 4 dot groups, legal ranks, no within-suit
  duplicate; malformed input leaves the boxes untouched and shows an inline
  error. The per-suit boxes remain the single source of truth.

---

## Feature 5 — Sample-deal interactivity

Refinements to the §3 sample-deals section:

- **Lead tracks the recommended lead by scoring mode.** `render_results` stamps
  `sample_lead_mode` and re-points the viewed lead to `best_mp` / `best_imp`
  whenever the mode changes (or on a new run) — so toggling Matchpoints ↔ IMPs
  moves the samples to the new recommendation.
- **Clickable candidate leads.** The dropdown is replaced by suit-labelled lead
  chips (one `st.button` per candidate, 7/row), the recommended one marked ★ and
  the selected one highlighted `primary`. A click sets the viewed lead via
  `on_click` (correct highlight on the same rerun) and stamps the current mode,
  so an explicit pick sticks until the next mode flip / run. Results persist in
  `st.session_state`, so chips survive reruns.

---

## Open items

All v3 features (1–5) are implemented and verified. Nothing outstanding.
