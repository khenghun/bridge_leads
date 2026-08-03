"""In-process result cache shared by the simulation services.

Simulations are deterministic (every service calls its engine with `seed=0`), so
identical requests can reuse a result — the contract the old Streamlit
`@st.cache_data` provided. Requests run concurrently in Starlette's threadpool,
hence the lock; `_inflight` adds dogpile protection so simultaneous identical
requests simulate **once**: the first thread computes while the rest wait on its
Event.
"""

import threading
import time
from collections import OrderedDict


class ResultCache:
    """LRU + TTL cache with single-flight (dogpile) protection.

    Entries are whole simulation results (a 500-deal contract run is a few MB of
    Python objects), so keep `max_entries` modest.
    """

    def __init__(self, max_entries: int = 64, ttl: float = 3600):
        self.max_entries = max_entries
        self.ttl = ttl
        self._entries: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
        self._inflight: "dict[str, threading.Event]" = {}
        self._lock = threading.Lock()

    # -- introspection used by tests ---------------------------------------
    @property
    def inflight(self) -> dict:
        return self._inflight

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._inflight.clear()

    # -- the cache itself ---------------------------------------------------
    def _get(self, key: str):
        """Return a fresh entry for `key`, or None. Caller holds the lock."""
        hit = self._entries.get(key)
        if hit is not None and time.monotonic() - hit[0] < self.ttl:
            self._entries.move_to_end(key)
            return hit[1]
        return None

    def get_or_compute(self, key: str, compute) -> dict:
        """Serve `key` from cache, or run `compute()` exactly once per key even
        under concurrent identical requests (followers wait on the leader's
        Event; if the leader raises, a waiter takes over)."""
        while True:
            with self._lock:
                result = self._get(key)
                if result is not None:
                    return result
                event = self._inflight.get(key)
                if event is None:
                    self._inflight[key] = threading.Event()
                    break                       # we are the leader; go compute
            # A leader is already computing this key: wait, then re-check the
            # cache. If the leader failed, the loop makes us the next leader.
            event.wait()

        try:
            result = compute()
            with self._lock:
                self._entries[key] = (time.monotonic(), result)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
            return result
        finally:
            with self._lock:
                self._inflight.pop(key, None).set()
