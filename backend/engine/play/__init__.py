"""Play solver — replay a recorded hand and price every decision one seat made.

Two modules, mirroring the split the other tools use:

- `state.py` — pure bridge bookkeeping (replay, legal cards, trick winner). No
  DDS, no sampling; a malformed play raises `ValueError` naming the play index.
- `grader.py` — the Monte-Carlo / double-dummy grader built on top of it, using
  the shared `engine.sampling` deal source and `engine.dds_runtime`.
"""

from .grader import grade_play, grade_position
from .state import (
    Position, Trick, legal_cards, next_seat, replay, trick_winner, walk,
)

__all__ = [
    'Position', 'Trick', 'legal_cards', 'next_seat', 'replay', 'trick_winner',
    'walk', 'grade_play', 'grade_position',
]
