"""
Disjunctive shape constraints.

A *term* is a dict ``{suit: (min, max)}`` over suits S/H/D/C; a missing suit or a
``None`` bound means unbounded. A *shape* is a list of terms joined by OR — a
hand matches the shape iff it matches **any one** term (and a term matches iff
every suit count is within that term's bounds).

`compile_shapes` turns a shape into:
  - an **envelope** box — the loosest ``{suit: (min, max)}`` covering all terms,
    fed to the deal generator's fast per-suit path so distribution still respects
    the maxima; and
  - a **predicate** ``cards -> bool`` applied after a deal is built to reject
    hands that match no term.

Random fill within the envelope reproduces each shape at its natural
combinatorial frequency, so the predicate doesn't bias the distribution.
"""

SUITS = ['S', 'H', 'D', 'C']


def _suit_counts(cards):
    """Count cards per suit. Cards are endplay format ('SA', 'HT', ...)."""
    counts = {s: 0 for s in SUITS}
    for c in cards:
        s = c[0]
        if s in counts:
            counts[s] += 1
    return counts


def _norm_term(term):
    """Fill missing suits / None bounds so every suit has a concrete (lo, hi)."""
    out = {}
    for s in SUITS:
        lo, hi = term.get(s, (None, None))
        out[s] = (lo if lo is not None else 0, hi if hi is not None else 13)
    return out


def term_matches(counts, term):
    """True if the per-suit counts satisfy every bound in this single term."""
    nt = _norm_term(term)
    return all(nt[s][0] <= counts[s] <= nt[s][1] for s in SUITS)


def matches(cards, terms):
    """True if the hand matches at least one term (the OR)."""
    counts = _suit_counts(cards)
    return any(term_matches(counts, t) for t in terms)


def envelope(terms):
    """Loosest {suit: (min, max)} box covering every term (min of mins, max of
    maxes per suit). Empty shape -> fully unbounded."""
    if not terms:
        return {s: (0, 13) for s in SUITS}
    lo = {s: 13 for s in SUITS}
    hi = {s: 0 for s in SUITS}
    for t in terms:
        nt = _norm_term(t)
        for s in SUITS:
            lo[s] = min(lo[s], nt[s][0])
            hi[s] = max(hi[s], nt[s][1])
    return {s: (lo[s], hi[s]) for s in SUITS}


def compile_shapes(terms):
    """Return (envelope_box, predicate) for a shape (list of terms).

    predicate(cards) -> bool tests the full disjunction; envelope_box is the
    bounding box to hand the generator's per-suit constraint path.
    """
    env = envelope(terms)

    def predicate(cards):
        return matches(cards, terms)

    return env, predicate


def feasibility_warnings(terms):
    """Human-readable warnings for terms that can't form a 13-card hand.

    A term is infeasible if its minimum lengths already exceed 13, or its
    maximum lengths can't reach 13. Returns a list of strings (empty = fine).
    Pure check — does not raise.
    """
    warnings = []
    for i, term in enumerate(terms, 1):
        nt = _norm_term(term)
        min_total = sum(nt[s][0] for s in SUITS)
        max_total = sum(nt[s][1] for s in SUITS)
        if min_total > 13:
            warnings.append(
                f"term {i}: minimum lengths total {min_total} (> 13) — impossible")
        elif max_total < 13:
            warnings.append(
                f"term {i}: maximum lengths total {max_total} (< 13) — impossible")
    return warnings
