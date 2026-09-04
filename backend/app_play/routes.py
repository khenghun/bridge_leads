"""Play-solver routes, mounted under /api/play.

Both solve handlers are plain `def` on purpose: Starlette runs sync endpoints in
a threadpool, so the blocking DDS solve never stalls the event loop. The query
log is written *before* the run, so a request that turns out to be
infeasible (422) is logged too — those are the interesting ones.
"""

from fastapi import APIRouter, HTTPException

from engine.shape_parser import ShapeParseError

from app.common import constraints as constraint_helpers
from app.common import querylog
from app.common.schemas import ShapeValidateRequest, ShapeValidateResponse

from . import service
from .schemas import (
    AnalyzeRequest, AnalyzeResponse, HealthResponse, PositionRequest,
    PositionResponse,
)

router = APIRouter(prefix='/api/play')

# The shared ConstraintsEditor validates advanced-shape text against
# `/api/validate/shape` — the same path the lead app serves — so the play
# app must answer it too. Behind nginx every `/api/` call reaches this app.
shared_router = APIRouter(prefix='/api')


@shared_router.post('/validate/shape', response_model=ShapeValidateResponse)
def validate_shape(req: ShapeValidateRequest):
    try:
        return constraint_helpers.validate_shape(req.text)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get('/health', response_model=HealthResponse)
def health():
    return {'status': 'ok'}


@router.get('/debug/dds')
def dds_stats():
    """DDS batch counters since process start (calls / boards / seconds per
    entry point) — the v1.4 performance plan's step-0 instrumentation. The
    batch geometry these expose (boards per call) is the performance story."""
    from engine import dds_runtime
    return {**dds_runtime.stats(), 'threads': dds_runtime.DDS_THREADS}


@router.post('/analyze', response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Grade every decision one seat made in a recorded hand."""
    querylog.QUERY_LOG.record('play', req.model_dump())
    try:
        return service.run_analysis(req)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=f"shape constraint: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post('/position', response_model=PositionResponse)
def position(req: PositionRequest):
    """Grade the legal cards for whoever is on play after the given play."""
    querylog.QUERY_LOG.record('play', req.model_dump())
    try:
        return service.run_position(req)
    except ShapeParseError as e:
        raise HTTPException(status_code=422, detail=f"shape constraint: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
