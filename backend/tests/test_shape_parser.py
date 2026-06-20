"""
Tests for engine.shape_parser — the disjunctive shape mini-language.

Pure functions, so these are deterministic. Cover each length-spec form, AND
within a term, OR across terms, intersection of repeated suits, and the error
cases that must raise ShapeParseError.
"""

import pytest

from engine.shape_parser import parse_shapes, ShapeParseError


# --------------------------------------------------------------------------
# atom / length-spec forms
# --------------------------------------------------------------------------
def test_range_form():
    assert parse_shapes("(2-4h)") == [{'H': (2, 4)}]


def test_exact_form():
    assert parse_shapes("(5s)") == [{'S': (5, 5)}]


def test_explicit_equals():
    assert parse_shapes("(=5s)") == [{'S': (5, 5)}]


def test_inclusive_at_least_and_at_most():
    assert parse_shapes("(>=2c)") == [{'C': (2, None)}]
    assert parse_shapes("(<=3h)") == [{'H': (None, 3)}]


def test_strict_compat_shorthand():
    # <5h means <= 4 ; >1c means >= 2 (the user's original notation)
    assert parse_shapes("(<5h)") == [{'H': (None, 4)}]
    assert parse_shapes("(>1c)") == [{'C': (2, None)}]


def test_case_insensitive_suit():
    assert parse_shapes("(5S)") == [{'S': (5, 5)}]


# --------------------------------------------------------------------------
# terms (AND) and expressions (OR)
# --------------------------------------------------------------------------
def test_and_within_term():
    assert parse_shapes("(5h, 2-3s, 2-4d, 2-4c)") == [
        {'H': (5, 5), 'S': (2, 3), 'D': (2, 4), 'C': (2, 4)}
    ]


def test_or_across_terms():
    terms = parse_shapes("(5h) or (5s)")
    assert terms == [{'H': (5, 5)}, {'S': (5, 5)}]


def test_or_is_case_insensitive():
    assert parse_shapes("(5h) OR (5s)") == [{'H': (5, 5)}, {'S': (5, 5)}]


def test_whitespace_tolerated():
    assert parse_shapes("  ( 2 - 4 h ,  5 s )  ") == [{'H': (2, 4), 'S': (5, 5)}]


def test_repeated_suit_intersects():
    # >=2h and <=4h  ->  (2, 4)
    assert parse_shapes("(>=2h, <=4h)") == [{'H': (2, 4)}]


def test_empty_input_returns_no_terms():
    assert parse_shapes("") == []
    assert parse_shapes("   ") == []
    assert parse_shapes(None) == []


def test_full_south_1nt_expression():
    text = ("(2-4s, 2-4h, 2-5d, 2-5c) or (5h, 2-3s, 2-4d, 2-4c) "
            "or (5s, 2-3h, 2-4d, 2-4c) or (6c, 2-3s, 2-3h, 2-3d) "
            "or (6d, 2-3s, 2-3h, 2-3c)")
    terms = parse_shapes(text)
    assert len(terms) == 5
    assert terms[0] == {'S': (2, 4), 'H': (2, 4), 'D': (2, 5), 'C': (2, 5)}
    assert terms[3] == {'C': (6, 6), 'S': (2, 3), 'H': (2, 3), 'D': (2, 3)}


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------
def test_missing_parens_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("5h")


def test_unparseable_clause_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("(5x)")          # x is not a suit


def test_range_with_operator_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("(>2-4h)")


def test_length_out_of_range_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("(14h)")
    with pytest.raises(ShapeParseError):
        parse_shapes("(>13h)")        # would imply >= 14


def test_empty_range_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("(4-2h)")


def test_contradictory_repeated_suit_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("(>=5h, <=3h)")


def test_empty_term_raises():
    with pytest.raises(ShapeParseError):
        parse_shapes("()")
