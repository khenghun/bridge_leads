"""
Exact constrained deal sampler.

Samples *uniformly* from all deals consistent with the known cards and the
per-seat HCP bounds. Suit-length / shape constraints are enforced by plain
rejection on the finished deal afterwards, which keeps the sample exactly
uniform over the full constraint set (uniform over HCP-valid deals, thinned
by a deal-independent predicate).

Why this is fast: HCP depends only on the honor cards, and honors come in
just four value classes (A=4, K=3, Q=2, J=1) within which cards are
exchangeable. A small dynamic program over those classes counts, with exact
integer arithmetic, how many complete deals every partial honor split can
produce (multinomial weights for the identical-value cards, times the
multinomial for dealing the spot cards into the leftover capacity). Sampling
walks the DP with integer-weighted draws, then deals the concrete cards
uniformly within each class and shuffle-cuts the spots — so tight HCP bands
(a 15-17 or 20-21 seat) cost nothing at all, where rejection sampling burns
hundreds of attempts per accepted deal.

`ExactDealSampler.total` is the exact number of HCP-consistent completions;
0 means the constraints are infeasible.
"""

import random
from math import factorial

from .deal_generator import (
    ALL_CARDS_SET, HCP_VALUES, HONORS, PLAYERS, SUITS, calculate_hcp,
)

_FACT = [factorial(n) for n in range(53)]

# compositions of n into k non-negative parts, cached (n <= 4, k <= 4)
_COMPS_CACHE = {}


def _comps(n, k):
    key = (n, k)
    got = _COMPS_CACHE.get(key)
    if got is None:
        if k == 1:
            got = [(n,)]
        else:
            got = [(i,) + rest
                   for i in range(n + 1) for rest in _comps(n - i, k - 1)]
        _COMPS_CACHE[key] = got
    return got


def _class_ways(m, comp):
    """Ways to hand m distinct same-value cards out in the given split."""
    w = _FACT[m]
    for c in comp:
        w //= _FACT[c]
    return w


class ExactDealSampler:
    """Uniform sampler over deals satisfying known cards + HCP bounds.

    Args mirror `generate_deal`: `known_hands` (player -> fixed cards),
    `hcp_constraints` (player -> (min, max), either bound None),
    `suit_constraints` (player -> {suit: (min, max)}), `acceptors`
    (player -> predicate on the finished 13-card hand). Suit constraints and
    acceptors are applied by rejection inside `sample()`.

    Build once per constraint set (the DP costs a few ms), then call
    `sample(rng)` per draw; it returns a hands dict or None (rejected).
    """

    def __init__(self, known_hands, hcp_constraints=None,
                 suit_constraints=None, acceptors=None):
        self.total = 0
        self._acceptors = acceptors or None

        known = {p: list((known_hands or {}).get(p, [])) for p in PLAYERS}
        self._known = known
        all_known = set()
        for cards in known.values():
            all_known.update(cards)
        remaining = sorted(ALL_CARDS_SET - all_known)

        caps = {p: 13 - len(known[p]) for p in PLAYERS}
        if any(c < 0 for c in caps.values()):
            return
        seats = [p for p in PLAYERS if caps[p] > 0]
        self._seats = seats
        self._caps = [caps[p] for p in seats]
        k = len(seats)

        hcp_constraints = hcp_constraints or {}
        lo = {}
        hi = {}
        for p in PLAYERS:
            c = hcp_constraints.get(p, (None, None))
            mn = c[0] if c[0] is not None else 0
            mx = c[1] if c[1] is not None else 40
            base = calculate_hcp(known[p])
            if base > mx:
                return                      # fixed cards already bust the max
            if caps[p] == 0 and base < mn:
                return                      # full hand below its minimum
            lo[p] = max(0, mn - base)
            hi[p] = mx - base

        # honor value classes present in the unseen cards, high to low
        classes = []
        class_cards = []
        for v in (4, 3, 2, 1):
            cards = [c for c in remaining if HCP_VALUES.get(c[1], 0) == v]
            if cards:
                classes.append((v, len(cards)))
                class_cards.append(cards)
        self._classes = classes
        self._class_cards = class_cards
        self._spots = [c for c in remaining if c[1] not in HONORS]

        total_pts = sum(v * m for v, m in classes)
        # only seats whose bounds can actually bind get a points dimension
        tracked = [i for i, p in enumerate(seats)
                   if lo[p] > 0 or hi[p] < total_pts]
        self._tracked = tracked
        self._lo = [lo[seats[i]] for i in tracked]
        self._hi = [hi[seats[i]] for i in tracked]

        # forward pass: reachable (honor counts, tracked points) states
        state0 = ((0,) * k, (0,) * len(tracked))
        layers = [{state0}]
        for v, m in classes:
            comps = _comps(m, k)
            nxt = set()
            for a, pts in layers[-1]:
                for comp in comps:
                    ns = self._step(a, pts, v, comp)
                    if ns is not None:
                        nxt.add(ns)
            layers.append(nxt)

        # backward pass: exact completion counts per state
        n_spots = len(self._spots)
        terminal = {}
        for a, pts in layers[-1]:
            if any(pts[j] < self._lo[j] for j in range(len(tracked))):
                continue
            w = _FACT[n_spots]
            for i in range(k):
                w //= _FACT[self._caps[i] - a[i]]
            terminal[(a, pts)] = w
        counts = [None] * len(classes) + [terminal]
        for t in range(len(classes) - 1, -1, -1):
            v, m = classes[t]
            comps = _comps(m, k)
            nxt = counts[t + 1]
            cur = {}
            for state in layers[t]:
                a, pts = state
                tot = 0
                for comp in comps:
                    ns = self._step(a, pts, v, comp)
                    if ns is not None:
                        c = nxt.get(ns)
                        if c:
                            tot += _class_ways(m, comp) * c
                if tot:
                    cur[state] = tot
            counts[t] = cur
        self._counts = counts
        self._state0 = state0
        self.total = counts[0].get(state0, 0) if classes else \
            terminal.get(state0, 0)

        # suit-length envelope for the rejection step
        bounds = {}
        if suit_constraints:
            for p in seats:
                if p in suit_constraints:
                    b = {}
                    for s, (mn, mx) in suit_constraints[p].items():
                        b[s] = (mn if mn is not None else 0,
                                mx if mx is not None else 13)
                    if b:
                        bounds[p] = b
        self._suit_bounds = bounds or None

    def _step(self, a, pts, v, comp):
        """Apply a class split to a state; None if capacity/max-HCP violated."""
        na = list(a)
        caps = self._caps
        for i, c in enumerate(comp):
            n = a[i] + c
            if n > caps[i]:
                return None
            na[i] = n
        npts = list(pts)
        for j, i in enumerate(self._tracked):
            c = comp[i]
            if c:
                q = pts[j] + v * c
                if q > self._hi[j]:
                    return None
                npts[j] = q
        return (tuple(na), tuple(npts))

    def sample(self, rng=None):
        """One uniform draw. Returns {player: [13 cards]} or None if the deal
        was rejected by the suit bounds / acceptors (or self.total == 0)."""
        if not self.total:
            return None
        if rng is None:
            rng = random

        # walk the DP: pick each class split with probability proportional
        # to (ways to deal these cards) x (exact completions afterwards)
        k = len(self._seats)
        state = self._state0
        splits = []
        for t, (v, m) in enumerate(self._classes):
            r = rng.randrange(self._counts[t][state])
            nxt = self._counts[t + 1]
            for comp in _comps(m, k):
                ns = self._step(state[0], state[1], v, comp)
                if ns is None:
                    continue
                c = nxt.get(ns)
                if not c:
                    continue
                w = _class_ways(m, comp) * c
                if r < w:
                    splits.append(comp)
                    state = ns
                    break
                r -= w

        # materialise: uniform concrete cards within each class, then spots
        hands = {p: list(self._known[p]) for p in PLAYERS}
        for comp, cards in zip(splits, self._class_cards):
            pool = list(cards)
            rng.shuffle(pool)
            i = 0
            for si, p in enumerate(self._seats):
                n = comp[si]
                if n:
                    hands[p].extend(pool[i:i + n])
                    i += n
        a_final = state[0]
        pool = list(self._spots)
        rng.shuffle(pool)
        i = 0
        for si, p in enumerate(self._seats):
            n = self._caps[si] - a_final[si]
            hands[p].extend(pool[i:i + n])
            i += n

        # rejection step: suit-length envelope, then shape acceptors
        if self._suit_bounds:
            for p, b in self._suit_bounds.items():
                counts = {s: 0 for s in SUITS}
                for c in hands[p]:
                    counts[c[0]] += 1
                for s, (mn, mx) in b.items():
                    if not mn <= counts[s] <= mx:
                        return None
        if self._acceptors:
            for p, pred in self._acceptors.items():
                if not pred(hands[p]):
                    return None
        return hands
