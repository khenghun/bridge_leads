"""Orchestration between the HTTP layer and the optimal-contract engine.

Same shape as the lead service: validate, assemble constraints, and run through
the deterministic (`seed=0`) result cache so identical requests simulate once.
"""

import json

from engine.contract import simulate_contracts

from ..common.cache import ResultCache
from ..common.constraints import build_constraints, validate_hand

_cache = ResultCache(max_entries=32, ttl=3600)


def run_simulation(req) -> dict:
    """Run (or serve from cache) a contract simulation for a ContractRequest."""
    validate_hand(req.hand, what='Your hand')
    constraints = build_constraints(req.constraints.model_dump())
    strains = list(req.strains) or ['N', 'S', 'H', 'D', 'C']

    key = json.dumps({
        'h': req.hand, 'seat': req.seat, 'v': req.vul, 'n': req.num_deals,
        'st': sorted(strains), 'c': constraints,
    }, sort_keys=True, default=list)

    def compute():
        return simulate_contracts(
            hand=req.hand, seat=req.seat, vul=req.vul, constraints=constraints,
            num_deals=req.num_deals, strains=strains, seed=0,
        )

    return _cache.get_or_compute(key, compute)
