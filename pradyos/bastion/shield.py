"""BASTION risk-classification and policy-simulation engine.

``assess(action)`` returns a :class:`Verdict` by a deterministic rule set:

  * irreversible, destructive, or secret-egress actions cross the **sovereign**
    approval boundary (decision ``escalate``);
  * a small set of constitutionally forbidden action kinds are always **denied**;
  * everything else that is reversible and policy-compliant stays **autonomous**
    (decision ``allow``).

A 0–10 risk score is a weighted sum of the action's risk factors. Every verdict
carries the reasons that fired, whether a rollback exists, and a narrower-
permission hint (explainable enforcement, §8.4).

``scan_content(text)`` is a heuristic prompt-injection scanner over untrusted
content; ``response_for(score)`` maps a risk score to the response protocol.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

_DATA_CLASSES = ("public", "internal", "secret")

# Action kinds that may never run autonomously OR via escalation — they touch
# the constitution itself (cf. IMPERIUM immutable rules). Always denied.
_FORBIDDEN_KINDS = frozenset(
    {
        "imperium.modify",
        "constitution.modify",
        "audit.delete",
        "ledger.delete",
    }
)

# Heuristic prompt-injection signatures (case-insensitive). Honest about being a
# heuristic — high recall, not a proof.
_INJECTION_SIGNATURES: tuple[tuple[str, str], ...] = (
    (
        r"ignore (all |the |your )?(previous|prior|above) (instructions|prompts?)",
        "ignore-instructions",
    ),
    (r"disregard (all |the |your )?(previous|prior|above)", "disregard"),
    (r"you are now (a|an|the)\b", "role-override"),
    (
        r"(reveal|print|show|leak) (your |the )?(system )?(prompt|instructions|secret|api[_ ]?key)",
        "exfiltration",
    ),
    (r"\bexfiltrate\b", "exfiltration"),
    (r"new (system )?prompt\s*[:=]", "prompt-injection"),
    (r"</?(system|assistant|user)>", "role-tag-injection"),
    (r"do not (tell|inform|alert) (the )?(user|sovereign|admin)", "conceal"),
)


class BastionError(RuntimeError):
    """Base class for BASTION failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Action:
    """A proposed action to assess.

    ``data_class`` is the sensitivity of any data the action touches
    (``public`` / ``internal`` / ``secret``).
    """

    kind: str
    target: str = ""
    reversible: bool = True
    privileged: bool = False
    egress: bool = False
    destructive: bool = False
    data_class: str = "internal"

    def __post_init__(self) -> None:
        if not _is_str(self.kind):
            raise BastionError("action kind must be a non-empty string")
        if self.data_class not in _DATA_CLASSES:
            raise BastionError(f"data_class must be one of {_DATA_CLASSES}")
        for flag in ("reversible", "privileged", "egress", "destructive"):
            if not isinstance(getattr(self, flag), bool):
                raise BastionError(f"{flag} must be a bool")


@dataclass(frozen=True)
class Verdict:
    """The result of assessing an :class:`Action`."""

    decision: str  # allow | escalate | deny
    domain: str  # autonomous | sovereign
    risk_score: int  # 0..10
    reasons: tuple[str, ...]
    rollback_available: bool
    narrower: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "domain": self.domain,
            "risk_score": self.risk_score,
            "reasons": list(self.reasons),
            "rollback_available": self.rollback_available,
            "narrower": self.narrower,
        }


class Bastion:
    """The constitutional shield: assess actions, scan content, set responses."""

    def __init__(self) -> None:
        self._history: list[dict[str, Any]] = []
        self._counts = {"allow": 0, "escalate": 0, "deny": 0}
        self._lock = threading.RLock()

    # ── assessment ───────────────────────────────────────────────────────────

    def assess(self, action: Action) -> Verdict:
        """Classify an action and return an explainable :class:`Verdict`."""
        if not isinstance(action, Action):
            raise BastionError("assess expects an Action")
        reasons: list[str] = []
        score = 0

        forbidden = action.kind in _FORBIDDEN_KINDS
        if forbidden:
            reasons.append("constitutionally-forbidden")
            score = 10

        if action.destructive:
            reasons.append("destructive")
            score += 4
        if not action.reversible:
            reasons.append("irreversible")
            score += 3
        if action.egress and action.data_class == "secret":
            reasons.append("secret-egress")
            score += 4
        elif action.egress:
            reasons.append("egress")
            score += 2
        if action.privileged:
            reasons.append("privileged")
            score += 2
        if action.data_class == "secret" and not action.egress:
            reasons.append("touches-secret")
            score += 1

        score = min(10, score)

        requires_sovereign = (
            (not action.reversible)
            or action.destructive
            or (action.egress and action.data_class == "secret")
        )

        if forbidden:
            decision, domain = "deny", "sovereign"
        elif requires_sovereign:
            decision, domain = "escalate", "sovereign"
        else:
            decision, domain = "allow", "autonomous"

        verdict = Verdict(
            decision=decision,
            domain=domain,
            risk_score=score,
            reasons=tuple(reasons),
            rollback_available=action.reversible and not forbidden,
            narrower=self._narrower(action, forbidden),
        )
        with self._lock:
            self._counts[decision] += 1
            self._history.append({"action": action.kind, "verdict": verdict.to_dict()})
        return verdict

    def _narrower(self, action: Action, forbidden: bool) -> str | None:
        if forbidden:
            return None
        if action.egress and action.data_class == "secret":
            return "downgrade data_class or route through an approved egress point"
        if not action.reversible:
            return "perform a reversible variant (snapshot first) to stay autonomous"
        if action.privileged:
            return "retry in the non-privileged lane if the target allows it"
        return None

    # ── content scanning ─────────────────────────────────────────────────────

    def scan_content(self, text: str) -> dict[str, Any]:
        """Heuristically scan untrusted content for prompt-injection patterns."""
        if not isinstance(text, str):
            raise BastionError("scan_content expects a string")
        matched: list[str] = []
        for pattern, name in _INJECTION_SIGNATURES:
            if re.search(pattern, text, re.IGNORECASE) and name not in matched:
                matched.append(name)
        score = min(10, len(matched) * 4)
        if score == 0:
            verdict = "clean"
        elif score <= 4:
            verdict = "suspicious"
        else:
            verdict = "malicious"
        return {"injection_score": score, "verdict": verdict, "signatures": matched}

    # ── response protocol ────────────────────────────────────────────────────

    @staticmethod
    def response_for(risk_score: int) -> str:
        """Map a 0–10 risk score to the response protocol tier."""
        if not isinstance(risk_score, int) or not 0 <= risk_score <= 10:
            raise BastionError("risk_score must be an int in 0..10")
        if risk_score < 3:
            return "log"
        if risk_score <= 6:
            return "quarantine"
        return "safe_stop_escalate"

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "assessments": sum(self._counts.values()),
                "by_decision": dict(self._counts),
            }

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
            self._counts = {"allow": 0, "escalate": 0, "deny": 0}
