"""Append-only log of the simulations people ask for.

Deliberately minimal: a timestamp, which tool was used, and the request body.
No IP address, no session, no user agent, no response — enough to see what the
app is being used for and how often, and not enough to profile anyone.

**Off unless `BRIDGE_QUERY_LOG` names a SQLite file**, so local dev and the test
suite write nothing; production sets it in `deploy/lead/docker-compose.prod.yml`.

Every write is best-effort. A full disk or a read-only mount must never turn a
working simulation into a 500, so failures are swallowed — with one warning to
the container log, not one per request.
"""

import json
import logging
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,      -- ISO-8601 UTC, e.g. '2026-08-04T13:22:05Z'
    tool    TEXT NOT NULL,      -- 'lead' | 'contract'
    payload TEXT NOT NULL       -- the request body, as JSON
);
CREATE INDEX IF NOT EXISTS queries_ts ON queries (ts);
"""


class QueryLog:
    """SQLite-backed query log. Thread-safe, and a no-op when `path` is falsy."""

    def __init__(self, path: str | None):
        self.path = path or None
        self._lock = threading.Lock()
        self._warned = False
        if self.path:
            try:
                parent = os.path.dirname(os.path.abspath(self.path))
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with closing(self._connect()) as conn, conn:
                    conn.executescript(_SCHEMA)
            except Exception:
                # Give up permanently rather than retry (and re-fail) on every
                # request for the life of the process.
                self._fail(f"could not open the query log at {self.path!r}")
                self.path = None

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def _connect(self):
        """A fresh connection per write.

        Writes are tiny and rare beside a multi-second DDS solve, so the connect
        cost is noise — and holding no handle open means nothing to go stale
        across threads, or if the file is rotated out from under us."""
        return sqlite3.connect(self.path, timeout=5)

    def record(self, tool: str, payload) -> None:
        """Append one query. Never raises."""
        if not self.path:
            return
        try:
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            body = json.dumps(payload, sort_keys=True, default=str)
            with self._lock, closing(self._connect()) as conn, conn:
                conn.execute(
                    'INSERT INTO queries (ts, tool, payload) VALUES (?, ?, ?)',
                    (ts, tool, body))
        except Exception:
            self._fail('could not write to the query log')

    def _fail(self, message: str) -> None:
        if not self._warned:
            self._warned = True
            log.warning('%s — query logging disabled', message, exc_info=True)


# Module-level singleton, read through the module (`querylog.QUERY_LOG`) rather
# than imported by value, so tests can swap it for one pointing at a tmp file.
QUERY_LOG = QueryLog(os.environ.get('BRIDGE_QUERY_LOG'))
