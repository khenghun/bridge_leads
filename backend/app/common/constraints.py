"""Request-side constraint helpers shared by both simulation services.

Both tools accept the same constraint block (HCP bands, suit lengths, shape
*text* in the mini-language, one suit-quality grade) and the same PBN hand
string; only the seats differ.
"""

from engine.shape_parser import parse_shapes
from engine.shapes import feasibility_warnings

RANKS = 'AKQJT98765432'
SEATS = ['N', 'E', 'S', 'W']


class SimulationError(ValueError):
    """Bad simulation input (surfaced to the client as HTTP 422)."""


def validate_hand(pbn: str, what: str = 'hand') -> None:
    """Validate a PBN hand ('S.H.D.C'): 4 suits, legal ranks, no within-suit
    duplicates, exactly 13 cards. Raises SimulationError on any miss."""
    parts = (pbn or '').split('.')
    if len(parts) != 4:
        raise SimulationError(
            f"{what} must be PBN 'spades.hearts.diamonds.clubs' (4 dot-separated suits).")
    total = 0
    for holding in parts:
        for c in holding:
            if c not in RANKS:
                raise SimulationError(f"invalid rank {c!r} in {what}")
        if len(set(holding)) != len(holding):
            raise SimulationError(f"duplicate rank within a suit in {what}")
        total += len(holding)
    if total != 13:
        raise SimulationError(f"{what} must have 13 cards, got {total}")


def build_constraints(c: dict) -> dict:
    """Translate the request Constraints (dict form) into the engine's constraint
    dict. Shape *text* is parsed into terms via `parse_shapes` (which raises
    ShapeParseError on bad syntax — caller maps that to 422)."""
    out: dict = {}
    hcp = {seat: tuple(rng) for seat, rng in (c.get('hcp') or {}).items()}
    if hcp:
        out['hcp'] = hcp
    suit_length = {
        seat: {s: tuple(rng) for s, rng in sl.items()}
        for seat, sl in (c.get('suit_length') or {}).items() if sl
    }
    if suit_length:
        out['suit_length'] = suit_length
    shapes = {}
    for seat, text in (c.get('shapes') or {}).items():
        if text and text.strip():
            shapes[seat] = parse_shapes(text)
    if shapes:
        out['shapes'] = shapes
    quality = {
        seat: {s: level for s, level in q.items() if level}
        for seat, q in (c.get('quality') or {}).items() if q
    }
    quality = {seat: q for seat, q in quality.items() if q}
    if quality:
        out['quality'] = quality
    return out


def validate_shape(text: str) -> dict:
    """Parse a shape expression and report term count + feasibility warnings.
    Raises ShapeParseError on bad syntax (caller maps to 422)."""
    terms = parse_shapes(text)
    return {'ok': True, 'terms_count': len(terms),
            'warnings': feasibility_warnings(terms)}
