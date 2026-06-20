"""
Regression tests for engine.deal_generator.

The generator is randomised, so most tests seed `random` and/or assert the
*invariants* that must hold for every deal it returns (full 52-card partition,
pinned known cards, HCP/suit bounds). Where a property must hold universally we
generate many deals in a loop to make a violation overwhelmingly likely to show.
"""

import random

import pytest

from engine.deal_generator import (
    generate_deal,
    calculate_hcp,
    PLAYERS,
    SUITS,
    RANKS,
    ALL_CARDS,
    ALL_CARDS_SET,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def assert_valid_full_deal(hands):
    """Every returned deal must be a clean partition of the 52-card deck."""
    assert set(hands) == set(PLAYERS)
    for p in PLAYERS:
        assert len(hands[p]) == 13, f"{p} has {len(hands[p])} cards"
    all_cards = [c for p in PLAYERS for c in hands[p]]
    assert len(all_cards) == 52
    assert len(set(all_cards)) == 52, "duplicate card across hands"
    assert set(all_cards) == ALL_CARDS_SET, "not a full deck"
    # each suit fully accounted for
    for s in SUITS:
        assert sum(1 for c in all_cards if c[0] == s) == 13


def suit_count(cards, suit):
    return sum(1 for c in cards if c[0] == suit)


# --------------------------------------------------------------------------
# calculate_hcp
# --------------------------------------------------------------------------
def test_calculate_hcp_basic():
    assert calculate_hcp([]) == 0
    assert calculate_hcp(['SA']) == 4
    assert calculate_hcp(['SA', 'HK', 'DQ', 'CJ']) == 4 + 3 + 2 + 1
    assert calculate_hcp(['S2', 'H3', 'DT', 'C9']) == 0  # spot cards, T has no HCP


def test_full_deck_is_40_hcp():
    assert calculate_hcp(ALL_CARDS) == 40
    assert len(ALL_CARDS) == 52


# --------------------------------------------------------------------------
# unconstrained generation
# --------------------------------------------------------------------------
def test_unconstrained_deal_is_valid():
    random.seed(0)
    for _ in range(50):
        hands = generate_deal({}, {})
        assert hands is not None
        assert_valid_full_deal(hands)
        # HCP across the deal always sums to 40
        assert sum(calculate_hcp(hands[p]) for p in PLAYERS) == 40


# --------------------------------------------------------------------------
# acceptors (post-build predicates, e.g. disjunctive shapes)
# --------------------------------------------------------------------------
def test_acceptor_filters_generated_hands():
    # Require North to hold at least 6 spades. Pair with a covering envelope so
    # generation stays efficient (matches how lead_simulator wires shapes).
    rng = random.Random(0)
    acc = {'N': lambda cards: suit_count(cards, 'S') >= 6}
    produced = 0
    for _ in range(30):
        hands = generate_deal(
            {}, {}, suit_constraints={'N': {'S': (6, 13)}},
            rng=rng, acceptors=acc)
        if hands is None:
            continue
        produced += 1
        assert_valid_full_deal(hands)
        assert suit_count(hands['N'], 'S') >= 6
    assert produced > 0, "acceptor rejected every deal"


def test_acceptor_none_is_unchanged_behaviour():
    # acceptors=None must behave exactly like the default path.
    rng = random.Random(42)
    hands = generate_deal({}, {}, rng=rng, acceptors=None)
    assert hands is not None
    assert_valid_full_deal(hands)


def test_acceptor_impossible_returns_none():
    # No hand can satisfy an always-false predicate -> None after max_attempts.
    rng = random.Random(1)
    hands = generate_deal({}, {}, rng=rng, max_attempts=50,
                          acceptors={'N': lambda cards: False})
    assert hands is None


def test_generation_is_deterministic_under_seed():
    random.seed(1234)
    first = generate_deal({}, {})
    random.seed(1234)
    second = generate_deal({}, {})
    assert first == second


def test_injected_rng_is_reproducible_and_isolated():
    # Two private RNGs with the same seed must yield identical deals, without
    # touching the global random state (thread-safe seeding).
    random.seed(999)
    global_before = random.random()
    a = generate_deal({}, {}, rng=random.Random(42))
    b = generate_deal({}, {}, rng=random.Random(42))
    assert a == b
    random.seed(999)
    assert random.random() == global_before  # global stream untouched by rng=


# --------------------------------------------------------------------------
# known (pinned) cards
# --------------------------------------------------------------------------
def test_known_cards_are_pinned():
    random.seed(7)
    known = {'N': ['SA', 'SK', 'SQ'], 'S': ['HA', 'HK']}
    for _ in range(30):
        hands = generate_deal(known, {})
        assert hands is not None
        assert_valid_full_deal(hands)
        for c in known['N']:
            assert c in hands['N']
        for c in known['S']:
            assert c in hands['S']


def test_known_cards_not_duplicated_elsewhere():
    random.seed(8)
    known = {'E': ['CA', 'CK', 'CQ', 'CJ']}
    hands = generate_deal(known, {})
    assert hands is not None
    others = [c for p in PLAYERS if p != 'E' for c in hands[p]]
    for c in known['E']:
        assert c not in others


# --------------------------------------------------------------------------
# HCP constraints
# --------------------------------------------------------------------------
def test_hcp_constraint_respected():
    random.seed(42)
    hcp = {'N': (15, 17)}
    for _ in range(40):
        hands = generate_deal({}, hcp)
        assert hands is not None
        assert 15 <= calculate_hcp(hands['N']) <= 17


def test_hcp_constraints_multiple_seats():
    random.seed(99)
    hcp = {'N': (20, 21), 'S': (0, 3)}
    for _ in range(40):
        hands = generate_deal({}, hcp)
        assert hands is not None
        assert 20 <= calculate_hcp(hands['N']) <= 21
        assert calculate_hcp(hands['S']) <= 3


def test_hcp_none_bounds_are_unbounded():
    random.seed(3)
    # min None -> 0, max None -> 40; should always succeed
    hands = generate_deal({}, {'N': (None, None)})
    assert hands is not None
    assert_valid_full_deal(hands)


# --------------------------------------------------------------------------
# suit-length constraints
# --------------------------------------------------------------------------
def test_exact_suit_length():
    random.seed(11)
    suit = {'N': {'S': (5, 5)}}
    for _ in range(40):
        hands = generate_deal({}, {}, suit)
        assert hands is not None
        assert suit_count(hands['N'], 'S') == 5


def test_suit_length_min_and_max():
    random.seed(21)
    suit = {'E': {'H': (4, 6)}, 'W': {'C': (0, 1)}}
    for _ in range(40):
        hands = generate_deal({}, {}, suit)
        assert hands is not None
        assert 4 <= suit_count(hands['E'], 'H') <= 6
        assert suit_count(hands['W'], 'C') <= 1


def test_combined_hcp_and_suit_constraints():
    random.seed(55)
    hcp = {'N': (12, 14)}
    suit = {'N': {'S': (5, 5), 'H': (3, 5)}}
    for _ in range(40):
        hands = generate_deal({}, hcp, suit)
        assert hands is not None
        assert 12 <= calculate_hcp(hands['N']) <= 14
        assert suit_count(hands['N'], 'S') == 5
        assert 3 <= suit_count(hands['N'], 'H') <= 5


def test_known_cards_plus_constraints():
    random.seed(77)
    known = {'N': ['SA', 'SK', 'SQ', 'SJ', 'ST']}  # 5 spades incl. AKQJ = 10 HCP
    hcp = {'N': (10, 15)}
    suit = {'N': {'S': (5, 5)}}
    for _ in range(30):
        hands = generate_deal(known, hcp, suit)
        assert hands is not None
        for c in known['N']:
            assert c in hands['N']
        assert suit_count(hands['N'], 'S') == 5
        assert 10 <= calculate_hcp(hands['N']) <= 15


# --------------------------------------------------------------------------
# impossible constraints -> None
# --------------------------------------------------------------------------
def test_known_cards_exceed_max_hcp_returns_none():
    # N already holds 22 HCP but is capped at 20.
    known = {'N': ['SA', 'HA', 'DA', 'CA', 'SK', 'HK']}
    assert calculate_hcp(known['N']) == 22
    assert generate_deal(known, {'N': (0, 20)}) is None


def test_known_suit_exceeds_max_returns_none():
    # N already holds 6 spades but is capped at 5.
    known = {'N': ['SA', 'SK', 'SQ', 'SJ', 'ST', 'S9']}
    assert generate_deal(known, {}, {'N': {'S': (0, 5)}}) is None


def test_impossible_suit_minimums_returns_none():
    # Every seat demanding >=4 spades needs 16 spades; only 13 exist.
    suit = {p: {'S': (4, 13)} for p in PLAYERS}
    assert generate_deal({}, {}, suit, max_attempts=200) is None


def test_impossible_total_hcp_returns_none():
    # Two seats demanding >=25 HCP each needs >=50; the deck holds 40.
    hcp = {'N': (25, 40), 'S': (25, 40)}
    assert generate_deal({}, hcp, max_attempts=200) is None
