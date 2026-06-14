"""FORESIGHT plane — predict → act → compare → learn (metacognition).

See :mod:`pradyos.foresight.engine`. The OS uses this to anticipate the value of
an action, choose the most promising one, and self-correct when reality differs.
"""

from __future__ import annotations

from pradyos.foresight.engine import (
    Episode,
    ForesightEngine,
    ForesightError,
    Outcome,
    Prediction,
    WorldModel,
)

__all__ = [
    "Episode",
    "ForesightEngine",
    "ForesightError",
    "Outcome",
    "Prediction",
    "WorldModel",
]
