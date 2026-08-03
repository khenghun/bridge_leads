"""Suit-quality constraint: the predicate, the sampler's DP, and the API edge.

The DP tests matter most. `ExactDealSampler` splits its honor classes by the
constrained suit and pulls that suit's ten out of the spot pool, so a mistake
there would not raise — it would silently skew every deal the app simulates.
The exactness tests below pin `.total` against brute-force enumeration.
"""

import itertools
import random
from collections import Counter

import pytest

from engine import suit_quality as sq
from engine.deal_generator import ALL_CARDS_SET, calculate_hcp
from engine.honor_sampler import ExactDealSampler
from engine.sampling import (
    build_known_and_constraints as _build_known_and_constraints, hand_to_cards,
)

PLAYERS = ['N', 'E', 'S', 'W']
LEADER = 'AK8.Q95.J982.Q43'


# --------------------------------------------------------------- predicate --

@pytest.mark.parametrize('holding, good', [
    ('AK', True),        # 2 of the top 3
    ('AQ', True),
    ('KQ', True),
    ('AKQ', True),
    ('AKQJT', True),
    ('QJT', True),       # 3 of the top 5, only one of the top 3
    ('AJT', True),
    ('KJT', True),
    ('JT', False),       # 2 of the top 5 is not enough
    ('A', False),
    ('AJ', False),       # one of the top 3 + one filler
    ('KT', False),
    ('QJ', False),
    ('', False),
    ('98765', False),    # length is not quality
    ('AJ98765', False),
])
def test_good_suit_definition(holding, good):
    cards = ['S' + r for r in holding]
    top3, jt = sq.counts(cards, 'S')
    assert sq.is_good(top3, jt) is good
    assert sq.satisfies('good', top3, jt) is good
    assert sq.satisfies('poor', top3, jt) is (not good)


def test_counts_ignores_other_suits():
    cards = ['SA', 'SK', 'HA', 'HK', 'HQ', 'DT', 'CJ']
    assert sq.counts(cards, 'S') == (2, 0)
    assert sq.counts(cards, 'H') == (3, 0)
    assert sq.counts(cards, 'D') == (0, 1)
    assert sq.counts(cards, 'C') == (0, 1)


def test_predicate_matches_counts():
    pred = sq.predicate('H', 'good')
    assert pred(['HQ', 'HJ', 'HT', 'S2'])
    assert not pred(['HA', 'HJ', 'S2'])


def test_min_length():
    # 'good' is reachable with two cards (KQ); 'poor' constrains nothing.
    assert sq.min_length('good') == 2
    assert sq.min_length('poor') == 0


# ------------------------------------------------------ sampler exactness --

def _brute_force(known, hcp, quality):
    """Enumerate every legal completion; returns the list of deals."""
    pool = sorted(ALL_CARDS_SET - {c for cs in known.values() for c in cs})
    caps = {p: 13 - len(known[p]) for p in PLAYERS}
    seats = [p for p in PLAYERS if caps[p] > 0]
    out = []
    for assign in itertools.product(range(len(seats)), repeat=len(pool)):
        counts = Counter(assign)
        if any(counts[i] != caps[seats[i]] for i in range(len(seats))):
            continue
        hands = {p: list(known[p]) for p in PLAYERS}
        for card, si in zip(pool, assign):
            hands[seats[si]].append(card)
        ok = True
        for p, (lo, hi) in (hcp or {}).items():
            h = calculate_hcp(hands[p])
            if (lo is not None and h < lo) or (hi is not None and h > hi):
                ok = False
                break
        if ok and quality:
            qp, qs, level = quality
            ok = sq.satisfies(level, *sq.counts(hands[qp], qs))
        if ok:
            out.append(hands)
    return out


def _fixed_position(free):
    """Deal everything except `free` to the four seats (W full, then N/E/S)."""
    rest = [c for c in sorted(ALL_CARDS_SET) if c not in free]
    return {'W': rest[:13], 'N': rest[13:23], 'E': rest[23:33], 'S': rest[33:43]}


# The constrained suit's ten sits in the free pool on purpose: it is an
# ordinary spot card to the rest of the engine, and the sampler has to move it
# into an honor class without breaking the spot-pool multinomial.
POOL = ['SA', 'SK', 'SQ', 'SJ', 'ST', 'H2', 'H3', 'D2', 'D3']


@pytest.mark.parametrize('quality', [
    None,
    ('N', 'S', 'good'),
    ('N', 'S', 'poor'),
    ('S', 'S', 'good'),
    ('E', 'S', 'poor'),
])
def test_sampler_total_is_exact(quality):
    known = _fixed_position(POOL)
    sampler = ExactDealSampler(known, None, None, None, quality)
    assert sampler.total == len(_brute_force(known, None, quality))


def test_good_and_poor_partition_the_space():
    """Since 'poor' is the complement of 'good', the two counts must sum to the
    unconstrained total — a sharp check on both terminal filters."""
    known = _fixed_position(POOL)
    total = ExactDealSampler(known, None, None, None, None).total
    good = ExactDealSampler(known, None, None, None, ('N', 'S', 'good')).total
    poor = ExactDealSampler(known, None, None, None, ('N', 'S', 'poor')).total
    assert good and poor
    assert good + poor == total


def test_sampler_total_is_exact_with_hcp():
    known = _fixed_position(POOL)
    hcp = {'N': (5, 40)}
    quality = ('N', 'S', 'good')
    sampler = ExactDealSampler(known, hcp, None, None, quality)
    assert sampler.total == len(_brute_force(known, hcp, quality))


def test_samples_are_uniform_over_the_constrained_space():
    """Sampled frequencies must track the exact per-outcome counts; a biased
    materialisation would show up here even though `.total` was right."""
    known = _fixed_position(POOL)
    quality = ('N', 'S', 'good')
    sampler = ExactDealSampler(known, None, None, None, quality)
    exact = _brute_force(known, None, quality)

    want = Counter(tuple(sorted(d['N'])) for d in exact)
    draws = 60000
    rng = random.Random(11)
    seen = Counter()
    for _ in range(draws):
        hands = sampler.sample(rng)
        assert hands is not None
        seen[tuple(sorted(hands['N']))] += 1

    assert not set(seen) - set(want), "sampled an outcome outside the exact set"
    assert len(seen) == len(want), "some legal outcome was never sampled"
    for key, w in want.items():
        expect = draws * w / sum(want.values())
        assert abs(seen[key] - expect) < 0.25 * expect


def test_every_sampled_deal_satisfies_the_constraint():
    known = {'W': hand_to_cards(LEADER)}
    quality = ('N', 'H', 'good')
    sampler = ExactDealSampler(known, {'N': (6, 11)}, {'N': {'H': (6, 6)}},
                               None, quality)
    assert sampler.total > 0
    rng = random.Random(5)
    seen = 0
    for _ in range(400):
        hands = sampler.sample(rng)
        if hands is None:
            continue
        seen += 1
        assert sq.satisfies('good', *sq.counts(hands['N'], 'H'))
        assert sum(1 for c in hands['N'] if c[0] == 'H') == 6
        assert 6 <= calculate_hcp(hands['N']) <= 11
    assert seen > 50, "constraint starved the sampler"


def test_quality_is_infeasible_when_the_leader_holds_the_honours():
    """Leader holds AKQJT of spades, so no other seat can have a good spade
    suit — the DP must report that exactly rather than starving."""
    known = {'W': hand_to_cards('AKQJT.95.982.Q43')}
    sampler = ExactDealSampler(known, None, None, None, ('N', 'S', 'good'))
    assert sampler.total == 0


def test_quality_and_hcp_prune_each_other():
    """The cheapest good holding is QJT (3 HCP) — the top-5 arm is what makes
    it that cheap — so a seat capped at 2 HCP is infeasible. The DP sees this
    because quality is dealt inside it, not checked afterwards."""
    known = {'W': hand_to_cards(LEADER)}
    assert ExactDealSampler(known, {'N': (0, 2)}, None, None,
                            ('N', 'S', 'good')).total == 0
    # 3 HCP is enough, and only via QJT: the leader holds SA and SK here.
    assert ExactDealSampler(known, {'N': (3, 3)}, None, None,
                            ('N', 'S', 'good')).total > 0


# ------------------------------------------------- constraint plumbing -----

def _build(constraints, leader='W'):
    return _build_known_and_constraints(leader, hand_to_cards(LEADER),
                                        constraints)


def test_build_resolves_quality_and_tightens_length():
    _k, _h, suit_length, acceptors, quality = _build(
        {'quality': {'N': {'H': 'good'}}})
    assert quality == ('N', 'H', 'good')
    assert suit_length['N']['H'][0] == 2       # 'good' implies 2+ cards
    assert 'N' in acceptors                    # predicate for the fallback path


def test_build_keeps_a_tighter_user_length():
    _k, _h, suit_length, _a, _q = _build({
        'suit_length': {'N': {'H': (6, 6)}},
        'quality': {'N': {'H': 'good'}},
    })
    assert suit_length['N']['H'] == (6, 6)


def test_poor_does_not_tighten_length():
    _k, _h, suit_length, _a, _q = _build({'quality': {'N': {'H': 'poor'}}})
    assert suit_length.get('N', {}).get('H', (0, 13))[0] == 0


def test_shape_and_quality_acceptors_compose():
    """Both land on the same seat; ANDing them is what keeps the shape alive."""
    five_hearts = [{'H': (5, 5), 'S': (2, 4), 'D': (2, 4), 'C': (2, 4)}]
    _k, _h, _sl, acceptors, _q = _build({
        'shapes': {'N': five_hearts},
        'quality': {'N': {'H': 'good'}},
    })
    pred = acceptors['N']
    good_shape = (['H' + r for r in 'AK432'] + ['S2', 'S3', 'S4']
                  + ['D2', 'D3', 'D4'] + ['C2', 'C3'])
    assert pred(good_shape)
    # right shape, ragged suit -> rejected by the quality half
    ragged = (['H' + r for r in 'J8765'] + ['S2', 'S3', 'S4']
              + ['D2', 'D3', 'D4'] + ['C2', 'C3'])
    assert not pred(ragged)
    # right suit, wrong shape -> rejected by the shape half
    wrong_shape = (['H' + r for r in 'AK4321'] + ['S2', 'S3', 'S4']
                   + ['D2', 'D3'] + ['C2', 'C3'])
    assert not pred(wrong_shape)


def test_only_one_quality_constraint_allowed():
    with pytest.raises(ValueError, match='[Oo]nly one suit-quality'):
        _build({'quality': {'N': {'H': 'good'}, 'E': {'S': 'good'}}})
    with pytest.raises(ValueError, match='[Oo]nly one suit-quality'):
        _build({'quality': {'N': {'H': 'good', 'S': 'poor'}}})


def test_quality_rejects_the_leader_and_bad_values():
    # 'W' is the own seat here (the opening leader, in the lead app's terms).
    with pytest.raises(ValueError, match='not your own hand'):
        _build({'quality': {'W': {'H': 'good'}}})
    with pytest.raises(ValueError, match='suit quality must be'):
        _build({'quality': {'N': {'H': 'solid'}}})
    with pytest.raises(ValueError, match='unknown suit'):
        _build({'quality': {'N': {'X': 'good'}}})


def test_empty_quality_is_no_constraint():
    _k, _h, _sl, acceptors, quality = _build({'quality': {'N': {}}})
    assert quality is None
    assert not acceptors
