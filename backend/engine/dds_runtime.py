"""Shared double-dummy solver runtime.

Every DDS call in the project goes through this module. It owns three pieces of
global state that must not be duplicated per app:

1. **The thread cap.** DDS otherwise grabs every core and allocates memory per
   thread — bad on a shared/public box with concurrent users. Override with the
   `BRIDGE_DDS_THREADS` env var (`0` = let DDS auto-detect all cores).
2. **The re-entrancy lock.** libdds's multi-board functions (`SolveAllBoards*`,
   `CalcAllTables*`) share global internal state and must be entered by one
   caller at a time, while FastAPI runs our blocking handlers concurrently in
   Starlette's threadpool. Both the lead simulator and the contract calculator
   take *this* lock — a per-module lock would not protect anything.
3. **The batch sizes.** Each batch function has its own array cap
   (`MAXNOOFBOARDS` = 200 boards, `MAXNOOFTABLES` = 40 tables); passing more
   raises, which would silently drop us onto a much slower single-board path.
"""

import os
import threading

import endplay._dds as _dds
from endplay.dds import solve_board, solve_all_boards, calc_dd_table, calc_all_tables

_BOARD_BATCH = _dds.MAXNOOFBOARDS      # 200
_TABLE_BATCH = _dds.MAXNOOFTABLES      # 40

DDS_THREADS = int(os.environ.get('BRIDGE_DDS_THREADS') or min(os.cpu_count() or 1, 4))
if DDS_THREADS > 0:
    _dds.SetMaxThreads(DDS_THREADS)

# The one global DDS lock (see the module docstring).
DDS_LOCK = threading.Lock()


def solve_all(deals):
    """Solve every candidate lead of every deal, in MAXNOOFBOARDS-sized batches.

    Each batch goes through DDS's multithreaded SolveAllBoardsBin; if a batch
    errors we fall back to solving its boards one at a time so a single bad
    deal can't sink the whole run.
    """
    results = []
    with DDS_LOCK:
        for i in range(0, len(deals), _BOARD_BATCH):
            batch = deals[i:i + _BOARD_BATCH]
            try:
                results.extend(solve_all_boards(batch))
            except Exception:
                results.extend(solve_board(d) for d in batch)
    return results


def calc_tables(deals, exclude=()):
    """Double-dummy table (5 strains x 4 declarers) per deal, in MAXNOOFTABLES batches.

    `exclude` is an iterable of `endplay.types.Denom` to skip; excluding the two
    minors cuts the solve time roughly 40%, which is the contract calculator's
    one performance lever. Same per-batch fallback as `solve_all`.
    """
    exclude = list(exclude)
    results = []
    with DDS_LOCK:
        for i in range(0, len(deals), _TABLE_BATCH):
            batch = deals[i:i + _TABLE_BATCH]
            try:
                results.extend(calc_all_tables(batch, exclude=exclude))
            except Exception:
                results.extend(calc_dd_table(d) for d in batch)
    return results
