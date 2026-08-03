"""The candidate contract set: 5 strains x {partscore, game, 6, 7} per declarer.

The pruning is a scoring argument, not a UI convenience (see
engine/contract/candidates.py), so pin it.
"""

import pytest

from engine.contract import candidates as cand


def test_twenty_contracts_per_declarer():
    one_seat = cand.enumerate_candidates(declarers=('S',))
    assert len(one_seat) == 20
    both = cand.enumerate_candidates(declarers=('S', 'N'))
    assert len(both) == 40
    assert len({c['key'] for c in both}) == 40      # keys are unique


def test_game_levels_are_bridge_correct():
    assert cand.GAME_LEVEL == {'N': 3, 'S': 4, 'H': 4, 'D': 5, 'C': 5}
    games = {c['strain']: c['level']
             for c in cand.enumerate_candidates(declarers=('S',))
             if c['kind'] == 'game'}
    assert games == {'N': 3, 'S': 4, 'H': 4, 'D': 5, 'C': 5}


def test_each_strain_has_the_four_decisions():
    by_strain = {}
    for c in cand.enumerate_candidates(declarers=('S',)):
        by_strain.setdefault(c['strain'], []).append(c['kind'])
    assert set(by_strain) == set('NSHDC')
    for kinds in by_strain.values():
        assert kinds == ['part', 'game', 'slam', 'grand']


def test_partscores_are_labelled_by_strain_not_level():
    labels = {c['key']: c['label'] for c in cand.enumerate_candidates(declarers=('S',))}
    assert labels['1S-S'] == '♠ partscore'
    assert labels['1N-S'] == 'NT partscore'
    assert labels['4S-S'] == '4♠'
    assert labels['3N-S'] == '3NT'
    assert labels['7N-S'] == '7NT'


def test_tricks_needed_matches_level():
    for c in cand.enumerate_candidates(declarers=('S',)):
        assert c['tricks_needed'] == 6 + c['level']


def test_strain_subset_and_bad_strain():
    subset = cand.enumerate_candidates(strains=['S', 'N'], declarers=('S',))
    assert {c['strain'] for c in subset} == {'S', 'N'}
    assert len(subset) == 8
    with pytest.raises(ValueError, match='unknown strain'):
        cand.enumerate_candidates(strains=['S', 'X'])
    with pytest.raises(ValueError, match='at least one strain'):
        cand.enumerate_candidates(strains=[])
