"""Opening-lead routes, mounted under /api.

`POST /api/simulate` is a plain `def` handler on purpose: Starlette runs sync
endpoints in a threadpool, so the multi-second (blocking) DDS solve never stalls
the event loop.
"""

from fastapi import APIRouter, HTTPException

from engine.lead import auctions
from engine.shape_parser import ShapeParseError

from . import service
from ..common import constraints as constraint_helpers
from .schemas import (
    AuctionsResponse, SimulateRequest, SimulateResponse,
)
from ..common.schemas import ShapeValidateRequest, ShapeValidateResponse

router = APIRouter(prefix='/api')


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/auctions', response_model=AuctionsResponse)
def list_auctions():
    """Predefined demo auctions used to auto-fill the contract + constraints."""
    out = []
    for name in auctions.auction_names():
        a = auctions.get_auction(name)
        out.append({
            'name': name,
            'contract': a['contract'],
            'declarer': a['declarer'],
            'hcp': {seat: tuple(rng) for seat, rng in a['hcp'].items()},
            'shapes_text': a['shapes_text'],
            'note': a['note'],
        })
    return {'auctions': out}


@router.post('/validate/shape', response_model=ShapeValidateResponse)
def validate_shape(req: ShapeValidateRequest):
    """Live validation for the advanced-shape box (✓ term count / ⚠ warnings).
    Shared by both tools' constraint editors."""
    try:
        return constraint_helpers.validate_shape(req.text)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post('/simulate', response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    """Run an opening-lead Monte-Carlo + DDS simulation and rank the leads."""
    try:
        return service.run_simulation(req)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=f"shape constraint: {e}")
    except ValueError as e:                         # includes SimulationError
        raise HTTPException(status_code=422, detail=str(e))
