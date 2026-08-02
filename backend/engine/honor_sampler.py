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

A **suit-quality** constraint (at most one per simulation — see
`suit_quality`) is enforced in the same DP rather than by rejection. Honor
classes are split by the constrained suit, so with spades constrained the
aces become `[SA]` and `[HA, DA, CA]`; the constrained suit's ten joins as a
zero-value class, since it is an ordinary spot card everywhere else. Two extra
state dimensions carry the constrained seat's running top-3 and J/T counts, and
the terminal pass filters them exactly where the HCP minimums are filtered. The
quality honors are therefore dealt in the *same* pass that satisfies HCP, so
the two constraints prune each other instead of one being tested after the fact
— and the draw stays exactly uniform.

`ExactDealSampler.total` is the exact number of HCP- and quality-consistent
completions; 0 means the constraints are infeasible.
"""

import random
from math import factorial

from . import suit_quality as sq
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

    `quality` is the optional single suit-quality constraint as a
    `(seat, suit, level)` tuple (level 'good' / 'poor'); unlike the above it is
    enforced natively in the DP, with no rejection.

    Build once per constraint set (the DP costs a few ms), then call
    `sample(rng)` per draw; it returns a hands dict or None (rejected).
    """

    def __init__(self, known_hands, hcp_constraints=None,
                 suit_constraints=None, acceptors=None, quality=None):
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

        # Resolve the suit-quality constraint into (seat index, level, honors
        # the seat already holds). `q_suit` stays None when there is nothing
        # left to steer, so the honor classes are not split needlessly.
        self._quality = None
        q_suit = None
        if quality:
            q_seat, q_suit, q_level = quality
            base3, basejt = sq.counts(known[q_seat], q_suit)
            if q_seat in seats:
                self._quality = (seats.index(q_seat), q_level, base3, basejt)
            else:
                # fully-known hand: the constraint is already decided
                if not sq.satisfies(q_level, base3, basejt):
                    return
                q_suit = None

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

        # Honor value classes present in the unseen cards, high to low. Each
        # entry is (value, multiplicity, quality kind), the last being 'top3' /
        # 'jt' for the constrained suit's own honors and None otherwise. With a
        # quality constraint every class splits in two so the DP can see *which*
        # card is the constrained suit's, and the constrained ten is added as a
        # zero-value class (it is a spot card to the rest of the engine).
        q_ten = q_suit + 'T' if q_suit else None
        classes = []
        class_cards = []
        for v in (4, 3, 2, 1):
            cards = [c for c in remaining if HCP_VALUES.get(c[1], 0) == v]
            if not cards:
                continue
            if q_suit:
                target = [c for c in cards if c[0] == q_suit]
                rest = [c for c in cards if c[0] != q_suit]
                if target:
                    kind = 'top3' if target[0][1] in sq.TOP3 else 'jt'
                    classes.append((v, len(target), kind))
                    class_cards.append(target)
                if rest:
                    classes.append((v, len(rest), None))
                    class_cards.append(rest)
            else:
                classes.append((v, len(cards), None))
                class_cards.append(cards)
        if q_ten and q_ten in remaining:
            classes.append((0, 1, 'jt'))
            class_cards.append([q_ten])
        self._classes = classes
        self._class_cards = class_cards
        self._spots = [c for c in remaining
                       if c[1] not in HONORS and c != q_ten]

        total_pts = sum(v * m for v, m, _ in classes)
        # only seats whose bounds can actually bind get a points dimension
        tracked = [i for i, p in enumerate(seats)
                   if lo[p] > 0 or hi[p] < total_pts]
        self._tracked = tracked
        self._lo = [lo[seats[i]] for i in tracked]
        self._hi = [hi[seats[i]] for i in tracked]

        # forward pass: reachable (honor counts, tracked points, quality) states
        state0 = ((0,) * k, (0,) * len(tracked),
                  (0, 0) if self._quality is not None else ())
        layers = [{state0}]
        for v, m, qk in classes:
            comps = _comps(m, k)
            nxt = set()
            for state in layers[-1]:
                for comp in comps:
                    ns = self._step(state, v, qk, comp)
                    if ns is not None:
                        nxt.add(ns)
            layers.append(nxt)

        # backward pass: exact completion counts per state
        n_spots = len(self._spots)
        terminal = {}
        for state in layers[-1]:
            a, pts, q = state
            if any(pts[j] < self._lo[j] for j in range(len(tracked))):
                continue
            if self._quality is not None:
                _, level, base3, basejt = self._quality
                if not sq.satisfies(level, base3 + q[0], basejt + q[1]):
                    continue
            w = _FACT[n_spots]
            for i in range(k):
                w //= _FACT[self._caps[i] - a[i]]
            terminal[state] = w
        counts = [None] * len(classes) + [terminal]
        for t in range(len(classes) - 1, -1, -1):
            v, m, qk = classes[t]
            comps = _comps(m, k)
            nxt = counts[t + 1]
            cur = {}
            for state in layers[t]:
                tot = 0
                for comp in comps:
                    ns = self._step(state, v, qk, comp)
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

    def _step(self, state, v, qkind, comp):
        """Apply a class split to a state; None if capacity, max-HCP or the
        quality ceiling is violated."""
        a, pts, q = state
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
                p = pts[j] + v * c
                if p > self._hi[j]:
                    return None
                npts[j] = p
        nq = q
        if qkind is not None and self._quality is not None:
            qi, level, base3, basejt = self._quality
            c = comp[qi]
            if c:
                top3, jt = q
                if qkind == 'top3':
                    top3 += c
                else:
                    jt += c
                nq = (top3, jt)
                # 'poor' is a ceiling: once the suit is good it can never go
                # back, so prune here the way max-HCP is pruned above.
                if level == 'poor' and sq.is_good(base3 + top3, basejt + jt):
                    return None
        return (tuple(na), tuple(npts), nq)

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
        for t, (v, m, qk) in enumerate(self._classes):
            r = rng.randrange(self._counts[t][state])
            nxt = self._counts[t + 1]
            for comp in _comps(m, k):
                ns = self._step(state, v, qk, comp)
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
