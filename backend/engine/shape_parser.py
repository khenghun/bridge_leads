"""
Parser for the disjunctive shape mini-language.

Grammar (number-first, suit in s/h/d/c, case-insensitive):

    expression := term ( "or" term )*
    term       := "(" atom ( "," atom )* ")"
    atom       := length-spec suit

Length specs, attached to a suit letter:

    2-4h    range, inclusive          -> (2, 4)
    5s      exact                      -> (5, 5)
    >=2c    at least (inclusive)       -> (2, None)
    <=3h    at most  (inclusive)       -> (None, 3)
    <5h     strict, compat shorthand   -> (None, 4)
    >1c     strict, compat shorthand   -> (2, None)

Unmentioned suits are unbounded. A suit named twice intersects (tighter wins).
Terms are ORed; the whole thing parses to a list of ``{suit: (min, max)}`` dicts
ready for :mod:`engine.shapes`.

Raises :class:`ShapeParseError` on bad tokens or contradictory/empty bounds.
Feasibility ("can this term make 13 cards?") is a *warning*, surfaced separately
via :func:`engine.shapes.feasibility_warnings`.
"""

import re

SUITS = ['S', 'H', 'D', 'C']

# length-spec + suit. op is optional; n2 (range upper) is optional.
_ATOM_RE = re.compile(
    r'^(<=|>=|<|>|=)?\s*(\d+)(?:\s*-\s*(\d+))?\s*([shdcSHDC])$')


class ShapeParseError(ValueError):
    """Raised when a shape expression can't be parsed."""


def _max_opt(a, b):
    """Tighter lower bound (None = unbounded below)."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _min_opt(a, b):
    """Tighter upper bound (None = unbounded above)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _parse_atom(text):
    """Parse a single clause like '2-4h' -> ('H', (2, 4))."""
    m = _ATOM_RE.match(text.strip())
    if not m:
        raise ShapeParseError(f"can't parse clause {text!r}")
    op, n1, n2, suit = m.group(1), int(m.group(2)), m.group(3), m.group(4).upper()

    if n2 is not None:
        if op:
            raise ShapeParseError(
                f"can't combine an operator with a range in {text!r}")
        lo, hi = n1, int(n2)
    elif op == '<':
        lo, hi = None, n1 - 1
    elif op == '>':
        lo, hi = n1 + 1, None
    elif op == '<=':
        lo, hi = None, n1
    elif op == '>=':
        lo, hi = n1, None
    else:  # '=' or bare number
        lo, hi = n1, n1

    for v in (lo, hi):
        if v is not None and not (0 <= v <= 13):
            raise ShapeParseError(f"length out of range 0-13 in {text!r}")
    if lo is not None and hi is not None and lo > hi:
        raise ShapeParseError(f"empty range in {text!r}")
    return suit, (lo, hi)


def _parse_term(text):
    """Parse one parenthesised, comma-separated term -> {suit: (min, max)}."""
    inner = text.strip()
    if not (inner.startswith('(') and inner.endswith(')')):
        raise ShapeParseError(f"term must be wrapped in parentheses: {text!r}")
    inner = inner[1:-1].strip()
    if not inner:
        raise ShapeParseError("empty term ()")

    term = {}
    for part in inner.split(','):
        part = part.strip()
        if not part:
            continue
        suit, (lo, hi) = _parse_atom(part)
        if suit in term:
            elo, ehi = term[suit]
            lo, hi = _max_opt(elo, lo), _min_opt(ehi, hi)
            if lo is not None and hi is not None and lo > hi:
                raise ShapeParseError(
                    f"contradictory bounds for {suit} in {text!r}")
        term[suit] = (lo, hi)
    if not term:
        raise ShapeParseError("empty term ()")
    return term


def parse_shapes(text):
    """Parse a full shape expression into a list of terms (the OR).

    Empty / whitespace input returns [] (no constraint). 'or'-separated terms
    each become a {suit: (min, max)} dict.
    """
    if not text or not text.strip():
        return []
    pieces = re.split(r'\bor\b', text, flags=re.IGNORECASE)
    terms = [_parse_term(p) for p in pieces if p.strip()]
    if not terms:
        raise ShapeParseError("no terms found")
    return terms
