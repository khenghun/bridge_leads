"""Orchestration between the HTTP layer and the opening-lead engine.

Leader-hand validation, constraint assembly, and the deterministic result cache;
the heavy work stays in `engine.lead.simulate_opening_lead`.

Determinism: every run uses `seed=0`, so identical inputs produce identical
output — which is exactly what makes the result cacheable.
"""

import json

from engine.lead import simulate_opening_lead

from ..common.cache import ResultCache
from ..common.constraints import SEATS, SimulationError, build_constraints, validate_hand

# Collect a generous per-lead cap of contract-setting sample deals so the UI can
# change how many it shows without re-solving (matches the old SAMPLE_CAP).
SAMPLE_CAP = 100

# Each cached result carries the full per-deal matrix (~1-2 MB of Python objects
# at 1000 deals), so keep the entry count modest.
_cache = ResultCache(max_entries=64, ttl=3600)


def leader_seat(declarer: str) -> str:
    """Opening leader is LHO of declarer."""
    return SEATS[(SEATS.index(declarer) + 1) % 4]


def validate_leader_hand(pbn: str) -> None:
    validate_hand(pbn, what='Leader hand')


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

    def compute():
        return simulate_opening_lead(
            leader_hand=req.leader_hand, level=req.level, strain=req.strain,
            declarer=req.declarer, vul=req.vul, penalty=req.penalty,
            constraints=constraints, num_simulations=req.num_simulations,
            seed=0, max_samples=SAMPLE_CAP,
        )

    result = _cache.get_or_compute(key, compute)

    return {
        **result,
        'leader': leader_seat(req.declarer),
        'meta': {'level': req.level, 'strain': req.strain, 'declarer': req.declarer},
    }
