"""REVERIE plane — the OS's idle cognition loop (reflection + curiosity).

See :mod:`pradyos.reverie.engine`. Reflects on FORESIGHT calibration + the skill
library to surface blind spots and self-proposed curiosity goals.
"""

from __future__ import annotations

from pradyos.reverie.driver import ReverieDriver
from pradyos.reverie.engine import Reverie, ReverieError

__all__ = ["Reverie", "ReverieError", "ReverieDriver"]
