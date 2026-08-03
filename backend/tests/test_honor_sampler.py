"""
Tests for engine.honor_sampler.ExactDealSampler.

The sampler claims to draw uniformly from all deals consistent with known
cards + HCP bounds. Structural invariants are asserted exactly; uniformity is
smoke-checked against a shuffle-and-reject reference (exact by construction)
with generous tolerances and fixed seeds so the test is deterministic.
"""

import random
from collections import Counter

from engine.deal_generator import ALL_CARDS_SET, calculate_hcp
from engine.honor_sampler import ExactDealSampler
from engine.sampling import hand_to_cards

LEADER = hand_to_cards("AK872.Q95.J98.Q4")     # 12 HCP West hand
KNOWN = {'W': LEADER}


def test_structure_and_bounds():
    sampler = ExactDealSampler(KNOWN, {'S': (15, 17), 'N': (10, 14)})
    rng = random.Random(1)
    for _ in range(200):
        hands = sampler.sample(rng)
        assert hands is not None
        all_cards = [c for cards in hands.values() for c in cards]
        assert len(all_cards) == 52
        assert set(all_cards) == set(ALL_CARDS_SET)
        assert all(len(hands[p]) == 13 for p in 'NESW')
        assert hands['W'] == LEADER
        assert 15 <= calculate_hcp(hands['S']) <= 17
        assert 10 <= calculate_hcp(hands['N']) <= 14


def test_deterministic_with_seed():
    sampler = ExactDealSampler(KNOWN, {'S': (15, 17)})
    a = [sampler.sample(random.Random(42)) for _ in range(5)]
    b = [sampler.sample(random.Random(42)) for _ in range(5)]
    assert a == b


def test_infeasible_hcp_total_zero():
    # two seats demanding 25+ each can't fit in the deck's remaining honors
    sampler = ExactDealSampler(KNOWN, {'S': (25, 40), 'N': (25, 40)})
    assert sampler.total == 0
    assert sampler.sample(random.Random(0)) is None


def test_infeasible_max_below_fixed_cards():
    sampler = ExactDealSampler(
        {'W': LEADER, 'N': ['DA', 'CK']}, {'N': (0, 4)})
    assert sampler.total == 0


def test_fixed_cards_stay_fixed_and_count():
    sampler = ExactDealSampler(
        {'W': LEADER, 'N': ['DA', 'CK']}, {'N': (7, 10)})
    rng = random.Random(3)
    for _ in range(50):
        hands = sampler.sample(rng)
        assert 'DA' in hands['N'] and 'CK' in hands['N']
        assert 7 <= calculate_hcp(hands['N']) <= 10


def test_suit_bounds_rejected_in_sample():
    sampler = ExactDealSampler(
        KNOWN, {'S': (15, 17)}, {'S': {'H': (5, None)}})
    rng = random.Random(4)
    got = 0
    while got < 30:
        hands = sampler.sample(rng)
        if hands is None:
            continue
        got += 1
        assert sum(1 for c in hands['S'] if c[0] == 'H') >= 5


def test_no_constraints_still_uniform_deal():
    sampler = ExactDealSampler(KNOWN, {})
    hands = sampler.sample(random.Random(5))
    assert hands is not None
    assert all(len(hands[p]) == 13 for p in 'NESW')


def test_matches_shuffle_reject_reference():
    """HCP histogram must match exact rejection sampling (both are supposed
    to be uniform over the same set)."""
    N = 4000
    lo_s, hi_s = 15, 17

    sampler = ExactDealSampler(KNOWN, {'S': (lo_s, hi_s)})
    rng = random.Random(6)
    dp_hist = Counter()
    for _ in range(N):
        hands = sampler.sample(rng)
        dp_hist[calculate_hcp(hands['S'])] += 1

    rest = sorted(ALL_CARDS_SET - set(LEADER))
    rng = random.Random(7)
    ref_hist = Counter()
    got = 0
    while got < N:
        rng.shuffle(rest)
        h = calculate_hcp(rest[26:39])
        if lo_s <= h <= hi_s:
            ref_hist[h] += 1
            got += 1

    for hcp_val in range(lo_s, hi_s + 1):
        p_dp = dp_hist[hcp_val] / N
        p_ref = ref_hist[hcp_val] / N
        # ~2.5 sigma at N=4000 is ~0.02; use 0.03 to keep the test stable
        assert abs(p_dp - p_ref) < 0.03, (hcp_val, p_dp, p_ref)
