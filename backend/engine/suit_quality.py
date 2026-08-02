"""
Suit quality: one seat, one suit, graded by the top honours held.

    good = at least 2 of the top 3 (A K Q)  OR  at least 3 of the top 5 (A K Q J T)
    poor = anything worse

`good` is the usual "sound preempt / overcall" agreement — the suit a weak-two
or an overcall promises (Ogust's "good suit" responses), and the Klinger suit
quality test's honour half. `poor` is its plain complement, so it matches
roughly 70% of random holdings: it is a deliberately weak filter that says
"this suit is ragged", not a narrow one.

Only **one** such constraint exists per simulation — it comes from the one
player who described a suit in the auction — which is what lets
`honor_sampler.ExactDealSampler` enforce it natively in its DP instead of by
rejection. The predicate here is for the legacy fallback generator (which
enforces it by rejection, like shapes) and for tests.

Note the ten: `deal_generator.HONORS` is A/K/Q/J only, so `T` is an ordinary
spot card everywhere else in the engine. The "3 of the top 5" arm is the sole
reason the sampler has to track it at all.
"""

TOP3 = ('A', 'K', 'Q')
TOP5 = ('A', 'K', 'Q', 'J', 'T')
LEVELS = ('good', 'poor')


def counts(cards, suit):
    """(# of the top 3 held, # of J/T held) in `suit`.

    Cards are endplay format ('SA', 'HT', ...). Splitting the count this way
    mirrors the sampler's two state dimensions: the top-3 arm and the pair that
    only matters for the top-5 arm.
    """
    top3 = 0
    jt = 0
    for c in cards:
        if c[0] != suit:
            continue
        r = c[1]
        if r in TOP3:
            top3 += 1
        elif r == 'J' or r == 'T':
            jt += 1
    return top3, jt


def is_good(top3, jt):
    """The good-suit test on the two counts (see module docstring)."""
    return top3 >= 2 or top3 + jt >= 3


def satisfies(level, top3, jt):
    """True if the counts meet `level` ('good' / 'poor')."""
    return is_good(top3, jt) if level == 'good' else not is_good(top3, jt)


def min_length(level):
    """Cards in the suit the constraint implies, so callers can tighten the
    per-suit minimum. `good` needs 2 (its cheapest arm is 2 of the top 3);
    `poor` implies nothing."""
    return 2 if level == 'good' else 0


def predicate(suit, level):
    """`cards -> bool` for the generator's acceptor path."""
    def pred(cards):
        top3, jt = counts(cards, suit)
        return satisfies(level, top3, jt)

    return pred


def describe(suit, level):
    """Short human-readable form, for error messages."""
    if level == 'good':
        return f"a good {suit} suit (2 of AKQ, or 3 of AKQJT)"
    return f"a poor {suit} suit (worse than 2 of AKQ / 3 of AKQJT)"
