"""FastAPI app instance.

Run in dev:  uvicorn app.main:app --reload  (from the backend/ directory)
In prod it sits behind nginx (same-origin), so CORS is a dev-only convenience.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

app = FastAPI(
    title='Opening Lead Simulator API',
    version='4.0',
    description='Monte-Carlo + double-dummy opening-lead simulator. No AI — pure simulation.',
)

# Permissive CORS for local dev (Vite dev server on another port). Behind nginx
# the frontend and API share an origin, so this is harmless in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)
