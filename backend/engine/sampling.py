"""Constrained deal sampling — shared by every simulator in the project.

Everything here was lifted out of the opening-lead simulator, where it had grown
around one fixed hand (the leader's). It is now parameterised by the *own seat*:
the one seat whose 13 cards the user knows, whichever tool is asking. The lead
app passes the opening leader; the contract calculator passes the user's own
seat.

Two samplers, in order of preference:

- `ExactDealSampler` — exactly uniform over deals consistent with known cards +
  per-seat HCP bounds (+ the one suit-quality constraint, enforced inside its
  DP). Suit-length/shape constraints are applied by rejection.
- `generate_deal` — the legacy steered rejection sampler, only *approximately*
  uniform, kept as a fallback for pathologically tight shape constraints where
  the exact sampler's rejection step starves.
"""

import random

from . import suit_quality
from .deal_generator import (
    generate_deal, PLAYERS as DG_PLAYERS, SUITS as DG_SUITS, calculate_hcp,
)
from .honor_sampler import ExactDealSampler
from .shapes import compile_shapes

# If the exact sampler's shape-rejection step throws away this many draws
# without producing a single deal, the shape constraints are pathologically
# tight for plain rejection; switch to the legacy steered generator (its
# distribution is approximate, but it fills suit minimums during placement).
_EXACT_FALLBACK_ATTEMPTS = 3000

SUIT_ORDER = ['S', 'H', 'D', 'C']
SORT_RANK = {r: i for i, r in enumerate('AKQJT98765432')}


def hand_to_cards(hand_str):
    """PBN hand string 'S.H.D.C' -> list of endplay cards (suit+rank)."""
    if not hand_str:
        return []
    cards = []
    for suit_chars, suit in zip(hand_str.split('.'), SUIT_ORDER):
        for rank in suit_chars:
            cards.append(suit + rank)
    return cards


def hand_list_to_str(cardlist):
    """List of cards -> PBN hand string (suits high-to-low)."""
    suits = {'S': [], 'H': [], 'D': [], 'C': []}
    for card in cardlist:
        if len(card) == 2:
            suits[card[0]].append(card[1])
    for s in SUIT_ORDER:
        suits[s].sort(key=lambda r: SORT_RANK.get(r, 99))
    return '.'.join(''.join(suits[s]) for s in SUIT_ORDER)


def _merge_box(box, env):
    """Intersect a per-suit (min,max) box with an envelope (tighter bound wins).
    `box` bounds may be None (unbounded); `env` bounds are concrete ints."""
    merged = dict(box)
    for s, (lo, hi) in env.items():
        elo, ehi = box.get(s, (None, None))
        mlo = lo if elo is None else max(lo, elo)
        mhi = hi if ehi is None else min(hi, ehi)
        merged[s] = (mlo, mhi)
    return merged


def _all_of(preds):
    """AND a seat's acceptor predicates into one. A seat can attract more than
    one (a shape *and* a suit quality), so they must compose rather than
    overwrite."""
    if len(preds) == 1:
        return preds[0]

    def pred(cards):
        return all(p(cards) for p in preds)

    return pred


def resolve_quality(spec, own_seat):
    """Validate the `{seat: {suit: level}}` suit-quality constraint down to a
    single `(seat, suit, level)` tuple, or None.

    Exactly one is supported: it models the one player who described a suit in
    the auction (the preempter / overcaller), and that ceiling is what lets the
    sampler enforce quality inside its DP instead of by rejection."""
    items = [(p, s, level)
             for p, suits in (spec or {}).items()
             for s, level in (suits or {}).items() if level]
    if not items:
        return None
    if len(items) > 1:
        raise ValueError(
            "Only one suit-quality constraint is supported (the one suit "
            f"described in the auction), but {len(items)} were given.")
    p, s, level = items[0]
    if p == own_seat:
        raise ValueError(
            "Suit quality can only constrain an unseen hand, not your own hand.")
    if p not in DG_PLAYERS:
        raise ValueError(f"unknown seat {p!r} in the suit-quality constraint")
    if s not in DG_SUITS:
        raise ValueError(f"unknown suit {s!r} in the suit-quality constraint")
    if level not in suit_quality.LEVELS:
        raise ValueError(
            f"suit quality must be one of {suit_quality.LEVELS}, got {level!r}")
    return (p, s, level)


def build_known_and_constraints(own_seat, own_cards, constraints):
    """Translate the public constraint dict (keyed by player letter) into the
    deal_generator's format. Returns
    (known_hands, hcp, suit_length, acceptors, quality).

    `own_seat` / `own_cards` are the one hand the user knows in full.
    Disjunctive `shapes` are compiled into (a) an envelope merged into the
    per-suit bounds to keep generation efficient, and (b) acceptor predicates
    that reject finished hands matching no term."""
    constraints = constraints or {}
    known = {own_seat: list(own_cards)}

    # fixed_cards merge into known hands
    for p, cards in (constraints.get('fixed_cards') or {}).items():
        known.setdefault(p, [])
        known[p] = list(known[p]) + [c for c in cards if c not in known[p]]

    hcp = dict(constraints.get('hcp') or {})
    suit_length = {p: dict(v) for p, v in (constraints.get('suit_length') or {}).items()}

    preds = {}
    for p, terms in (constraints.get('shapes') or {}).items():
        if not terms:
            continue
        env, predicate = compile_shapes(terms)
        suit_length[p] = _merge_box(suit_length.get(p, {}), env)
        preds.setdefault(p, []).append(predicate)

    quality = resolve_quality(constraints.get('quality'), own_seat)
    if quality:
        p, s, level = quality
        need = suit_quality.min_length(level)
        if need:
            # 'good' implies at least two cards in the suit; tightening the
            # length minimum prunes deals the DP would otherwise have to build.
            box = dict(suit_length.get(p, {}))
            lo, hi = box.get(s, (None, None))
            box[s] = (need if lo is None else max(lo, need), hi)
            suit_length[p] = box
        # The exact sampler enforces quality natively, so this predicate only
        # ever runs on the legacy fallback generator's path.
        preds.setdefault(p, []).append(suit_quality.predicate(s, level))

    acceptors = {p: _all_of(ps) for p, ps in preds.items()}
    return known, hcp, suit_length, acceptors, quality


def check_hcp_feasibility(known, hcp):
    """The deck holds exactly 40 HCP. Raise ValueError when the per-seat HCP
    bounds (combined with each seat's known cards) can never sum to 40 —
    otherwise generation would grind through every attempt and find nothing."""
    min_total = 0
    max_total = 0
    for p in DG_PLAYERS:
        fixed_cards = known.get(p, [])
        fixed = calculate_hcp(fixed_cards)
        lo, hi = hcp.get(p, (None, None))
        lo = 0 if lo is None else lo
        hi = 40 if hi is None else hi
        if fixed > hi:
            raise ValueError(
                f"No way to meet the HCP constraints: {p}'s known cards already "
                f"hold {fixed} HCP, above the {hi} HCP maximum.")
        if len(fixed_cards) == 13:
            hi = fixed          # a fully-known hand contributes exactly its HCP
        min_total += max(lo, fixed)
        max_total += hi
    if min_total > 40:
        raise ValueError(
            f"No way to meet the HCP constraints: the seat minimums (including "
            f"known cards) total {min_total} HCP, but the deck holds only 40.")
    if max_total < 40:
        raise ValueError(
            f"No way to meet the HCP constraints: the seat maximums allow only "
            f"{max_total} HCP in total, but all 40 HCP in the deck must be dealt.")


def build_sampler(known, hcp, suit_length, acceptors, quality):
    """Build the exact sampler and raise a descriptive ValueError when the
    constraint set admits no deal at all (`.total == 0`)."""
    sampler = ExactDealSampler(known, hcp, suit_length, acceptors or None, quality)
    if sampler.total == 0:
        if quality:
            raise ValueError(
                "No way to meet the constraints: no arrangement of the unseen "
                f"honor cards gives {quality[0]} "
                f"{suit_quality.describe(quality[1], quality[2])} while also "
                "satisfying every seat's HCP range.")
        raise ValueError(
            "No way to meet the HCP constraints: no arrangement of the unseen "
            "honor cards satisfies every seat's HCP range.")
    return sampler


def generate_layouts(known, hcp, suit_length, acceptors, quality,
                     num_deals, rng=None, max_attempts_factor=1000):
    """Sample up to `num_deals` deals as layouts `{seat: 'S.H.D.C'}`.

    Exact sampler first (uniform over all HCP-consistent deals), falling back to
    the legacy steered generator if its rejection step produces nothing at all.
    Returns a list of layouts, shorter than `num_deals` only if the attempt
    budget ran out.
    """
    rng = rng if rng is not None else random
    sampler = build_sampler(known, hcp, suit_length, acceptors, quality)

    layouts = []
    use_exact = True
    attempts = 0
    max_attempts = num_deals * max_attempts_factor
    while len(layouts) < num_deals and attempts < max_attempts:
        attempts += 1
        if use_exact:
            hands = sampler.sample(rng)
            if hands is None and not layouts and attempts >= _EXACT_FALLBACK_ATTEMPTS:
                use_exact = False
        else:
            hands = generate_deal(known, hcp, suit_length, max_attempts=1000, rng=rng,
                                  acceptors=acceptors or None)
        if hands is None:
            continue
        layouts.append({p: hand_list_to_str(hands[p]) for p in DG_PLAYERS})
    return layouts
