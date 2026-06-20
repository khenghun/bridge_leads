"""
Tests for engine.auctions — the predefined demo auctions.

Verifies each preset is well-formed (parses, feasible, valid HCP) and that the
1NT-3NT demo runs end-to-end through the simulator.
"""

import pytest

from engine.auctions import auction_names, get_auction, constraints, AUCTIONS
from engine.shape_parser import parse_shapes
from engine.shapes import feasibility_warnings
from engine.lead_simulator import simulate_opening_lead

LEADER = "AK872.Q95.J98.Q4"


def test_at_least_one_auction_registered():
    assert auction_names()
    assert '1NT (S) – 3NT (N)' in auction_names()


@pytest.mark.parametrize("name", list(AUCTIONS))
def test_preset_is_well_formed(name):
    a = get_auction(name)
    # contract parses to a level + strain via the same rules the app uses.
    assert a['contract'][:1] in '1234567'
    assert a['declarer'] in ('N', 'E', 'S', 'W')
    # HCP ranges sane.
    for seat, (lo, hi) in a['hcp'].items():
        assert 0 <= lo <= hi <= 40
    # Every shape text parses and every term can form 13 cards.
    for seat, text in a['shapes_text'].items():
        terms = parse_shapes(text)
        assert terms
        assert feasibility_warnings(terms) == []


def test_constraints_builds_engine_ready_dict():
    cons = constraints('1NT (S) – 3NT (N)')
    assert cons['hcp']['S'] == (15, 17)
    assert cons['hcp']['N'] == (10, 14)
    # South is the 5-term 1NT shape; North the 3-term raise.
    assert len(cons['shapes']['S']) == 5
    assert len(cons['shapes']['N']) == 3


def test_1nt_3nt_demo_runs_end_to_end():
    cons = constraints('1NT (S) – 3NT (N)')
    a = get_auction('1NT (S) – 3NT (N)')
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer=a['declarer'],
        constraints=cons, num_simulations=5, seed=3,
    )
    assert result['num_simulations'] == 5
    assert len(result['leads']) == 13
    assert result['best_mp'] is not None
