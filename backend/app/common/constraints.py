"""Request-side constraint helpers shared by both simulation services.

Both tools accept the same constraint block (HCP bands, suit lengths, shape
*text* in the mini-language, one suit-quality grade) and the same PBN hand
string; only the seats differ.
"""

from engine.shape_parser import parse_shapes
from engine.shapes import feasibility_warnings

RANKS = 'AKQJT98765432'
SUITS = 'SHDC'
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


def build_fixed_cards(spec: dict) -> dict:
    """Normalise the `fixed_cards` block to `{seat: [card, ...]}`.

    Checks only what is knowable without the user's own hand: card syntax, and
    that no card is claimed twice (within a seat or across two seats). The
    remaining check — a fixed card that duplicates one of your own, or lands on
    your own seat — needs the hand, so `engine.sampling.resolve_fixed_cards`
    does it."""
    out: dict = {}
    owner: dict = {}
    for seat, cards in (spec or {}).items():
        seen = []
        for raw in cards or []:
            card = (raw or '').strip().upper().replace('10', 'T')
            if len(card) != 2 or card[0] not in SUITS or card[1] not in RANKS:
                raise SimulationError(
                    f"{raw!r} is not a card — use the endplay form, suit then "
                    "rank, e.g. 'HA' or 'DT'.")
            if card in seen:
                raise SimulationError(f"{seat} is given {card} twice.")
            if card in owner:
                raise SimulationError(
                    f"{card} is given to both {owner[card]} and {seat} — a card "
                    "can only be in one hand.")
            owner[card] = seat
            seen.append(card)
        if len(seen) > 13:
            raise SimulationError(f"{seat} is given {len(seen)} cards; a hand holds 13.")
        if seen:
            out[seat] = seen
    return out


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
    fixed_cards = build_fixed_cards(c.get('fixed_cards'))
    if fixed_cards:
        out['fixed_cards'] = fixed_cards
    return out


def validate_shape(text: str) -> dict:
    """Parse a shape expression and report term count + feasibility warnings.
    Raises ShapeParseError on bad syntax (caller maps to 422)."""
    terms = parse_shapes(text)
    return {'ok': True, 'terms_count': len(terms),
            'warnings': feasibility_warnings(terms)}
