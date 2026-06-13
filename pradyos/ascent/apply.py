"""ASCENT applier — the gated path by which an approved proposal becomes an edit.

This is the most consequential step in the self-improvement loop: turning a
Sovereign-approved candidate into a real change on disk. It is therefore the most
heavily gated, and deliberately conservative about *where* it writes:

  * **Stages, never overwrites the running source.** By default the applier
    writes the approved source into a separate, writable ``apply_root`` (a
    staging area), preserving the module's relative path. The machine authors and
    stages a complete, gated change; promoting a staged change into the live tree
    (and restarting) is a separate, privileged act. This is also what makes apply
    work inside the hardened OS, where ``pradyos-web`` runs under
    ``ProtectSystem=strict`` and *cannot* write to its own package.
  * **Re-gates at apply time.** The candidate was generated against a snapshot of
    the source; before writing, the applier re-runs the REVIEW GATE against the
    *current* on-disk source. A change that would now ``deny`` or ``escalate``
    (broken parse, dropped public API, a forbidden/constitutional path) is
    refused — defence-in-depth on top of the approval.
  * **Path-safe.** The target is resolved and confined to ``apply_root``; any
    traversal outside it is refused.
  * **Atomic + audited.** Writes via a temp file + ``os.replace``, and records
    every apply (success or refusal) to the audit ledger.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from pradyos.ascent.loop import AscentError, _is_str
from pradyos.review import ReviewGate

# Review decisions that are safe to write. ``deny``/``escalate`` are refused —
# escalate in particular guards the constitution / audit / kernel / the gate
# itself, which must never be self-applied.
_APPLYABLE = ("approve", "revise")


class AscentApplier:
    """Stages a Sovereign-approved change to disk, re-gated + path-safe + audited."""

    def __init__(
        self,
        apply_root: Path | str,
        source_root: Path | str | None = None,
        review: Any | None = None,
        audit: Any | None = None,
    ) -> None:
        self._apply_root = Path(apply_root).resolve()
        if source_root is None:
            import pradyos

            # the parent of the package dir, so "pradyos/<...>.py" resolves correctly
            source_root = Path(pradyos.__file__).resolve().parent.parent
        self._source_root = Path(source_root).resolve()
        self._review = review if review is not None else ReviewGate()
        self._audit = audit  # an object with .record(agent_id, kind, summary, detail=) | None
        self._lock = threading.RLock()

    def read_current(self, module: str) -> str:
        """The present on-disk source of ``module`` (``""`` if absent/unreadable)."""
        try:
            path = (self._source_root / module).resolve()
        except (OSError, ValueError):
            return ""
        # Only read within the source root (no traversal).
        if os.path.commonpath([str(path), str(self._source_root)]) != str(self._source_root):
            return ""
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError:
            return ""

    def _safe_target(self, module: str) -> Path:
        target = (self._apply_root / module).resolve()
        root = str(self._apply_root)
        if target != self._apply_root and os.path.commonpath([str(target), root]) != root:
            raise AscentError("unsafe module path (escapes apply root)")
        return target

    def apply(self, module: str, after: str) -> dict[str, Any]:
        """Re-gate ``after`` against the current on-disk source, then stage it.

        Returns a result dict: ``applied`` (bool), the re-gate ``gate_decision``,
        a ``reason``, the staged ``path`` (or None when refused), and ``bytes``.
        """
        if not _is_str(module):
            raise AscentError("module must be a non-empty string")
        if not isinstance(after, str):
            raise AscentError("after must be a string")

        before = self.read_current(module)
        review = self._review.assess(module, after, before)
        decision = review["decision"]

        if decision not in _APPLYABLE:
            result = {
                "applied": False,
                "module": module,
                "gate_decision": decision,
                "reason": review["summary"],
                "path": None,
                "bytes": 0,
            }
            self._record(result)
            return result

        target = self._safe_target(module)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(after, encoding="utf-8")
        os.replace(tmp, target)  # atomic

        result = {
            "applied": True,
            "module": module,
            "gate_decision": decision,
            "reason": "staged for deploy",
            "path": str(target),
            "bytes": len(after.encode("utf-8")),
        }
        self._record(result)
        return result

    def _record(self, result: dict[str, Any]) -> None:
        if self._audit is None:
            return
        try:
            verb = "staged" if result["applied"] else f"refused ({result['gate_decision']})"
            self._audit.record(
                "ascent",
                "ascent.apply",
                f"ASCENT apply {verb}: {result['module']}",
                detail=dict(result),
                exit_code=0 if result["applied"] else 1,
            )
        except Exception:  # noqa: BLE001 — auditing must never break the apply path
            pass
