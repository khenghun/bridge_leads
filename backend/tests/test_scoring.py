"""
Regression tests for engine.scoring.

These are fully deterministic: the IMP scale and the MP/IMP aggregation are pure
Python, and declarer scores come from endplay (the score oracle) for well-known
duplicate-bridge results.
"""

import pytest

from engine.scoring import imps, declarer_score, aggregate


# --------------------------------------------------------------------------
# imps() — standard IMP scale
# --------------------------------------------------------------------------
@pytest.mark.parametrize("diff,expected", [
    (0, 0),
    (19, 0),     # below first threshold (20)
    (20, 1),
    (49, 1),
    (50, 2),
    (250, 6),
    (429, 9),
    (430, 10),
    (4000, 24),  # top of the scale
    (5000, 24),  # clamps at the maximum
])
def test_imps_scale(diff, expected):
    assert imps(diff) == expected


def test_imps_is_antisymmetric():
    for d in (20, 50, 250, 430, 1000):
        assert imps(-d) == -imps(d)


# --------------------------------------------------------------------------
# declarer_score() — pinned against endplay's score oracle
# --------------------------------------------------------------------------
@pytest.mark.parametrize("args,expected", [
    ((3, 'N', 'S', 9, 'none', 'none'), 400),    # 3NT making, non-vul
    ((3, 'N', 'S', 9, 'both', 'none'), 600),     # 3NT making, vul
    ((4, 'S', 'S', 10, 'none', 'none'), 420),    # 4S making, non-vul
    ((1, 'N', 'S', 7, 'none', 'none'), 90),      # 1NT making
    ((2, 'C', 'S', 8, 'none', 'none'), 90),      # 2C making
    ((3, 'N', 'S', 8, 'none', 'none'), -50),     # 3NT down 1, non-vul
    ((3, 'N', 'S', 8, 'none', 'doubled'), -100),  # 3NT down 1 doubled
    ((7, 'N', 'S', 13, 'both', 'none'), 2220),   # 7NT making, vul
])
def test_declarer_score_known_results(args, expected):
    assert declarer_score(*args) == expected


def test_overtricks_increase_score():
    base = declarer_score(3, 'N', 'S', 9, 'none', 'none')      # exactly making
    over = declarer_score(3, 'N', 'S', 10, 'none', 'none')     # +1 overtrick
    assert over > base


def test_strain_argument_is_case_insensitive():
    assert (declarer_score(3, 'n', 'S', 9, 'none', 'none')
            == declarer_score(3, 'N', 'S', 9, 'none', 'none'))


# --------------------------------------------------------------------------
# aggregate() — matchpoints
# --------------------------------------------------------------------------
def test_matchpoints_clear_winner():
    # A beats B on every deal -> A=100%, B=0%.
    scores = {'A': [100, 100], 'B': [50, 50]}
    out = aggregate(scores, mode='matchpoints')
    assert out['A'] == 100.0
    assert out['B'] == 0.0


def test_matchpoints_ties_split_half():
    # A and B tie; both beat C. comparisons = 2.
    # A: tie(0.5) + win(1) = 1.5 / 2 = 0.75 -> 75%
    scores = {'A': [100], 'B': [100], 'C': [0]}
    out = aggregate(scores, mode='matchpoints')
    assert out['A'] == pytest.approx(75.0)
    assert out['B'] == pytest.approx(75.0)
    assert out['C'] == pytest.approx(0.0)


def test_matchpoints_single_lead_is_full():
    # With one candidate, comparisons floors at 1; it beats nothing -> 0%.
    out = aggregate({'A': [100, 200]}, mode='matchpoints')
    assert out['A'] == 0.0


# --------------------------------------------------------------------------
# aggregate() — imps vs per-deal datum
# --------------------------------------------------------------------------
def test_imps_vs_datum():
    # datum = (500 + 0) / 2 = 250; A diff +250 -> +6 IMPs, B diff -250 -> -6.
    scores = {'A': [500], 'B': [0]}
    out = aggregate(scores, mode='imps')
    assert out['A'] == pytest.approx(6.0)
    assert out['B'] == pytest.approx(-6.0)


def test_imps_zero_when_all_equal():
    scores = {'A': [100, 100], 'B': [100, 100]}
    out = aggregate(scores, mode='imps')
    assert out['A'] == 0.0
    assert out['B'] == 0.0


# --------------------------------------------------------------------------
# aggregate() — degenerate inputs
# --------------------------------------------------------------------------
def test_aggregate_empty():
    assert aggregate({}, mode='matchpoints') == {}
    assert aggregate({}, mode='imps') == {}


def test_aggregate_zero_deals():
    out = aggregate({'A': [], 'B': []}, mode='imps')
    assert out == {'A': 0.0, 'B': 0.0}
