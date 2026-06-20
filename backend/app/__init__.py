"""FastAPI application package for the Opening Lead Simulator.

Thin HTTP layer over the framework-agnostic `engine` package: request/response
schemas (`schemas`), orchestration + caching (`service`), routes (`routes`), and
the app instance (`main`). No simulation logic lives here — that stays in `engine`.
"""
