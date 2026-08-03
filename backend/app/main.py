"""FastAPI app instance.

Run in dev:  uvicorn app.main:app --reload  (from the backend/ directory)
In prod it sits behind nginx (same-origin), so CORS is a dev-only convenience.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .contract.routes import router as contract_router
from .lead.routes import router as lead_router

app = FastAPI(
    title='Bridge Simulation API',
    version='7.0',
    description='Monte-Carlo + double-dummy bridge tools (opening lead, optimal '
                'contract). No AI — pure simulation.',
)

# Permissive CORS for local dev (Vite dev server on another port). Behind nginx
# the frontend and API share an origin, so this is harmless in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(lead_router)
app.include_router(contract_router)
