"""DRIVE plane — the goal/drive manager (self-direction, Sovereign-gated, L3).

See :mod:`pradyos.drive.manager`. REVERIE's curiosity goals are proposed here;
the Sovereign approves; approved goals can be run through the Guild.
"""

from __future__ import annotations

from pradyos.drive.manager import STATUSES, DriveError, DriveManager, Goal

__all__ = ["STATUSES", "DriveError", "DriveManager", "Goal"]
