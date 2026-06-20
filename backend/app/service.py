"""Orchestration between the HTTP layer and the simulation engine.

Ports the glue that used to live in `app.py`: leader-hand validation, shape-text
parsing, constraint assembly, and the deterministic result cache. The heavy work
stays in `engine.lead_simulator.simulate_opening_lead`.

Determinism: every run uses `seed=0`, so identical inputs produce identical
output — which is exactly what makes the result cacheable (the old code relied on
`@st.cache_data`; here we keep a small in-process LRU+TTL, matching its
`max_entries=256, ttl=3600`).
"""

import json
import time
from collections import OrderedDict

from engine.lead_simulator import simulate_opening_lead
from engine.shape_parser import parse_shapes
from engine.shapes import feasibility_warnings

# Collect a generous per-lead cap of contract-setting sample deals so the UI can
# change how many it shows without re-solving (matches the old SAMPLE_CAP).
SAMPLE_CAP = 100
RANKS = 'AKQJT98765432'
SEATS = ['N', 'E', 'S', 'W']

_CACHE_MAX = 256
_CACHE_TTL = 3600           # seconds
_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


class SimulationError(ValueError):
    """Bad simulation input (surfaced to the client as HTTP 422)."""


def leader_seat(declarer: str) -> str:
    """Opening leader is LHO of declarer."""
    return SEATS[(SEATS.index(declarer) + 1) % 4]


def validate_leader_hand(pbn: str) -> None:
    """Validate a PBN leader hand ('S.H.D.C'): 4 suits, legal ranks, no
    within-suit duplicates, exactly 13 cards. Raises SimulationError on any miss."""
    parts = (pbn or '').split('.')
    if len(parts) != 4:
        raise SimulationError(
            "Leader hand must be PBN 'spades.hearts.diamonds.clubs' (4 dot-separated suits).")
    total = 0
    for holding in parts:
        for c in holding:
            if c not in RANKS:
                raise SimulationError(f"invalid rank {c!r} in leader hand")
        if len(set(holding)) != len(holding):
            raise SimulationError("duplicate rank within a suit in leader hand")
        total += len(holding)
    if total != 13:
        raise SimulationError(f"leader hand must have 13 cards, got {total}")


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
    return out


def validate_shape(text: str) -> dict:
    """Parse a shape expression and report term count + feasibility warnings.
    Raises ShapeParseError on bad syntax (caller maps to 422)."""
    terms = parse_shapes(text)
    return {'ok': True, 'terms_count': len(terms),
            'warnings': feasibility_warnings(terms)}


def run_simulation(req) -> dict:
    """Run (or serve from cache) an opening-lead simulation for a SimulateRequest.

    Returns the engine result augmented with the `leader` seat and echoed `meta`
    so the frontend renders without recomputing anything."""
    validate_leader_hand(req.leader_hand)
    constraints = build_constraints(req.constraints.model_dump())

    key = json.dumps({
        'h': req.leader_hand, 'l': req.level, 's': req.strain, 'd': req.declarer,
        'v': req.vul, 'p': req.penalty, 'n': req.num_simulations, 'c': constraints,
    }, sort_keys=True, default=list)

    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < _CACHE_TTL:
        _cache.move_to_end(key)
        result = hit[1]
    else:
        result = simulate_opening_lead(
            leader_hand=req.leader_hand, level=req.level, strain=req.strain,
            declarer=req.declarer, vul=req.vul, penalty=req.penalty,
            constraints=constraints, num_simulations=req.num_simulations,
            seed=0, max_samples=SAMPLE_CAP,
        )
        _cache[key] = (now, result)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)

    return {
        **result,
        'leader': leader_seat(req.declarer),
        'meta': {'level': req.level, 'strain': req.strain, 'declarer': req.declarer},
    }
