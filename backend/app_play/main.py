"""FastAPI app instance for the play solver.

Run in dev:  uvicorn app_play.main:app --reload --port 8001  (from backend/)

A separate app from `app.main` — and a separate container from the same image —
so a play deploy never redeploys the lead API. In prod it sits behind nginx
(same-origin), so CORS is a dev-only convenience.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as play_router, shared_router

app = FastAPI(
    title='Bridge Play Solver API',
    version='1.0',
    description='Replay a recorded hand and price every decision one seat made '
                '— Monte-Carlo + double-dummy. No AI, pure simulation.',
)

# Permissive CORS for local dev (Vite dev server on another port). Behind nginx
# the frontend and API share an origin, so this is harmless in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(play_router)
app.include_router(shared_router)
