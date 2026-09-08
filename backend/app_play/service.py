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
# 1000-deal lead matrix, so a roomier cache is cheap. An expert-opponents run
# arrives as one request per decision, and a client that dropped (a sleeping
# laptop) resumes by re-requesting them: every chunk of a whole-table run must
# still be here an hour later, so the cache is sized for hundreds of entries.
_cache = ResultCache(max_entries=1024, ttl=3600)

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
        'x': req.expert.model_dump() if req.expert_opponents else None,
        'xc': _expert_constraints(req),
        'esc': _escalation(req),
        **extra,
    }, sort_keys=True, default=list)


def _expert_constraints(req):
    """The all-seat constraints the expert filter judges opponents under:
    `expert_constraints` when given, else the request's own (which only cover
    the seats hidden from the graded view)."""
    if not req.expert_opponents:
        return None
    src = req.expert_constraints if req.expert_constraints is not None else req.constraints
    return build_constraints(src.model_dump())


def _escalation(req):
    """The escalation settings as the engine takes them; None when the client
    turned it off or nothing is sampled."""
    if req.escalation is None or req.method == 'double_dummy':
        return None
    return req.escalation.model_dump()


def _expert_kwargs(req) -> dict:
    if not req.expert_opponents:
        return {}
    return {'expert': req.expert.model_dump(),
            'expert_constraints': _expert_constraints(req)}


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
            constraints=constraints, seed=0, vul=req.vul, penalty=req.penalty,
            decisions=req.decisions, escalation=_escalation(req),
            **_expert_kwargs(req))

    return _cache.get_or_compute(
        _key(req, {'seat': req.seat, 'dec': req.decisions}), compute)


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
            num_deals=req.num_deals, constraints=constraints, seed=0,
            vul=req.vul, penalty=req.penalty, **_expert_kwargs(req))

    return _cache.get_or_compute(_key(req, {'seat': None}), compute)
