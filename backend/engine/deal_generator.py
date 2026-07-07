"""
Deal Generator — constrained random bridge deals.
Vendored from bridge_ai/solver/deal_generator_v2.py (optimized v2).

Generates a full 52-card deal where:
  - Known cards are pinned in their assigned hands
  - Remaining cards are distributed to satisfy per-player HCP and per-suit length bounds
Cards use endplay format: suit+rank (e.g. "SA", "H2"). Rank "T" = ten.

Sampling model: each attempt places honors one at a time, choosing uniformly
among the players that can still take the card (capacity, max HCP, max suit
length), then deals non-honors the same way and rejects the finished deal
unless every minimum holds. That is plain rejection sampling, and tight
minimums (e.g. a 15-17 HCP seat) reject >95% of attempts, so the hot loop is
tuned for cheap failure:

  - attempts abort as soon as they are *provably* doomed (the honors still to
    come can no longer cover the remaining HCP minimums, or a player has more
    unmet minimums than free card slots). Doom checks are necessary
    conditions for success and run only AFTER the uniform random choice, so
    the distribution of accepted deals is exactly the same as running every
    attempt to completion — doomed attempts just fail early;
  - per-attempt state is flat integer lists indexed by player/suit number
    (not nested dicts), and hands are only materialised for attempts that
    survive the honor phase.
"""

import random

SUITS = ['S', 'H', 'D', 'C']
RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
HONORS = frozenset(['A', 'K', 'Q', 'J'])
ALL_CARDS = [s + r for s in SUITS for r in RANKS]
ALL_CARDS_SET = frozenset(ALL_CARDS)
PLAYERS = ['N', 'E', 'S', 'W']
HCP_VALUES = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}

_SUIT_IDX = {s: i for i, s in enumerate(SUITS)}
_P4 = (0, 1, 2, 3)


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
    # Players and suits are flat indices (PLAYERS / SUITS order) in the hot
    # loop; per-(player,suit) tables are 16-slot lists indexed p*4+s.
    base_hands = {p: list(known_hands.get(p, [])) for p in PLAYERS}

    all_known = set()
    for cards in base_hands.values():
        all_known.update(cards)
    base_remaining = ALL_CARDS_SET - all_known

    # (card, hcp value, suit index) so the hot loop avoids dict lookups
    base_honor_items = [(c, HCP_VALUES[c[1]], _SUIT_IDX[c[0]])
                        for c in base_remaining if c[1] in HONORS]
    base_non_honors = [c for c in base_remaining if c[1] not in HONORS]

    non_honors_by_suit = [[] for _ in SUITS]
    for c in base_non_honors:
        non_honors_by_suit[_SUIT_IDX[c[0]]].append(c)

    base_needed = [13 - len(base_hands[p]) for p in PLAYERS]
    base_hcp = [calculate_hcp(base_hands[p]) for p in PLAYERS]

    base_suit_counts = [0] * 16
    for pi, p in enumerate(PLAYERS):
        for c in base_hands[p]:
            base_suit_counts[pi * 4 + _SUIT_IDX[c[0]]] += 1

    if not hcp_constraints:
        hcp_constraints = {}
    min_hcp = [0] * 4
    max_hcp = [40] * 4
    for pi, p in enumerate(PLAYERS):
        hcp_c = hcp_constraints.get(p, (None, None))
        if hcp_c[0] is not None:
            min_hcp[pi] = hcp_c[0]
        if hcp_c[1] is not None:
            max_hcp[pi] = hcp_c[1]

    suit_min = [0] * 16
    suit_max = [13] * 16
    has_suit_constraints = False
    if suit_constraints:
        for pi, p in enumerate(PLAYERS):
            if p in suit_constraints:
                has_suit_constraints = True
                for suit, bounds in suit_constraints[p].items():
                    si = _SUIT_IDX[suit]
                    if bounds[0] is not None:
                        suit_min[pi * 4 + si] = bounds[0]
                    if bounds[1] is not None:
                        suit_max[pi * 4 + si] = bounds[1]

    # === Early validation: known cards must already satisfy constraints ===
    for pi, p in enumerate(PLAYERS):
        if base_hcp[pi] > max_hcp[pi]:
            if debug:
                print(f"DEBUG: {p} known cards already {base_hcp[pi]} HCP > max {max_hcp[pi]}")
            return None
        if has_suit_constraints:
            for si, s in enumerate(SUITS):
                if base_suit_counts[pi * 4 + si] > suit_max[pi * 4 + si]:
                    if debug:
                        print(f"DEBUG: {p} known cards already "
                              f"{base_suit_counts[pi * 4 + si]} {s} > max {suit_max[pi * 4 + si]}")
                    return None

    # === Doom-check invariants ===
    # deficit: HCP each player still needs to reach its minimum; only honors
    # still to be placed can reduce it. suit_need: cards each player still
    # needs to fill its per-suit minimums.
    total_honor_points = sum(v for _, v, _ in base_honor_items)
    base_deficit = [max(0, min_hcp[pi] - base_hcp[pi]) for pi in _P4]
    base_total_deficit = sum(base_deficit)
    base_suit_need = [
        sum(max(0, suit_min[pi * 4 + si] - base_suit_counts[pi * 4 + si])
            for si in range(4))
        for pi in _P4
    ]
    if base_total_deficit > total_honor_points:
        if debug:
            print(f"DEBUG: HCP minimums need {base_total_deficit} more points "
                  f"but only {total_honor_points} remain")
        return None
    for pi, p in enumerate(PLAYERS):
        if base_deficit[pi] > 4 * base_needed[pi]:
            if debug:
                print(f"DEBUG: {p} needs {base_deficit[pi]} HCP in {base_needed[pi]} cards")
            return None
        if base_suit_need[pi] > base_needed[pi]:
            if debug:
                print(f"DEBUG: {p} suit minimums need {base_suit_need[pi]} cards, "
                      f"has room for {base_needed[pi]}")
            return None

    # per-suit: the unseen cards of each suit must cover every seat's unmet
    # minimum, or no attempt can ever succeed
    if has_suit_constraints:
        unseen_per_suit = [len(non_honors_by_suit[si]) for si in range(4)]
        for _, _, si in base_honor_items:
            unseen_per_suit[si] += 1
        for si, s in enumerate(SUITS):
            needed = sum(max(0, suit_min[pi * 4 + si] - base_suit_counts[pi * 4 + si])
                         for pi in _P4)
            if needed > unseen_per_suit[si]:
                if debug:
                    print(f"DEBUG: {s} minimums need {needed} cards, only "
                          f"{unseen_per_suit[si]} unseen")
                return None

    honors = list(base_honor_items)
    n_honors = len(honors)
    rand = rng.random           # float draws: ~4x cheaper than choice/randrange
    shuffle = rng.shuffle

    for _ in range(max_attempts):
        hcp = list(base_hcp)
        needed = list(base_needed)
        counts = list(base_suit_counts)
        deficit = list(base_deficit)
        total_deficit = base_total_deficit
        suit_need = list(base_suit_need)
        rem_points = total_honor_points
        placements = []      # (card, player idx); hands built only on success

        # Distribute honors: uniform choice among players with room (capacity,
        # max HCP, max suit length) — identical to plain rejection sampling —
        # then abort the attempt if the placement made success impossible.
        # Honors are drawn by incremental Fisher-Yates (same distribution as
        # shuffling up front) so an attempt that dies after 4 placements pays
        # for 4 draws, not 16.
        success = True
        for i in range(n_honors):
            j = i + int(rand() * (n_honors - i))
            honors[i], honors[j] = honors[j], honors[i]
            card, v, si = honors[i]
            possible = [pi for pi in _P4
                        if needed[pi] > 0
                        and hcp[pi] + v <= max_hcp[pi]
                        and counts[pi * 4 + si] < suit_max[pi * 4 + si]]
            if not possible:
                success = False
                break
            pi = possible[0] if len(possible) == 1 else possible[int(rand() * len(possible))]
            placements.append((card, pi))
            hcp[pi] += v
            needed[pi] -= 1
            ci = pi * 4 + si
            if counts[ci] < suit_min[ci]:
                suit_need[pi] -= 1
            counts[ci] += 1
            rem_points -= v
            d = deficit[pi]
            if d:
                cut = v if v <= d else d
                deficit[pi] = d - cut
                total_deficit -= cut
            # doom checks (necessary conditions; do not affect distribution)
            if (total_deficit > rem_points          # minimums out of reach
                    or deficit[pi] > 4 * needed[pi]  # p can't fit missing HCP
                    or suit_need[pi] > needed[pi]):  # p can't fill suit minimums
                success = False
                break

        if not success:
            continue

        # rem_points == 0 here, so total_deficit == 0: minimums are met.
        # Keep the explicit check as a cheap safety net.
        if not all(min_hcp[pi] <= hcp[pi] <= max_hcp[pi] for pi in _P4):
            continue

        work_hands = [list(base_hands[p]) for p in PLAYERS]
        for card, pi in placements:
            work_hands[pi].append(card)

        # === Distribute non-honors ===
        if has_suit_constraints:
            failed = False
            non_honor_pool = []
            for si in range(4):
                available = list(non_honors_by_suit[si])
                # remaining cards of this suit must cover the unmet minimums
                unmet = sum(max(0, suit_min[pi * 4 + si] - counts[pi * 4 + si])
                            for pi in _P4)
                if unmet > len(available):
                    failed = True
                    break
                shuffle(available)
                eligible = [pi for pi in _P4
                            if needed[pi] > 0 and counts[pi * 4 + si] < suit_max[pi * 4 + si]]
                for card in available:
                    eligible = [pi for pi in eligible
                                if needed[pi] > 0 and counts[pi * 4 + si] < suit_max[pi * 4 + si]]
                    if eligible:
                        pi = eligible[0] if len(eligible) == 1 else eligible[int(rand() * len(eligible))]
                        work_hands[pi].append(card)
                        needed[pi] -= 1
                        ci = pi * 4 + si
                        if counts[ci] < suit_min[ci]:
                            unmet -= 1
                            suit_need[pi] -= 1
                        counts[ci] += 1
                        if suit_need[pi] > needed[pi]:
                            failed = True     # p can't fill its minimums now
                            break
                    else:
                        non_honor_pool.append(card)
                if failed:
                    break
                if unmet:
                    failed = True   # suit exhausted with a minimum unmet
                    break
            if failed:
                continue
            if non_honor_pool:
                shuffle(non_honor_pool)
                for card in non_honor_pool:
                    si = _SUIT_IDX[card[0]]
                    candidates = [pi for pi in _P4
                                  if needed[pi] > 0 and counts[pi * 4 + si] < suit_max[pi * 4 + si]]
                    if candidates:
                        pi = candidates[int(rand() * len(candidates))]
                        work_hands[pi].append(card)
                        needed[pi] -= 1
                        counts[pi * 4 + si] += 1
        else:
            non_honors = list(base_non_honors)
            shuffle(non_honors)
            idx = 0
            for pi in _P4:
                take = needed[pi]
                if take > 0:
                    work_hands[pi].extend(non_honors[idx:idx + take])
                    idx += take

        if not all(len(work_hands[pi]) == 13 for pi in _P4):
            continue

        result = {p: work_hands[pi] for pi, p in enumerate(PLAYERS)}
        if acceptors:
            if not all(pred(result[p]) for p, pred in acceptors.items()):
                continue

        return result

    if debug:
        print(f"DEBUG: Failed after {max_attempts} attempts")
    return None
