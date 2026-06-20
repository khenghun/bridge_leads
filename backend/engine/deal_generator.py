"""
Deal Generator — constrained random bridge deals.
Vendored from bridge_ai/solver/deal_generator_v2.py (optimized v2).

Generates a full 52-card deal where:
  - Known cards are pinned in their assigned hands
  - Remaining cards are distributed to satisfy per-player HCP and per-suit length bounds
Cards use endplay format: suit+rank (e.g. "SA", "H2"). Rank "T" = ten.
"""

import random

SUITS = ['S', 'H', 'D', 'C']
RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
HONORS = frozenset(['A', 'K', 'Q', 'J'])
ALL_CARDS = [s + r for s in SUITS for r in RANKS]
ALL_CARDS_SET = frozenset(ALL_CARDS)
PLAYERS = ['N', 'E', 'S', 'W']
HCP_VALUES = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}


def calculate_hcp(cards):
    """High card points for a list of cards (suit+rank format like "H2")."""
    return sum(HCP_VALUES.get(card[1], 0) for card in cards)


def generate_deal(known_hands, hcp_constraints, suit_constraints=None,
                  max_attempts=10000, debug=False, rng=None, acceptors=None):
    """
    Generate a bridge deal satisfying known cards, HCP, and suit-length constraints.

    Args:
        known_hands: dict player ('N'/'E'/'S'/'W') -> list of fixed cards.
        hcp_constraints: dict player -> (min_hcp, max_hcp); either bound may be None.
        suit_constraints: dict player -> {suit -> (min_len, max_len)}; either bound None.
        max_attempts: retries before giving up.
        debug: print diagnostic info.
        rng: a random.Random instance for reproducible/thread-safe generation;
             defaults to the global `random` module.
        acceptors: dict player -> predicate(cards)->bool, checked on the finished
             hand to support constraints the per-suit bounds can't express (e.g.
             disjunctive shapes). A deal is rejected unless every predicate passes.
             Pair with a covering `suit_constraints` envelope to keep generation
             efficient. None = no extra checks.

    Returns:
        dict player -> list of 13 cards, or None if no valid deal was found.
    """
    if rng is None:
        rng = random
    # === Precompute invariants ONCE before the loop ===
    base_hands = {p: list(known_hands.get(p, [])) for p in PLAYERS}

    all_known = set()
    for cards in base_hands.values():
        all_known.update(cards)
    base_remaining = ALL_CARDS_SET - all_known

    base_honors = [c for c in base_remaining if c[1] in HONORS]
    base_non_honors = [c for c in base_remaining if c[1] not in HONORS]

    non_honors_by_suit = {s: [] for s in SUITS}
    for c in base_non_honors:
        non_honors_by_suit[c[0]].append(c)

    static_cards_needed = {p: 13 - len(base_hands[p]) for p in PLAYERS}
    base_hcp = {p: calculate_hcp(base_hands[p]) for p in PLAYERS}

    base_suit_counts = {}
    for p in PLAYERS:
        counts = {s: 0 for s in SUITS}
        for c in base_hands[p]:
            counts[c[0]] += 1
        base_suit_counts[p] = counts

    if not hcp_constraints:
        hcp_constraints = {}
    constraint_bounds = {}
    for p in PLAYERS:
        hcp_c = hcp_constraints.get(p, (None, None))
        min_hcp = hcp_c[0] if hcp_c[0] is not None else 0
        max_hcp = hcp_c[1] if hcp_c[1] is not None else 40
        constraint_bounds[p] = (min_hcp, max_hcp)

    suit_max = {p: {s: 13 for s in SUITS} for p in PLAYERS}
    suit_min = {p: {s: 0 for s in SUITS} for p in PLAYERS}
    has_suit_constraints = False
    if suit_constraints:
        for p in PLAYERS:
            if p in suit_constraints:
                has_suit_constraints = True
                for suit, bounds in suit_constraints[p].items():
                    if bounds[0] is not None:
                        suit_min[p][suit] = bounds[0]
                    if bounds[1] is not None:
                        suit_max[p][suit] = bounds[1]

    # === Early validation: known cards must already satisfy constraints ===
    for p in PLAYERS:
        if base_hcp[p] > constraint_bounds[p][1]:
            if debug:
                print(f"DEBUG: {p} known cards already {base_hcp[p]} HCP > max {constraint_bounds[p][1]}")
            return None
        if has_suit_constraints:
            for s in SUITS:
                if base_suit_counts[p][s] > suit_max[p][s]:
                    if debug:
                        print(f"DEBUG: {p} known cards already {base_suit_counts[p][s]} {s} > max {suit_max[p][s]}")
                    return None

    for _ in range(max_attempts):
        honors = list(base_honors)
        rng.shuffle(honors)

        work_hands = {p: list(base_hands[p]) for p in PLAYERS}
        hcp = dict(base_hcp)
        cards_needed = dict(static_cards_needed)
        suit_counts = {p: dict(base_suit_counts[p]) for p in PLAYERS}

        # Distribute honors first, respecting max HCP AND max suit length
        success = True
        for card in honors:
            card_hcp = HCP_VALUES[card[1]]
            card_suit = card[0]
            possible = []
            for p in PLAYERS:
                if cards_needed[p] > 0:
                    if hcp[p] + card_hcp <= constraint_bounds[p][1]:
                        if suit_counts[p][card_suit] < suit_max[p][card_suit]:
                            possible.append(p)
            if not possible:
                success = False
                break
            p = rng.choice(possible)
            work_hands[p].append(card)
            hcp[p] += card_hcp
            cards_needed[p] -= 1
            suit_counts[p][card_suit] += 1

        if not success:
            continue

        hcp_valid = all(constraint_bounds[p][0] <= hcp[p] <= constraint_bounds[p][1]
                        for p in PLAYERS)
        if not hcp_valid:
            continue

        # === Distribute non-honors ===
        if has_suit_constraints:
            non_honor_pool = []
            for s in SUITS:
                available = list(non_honors_by_suit[s])
                rng.shuffle(available)
                eligible = [p for p in PLAYERS
                            if cards_needed[p] > 0 and suit_counts[p][s] < suit_max[p][s]]
                for card in available:
                    eligible = [p for p in eligible
                                if cards_needed[p] > 0 and suit_counts[p][s] < suit_max[p][s]]
                    if eligible:
                        p = rng.choice(eligible)
                        work_hands[p].append(card)
                        cards_needed[p] -= 1
                        suit_counts[p][s] += 1
                    else:
                        non_honor_pool.append(card)
            if non_honor_pool:
                rng.shuffle(non_honor_pool)
                for card in non_honor_pool:
                    card_suit = card[0]
                    candidates = [p for p in PLAYERS
                                  if cards_needed[p] > 0 and suit_counts[p][card_suit] < suit_max[p][card_suit]]
                    if candidates:
                        p = rng.choice(candidates)
                        work_hands[p].append(card)
                        cards_needed[p] -= 1
                        suit_counts[p][card_suit] += 1
        else:
            non_honors = list(base_non_honors)
            rng.shuffle(non_honors)
            idx = 0
            for p in PLAYERS:
                take = cards_needed[p]
                if take > 0:
                    for c in non_honors[idx:idx + take]:
                        suit_counts[p][c[0]] += 1
                    work_hands[p].extend(non_honors[idx:idx + take])
                    idx += take

        if not all(len(work_hands[p]) == 13 for p in PLAYERS):
            continue

        if has_suit_constraints:
            all_valid = True
            for p in PLAYERS:
                if not all_valid:
                    break
                for s in SUITS:
                    if suit_counts[p][s] < suit_min[p][s]:
                        all_valid = False
                        break
            if not all_valid:
                continue

        if acceptors:
            if not all(pred(work_hands[p]) for p, pred in acceptors.items()):
                continue

        return work_hands

    if debug:
        print(f"DEBUG: Failed after {max_attempts} attempts")
    return None
