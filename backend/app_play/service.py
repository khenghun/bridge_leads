"""Orchestration between the HTTP layer and the play-solver engine.

Constraint assembly (shape *text* -> terms), the "you cannot constrain a hand
you can see" check, and the deterministic result cache. The grading itself stays
in `engine.play`.

Determinism: every run uses `seed=0`, so identical inputs produce identical
output — which is what makes the call cacheable, exactly as in the other two
tools.
"""

import json

from engine.play import grader, state

from app.common.cache import ResultCache
from app.common.constraints import build_constraints

# A graded full hand is 26 decisions x an options list — far smaller than a
# 1000-deal lead matrix, so a roomier cache is cheap. Re-grading the same hand
# for a different seat is the common case and misses anyway.
_cache = ResultCache(max_entries=64, ttl=3600)

CONSTRAINT_BLOCKS = ('hcp', 'suit_length', 'shapes', 'quality', 'fixed_cards')


def clear_cache() -> None:
    _cache.clear()


def _reject_visible(constraints: dict, visible, hidden) -> None:
    """Constraints describe hands the player *cannot see*; the rest are known."""
    for seat in visible:
        for block in CONSTRAINT_BLOCKS:
            if (constraints.get(block) or {}).get(seat):
                raise ValueError(
                    f"{seat}'s hand is visible here, so there is nothing to "
                    "infer about it — constrain only the hidden seats "
                    f"({', '.join(hidden)}).")


def _key(req, extra: dict) -> str:
    return json.dumps({
        'h': req.hands, 'l': req.level, 's': req.strain, 'd': req.declarer,
        'v': req.vul, 'p': req.penalty, 'play': list(req.play),
        'm': req.method, 'n': req.num_deals,
        'c': build_constraints(req.constraints.model_dump()),
        **extra,
    }, sort_keys=True, default=list)


def run_analysis(req) -> dict:
    """Grade every decision `req.seat` made. Raises ValueError -> 422."""
    constraints = build_constraints(req.constraints.model_dump())

    dummy = state.next_seat(req.declarer, 2)
    if req.seat == dummy:
        raise ValueError(
            f"{req.seat} is dummy and makes no decisions — declarer plays "
            "dummy's cards. Grade the declarer instead.")
    visible = ([req.declarer, dummy] if req.seat == req.declarer
               else [req.seat, dummy])
    hidden = [s for s in state.SEATS if s not in visible]
    _reject_visible(constraints, visible, hidden)

    def compute():
        return grader.grade_play(
            hands=req.hands, level=req.level, strain=req.strain,
            declarer=req.declarer, play=list(req.play), seat=req.seat,
            method=req.method, num_deals=req.num_deals,
            constraints=constraints, seed=0)

    return _cache.get_or_compute(_key(req, {'seat': req.seat}), compute)


def run_position(req) -> dict:
    """Grade the legal cards for whoever is on play. Raises ValueError -> 422."""
    constraints = build_constraints(req.constraints.model_dump())

    # Replaying first is cheap and gives the visibility check (and any malformed
    # play) a chance to answer before a single DDS call is spent.
    position = state.replay(req.hands, req.strain, req.declarer, list(req.play))
    if position.complete:
        raise ValueError("the play is complete — there is no card left to choose.")
    view = grader.view_for(position, position.to_play)
    visible = grader.visible_seats(position, view)
    hidden = [s for s in state.SEATS if s not in visible]
    _reject_visible(constraints, visible, hidden)

    def compute():
        return grader.grade_position(
            hands=req.hands, level=req.level, strain=req.strain,
            declarer=req.declarer, play=list(req.play), method=req.method,
            num_deals=req.num_deals, constraints=constraints, seed=0)

    return _cache.get_or_compute(_key(req, {'seat': None}), compute)
