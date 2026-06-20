"""
Tests for engine.shapes — envelope computation, the match predicate, and
feasibility warnings. Deterministic (pure functions).
"""

from engine.shapes import (
    envelope,
    matches,
    term_matches,
    compile_shapes,
    feasibility_warnings,
    _suit_counts,
)

# The South 15-17 1NT shape (balanced / 5-card major / 6-card minor).
SOUTH_1NT = [
    {'S': (2, 4), 'H': (2, 4), 'D': (2, 5), 'C': (2, 5)},   # A balanced
    {'H': (5, 5), 'S': (2, 3), 'D': (2, 4), 'C': (2, 4)},   # B 5 hearts
    {'S': (5, 5), 'H': (2, 3), 'D': (2, 4), 'C': (2, 4)},   # C 5 spades
    {'C': (6, 6), 'S': (2, 3), 'H': (2, 3), 'D': (2, 3)},   # D 6 clubs
    {'D': (6, 6), 'S': (2, 3), 'H': (2, 3), 'C': (2, 3)},   # E 6 diamonds
]


def _hand(s, h, d, c):
    """Build a hand of arbitrary cards with the given suit lengths."""
    ranks = 'AKQJT98765432'
    return ([f'S{r}' for r in ranks[:s]] + [f'H{r}' for r in ranks[:h]]
            + [f'D{r}' for r in ranks[:d]] + [f'C{r}' for r in ranks[:c]])


# --------------------------------------------------------------------------
# envelope
# --------------------------------------------------------------------------
def test_envelope_is_elementwise_min_max():
    env = envelope(SOUTH_1NT)
    # spades: mins {2,2,5,2,2} -> 2 ; maxes {4,3,5,3,3} -> 5
    assert env['S'] == (2, 5)
    assert env['H'] == (2, 5)
    # diamonds: maxes {5,4,4,3,6} -> 6 ; mins -> 2
    assert env['D'] == (2, 6)
    assert env['C'] == (2, 6)


def test_envelope_empty_is_unbounded():
    assert envelope([]) == {'S': (0, 13), 'H': (0, 13),
                            'D': (0, 13), 'C': (0, 13)}


def test_envelope_treats_missing_suit_as_unbounded():
    env = envelope([{'S': (5, 5)}])      # other suits unspecified
    assert env['S'] == (5, 5)
    assert env['H'] == (0, 13)


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def test_balanced_hand_matches_term_a():
    assert matches(_hand(4, 3, 3, 3), SOUTH_1NT)     # 4333
    assert matches(_hand(4, 4, 3, 2), SOUTH_1NT)     # 4432


def test_five_card_major_matches():
    assert matches(_hand(5, 3, 3, 2), SOUTH_1NT)     # 5 spades
    assert matches(_hand(2, 5, 3, 3), SOUTH_1NT)     # 5 hearts


def test_six_card_minor_matches():
    assert matches(_hand(2, 2, 3, 6), SOUTH_1NT)     # 6 clubs
    assert matches(_hand(3, 2, 6, 2), SOUTH_1NT)     # 6 diamonds


def test_shape_outside_all_terms_rejected():
    assert not matches(_hand(5, 5, 2, 1), SOUTH_1NT)  # 5-5 majors, singleton
    assert not matches(_hand(7, 2, 2, 2), SOUTH_1NT)  # 7-card suit
    assert not matches(_hand(1, 3, 4, 5), SOUTH_1NT)  # singleton spade


def test_term_matches_single_term():
    counts = _suit_counts(_hand(5, 3, 3, 2))
    assert term_matches(counts, SOUTH_1NT[2])         # matches the 5-spade term
    assert not term_matches(counts, SOUTH_1NT[1])     # not the 5-heart term


def test_none_bounds_are_unbounded():
    term = [{'S': (5, None)}]                          # at least 5 spades
    assert matches(_hand(7, 2, 2, 2), term)
    assert not matches(_hand(4, 3, 3, 3), term)


# --------------------------------------------------------------------------
# compile_shapes
# --------------------------------------------------------------------------
def test_compile_shapes_returns_envelope_and_predicate():
    env, pred = compile_shapes(SOUTH_1NT)
    assert env == envelope(SOUTH_1NT)
    assert pred(_hand(4, 3, 3, 3)) is True
    assert pred(_hand(7, 2, 2, 2)) is False


# --------------------------------------------------------------------------
# feasibility
# --------------------------------------------------------------------------
def test_feasible_terms_have_no_warnings():
    assert feasibility_warnings(SOUTH_1NT) == []


def test_minimum_exceeds_13_warns():
    # 4+4+4+4 = 16 minimum -> impossible
    warns = feasibility_warnings([{'S': (4, 5), 'H': (4, 5),
                                   'D': (4, 5), 'C': (4, 5)}])
    assert len(warns) == 1 and '> 13' in warns[0]


def test_maximum_below_13_warns():
    # 2+2+2+2 = 8 maximum -> can't reach 13
    warns = feasibility_warnings([{'S': (0, 2), 'H': (0, 2),
                                   'D': (0, 2), 'C': (0, 2)}])
    assert len(warns) == 1 and '< 13' in warns[0]
