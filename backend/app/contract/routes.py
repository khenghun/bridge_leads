"""Optimal-contract routes, mounted under /api/contract.

`POST /api/contract/simulate` is a plain `def` handler for the same reason the
lead endpoint is: Starlette runs sync endpoints in a threadpool, keeping the
multi-second DDS solve off the event loop.
"""

from fastapi import APIRouter, HTTPException

from engine.shape_parser import ShapeParseError

from . import service
from .schemas import ContractRequest, ContractResponse
from ..common import querylog

router = APIRouter(prefix='/api/contract')


@router.post('/simulate', response_model=ContractResponse)
def simulate(req: ContractRequest):
    """Rank the contracts our side could be in, by Monte-Carlo + double-dummy."""
    # Before the run — see the note in app/lead/routes.py.
    querylog.QUERY_LOG.record('contract', req.model_dump())
    try:
        return service.run_simulation(req)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=f"shape constraint: {e}")
    except ValueError as e:                         # includes SimulationError
        raise HTTPException(status_code=422, detail=str(e))
