"""HTTP layer for the play solver.

Its own FastAPI app (and its own container) rather than another router on
`app.main`, so a play deploy never redeploys the lead API. Everything shared —
the constraint vocabulary, the result cache, the query log, the engine — is
imported from `app.common` / `engine`, exactly as `app/lead` does.
"""
