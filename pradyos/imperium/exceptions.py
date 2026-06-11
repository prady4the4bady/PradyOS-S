"""IMPERIUM — custom exceptions.

Centralises all exception types raised by the IMPERIUM plane so callers
can import from a single, stable location.
"""

from __future__ import annotations


class ImperiumError(Exception):
    """Base class for all IMPERIUM errors."""


class TaskNotFound(ImperiumError):
    """Raised when a task_id cannot be found in the kernel registry.

    Surfaces from :meth:`Imperium.rollback` (and therefore from
    :meth:`SelfHealEngine.heal`) when the supplied *task_id* was never
    submitted to this kernel or has been purged from the in-memory registry.
    """
