"""A fingerprint of the engine's source, for the play worker's sha check.

The play solver's Lambda worker (docs/play/v1.5-lambda-strict-plan.md) runs
the same engine as the API; every request carries `engine_sha` and the worker
refuses a mismatch, so a half-deployed API/worker pair can be slow (the client
falls back to judging locally) but never disagree with itself. The fingerprint
is a hash of the engine package's Python sources — the same code gives the
same sha wherever it runs, with no dependency on git or an image tag. Line
endings are normalised first: a Windows checkout (core.autocrlf) and the
Linux image CI builds must agree, and they did not before this.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent


def source_digest(root: Path) -> str:
    """12 hex chars over every `.py` under `root`, in path order, CRLF-blind."""
    h = hashlib.sha256()
    for path in sorted(Path(root).rglob('*.py')):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(b'\0')
        h.update(path.read_bytes().replace(b'\r\n', b'\n'))
        h.update(b'\0')
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def engine_sha() -> str:
    return source_digest(_ENGINE_DIR)
