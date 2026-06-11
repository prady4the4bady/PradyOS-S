"""Constitutional policy classifier (BASTION seed)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalDomain(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(slots=True)
class PolicyDecision:
    domain: ApprovalDomain
    reason: str
    matched_rule: str | None = None
    suggested_narrowing: str | None = None


@dataclass(slots=True)
class ConstitutionalRule:
    name: str
    description: str
    pattern: re.Pattern[str] | None = None
    kinds: frozenset[str] = field(default_factory=frozenset)
    decision: ApprovalDomain = ApprovalDomain.APPROVAL_REQUIRED
    suggested_narrowing: str | None = None

    def matches(self, kind: str, summary: str, detail: dict[str, Any]) -> bool:
        if self.kinds and kind not in self.kinds:
            return False
        if self.pattern is not None:
            haystack = " ".join(
                [summary, str(detail.get("command", "")), str(detail.get("intent", ""))]
            )
            return bool(self.pattern.search(haystack))
        return bool(self.kinds)


class Constitution:
    def __init__(self, rules: list[ConstitutionalRule]) -> None:
        self.rules = rules

    def classify(
        self, kind: str, summary: str, detail: dict[str, Any] | None = None
    ) -> PolicyDecision:
        detail = detail or {}
        for rule in self.rules:
            if rule.matches(kind, summary, detail):
                return PolicyDecision(
                    domain=rule.decision,
                    reason=rule.description,
                    matched_rule=rule.name,
                    suggested_narrowing=rule.suggested_narrowing,
                )
        return PolicyDecision(
            domain=ApprovalDomain.AUTONOMOUS,
            reason="No constitutional rule applied — falls within Domain B autonomous execution.",
            matched_rule=None,
        )


_DESTRUCTIVE_RE = re.compile(
    r"(?:^|[\s;|&])(rm\s+-rf?\s+/|mkfs(\.\w+)?\b|fdisk\b|dd\s+if=|shred\b|wipefs\b|"
    r"DROP\s+TABLE\b|TRUNCATE\s+TABLE\b|reboot\b|shutdown\b|halt\b|poweroff\b|"
    r"systemctl\s+(?:stop|disable|mask)\s+pradyos-)",
    re.IGNORECASE,
)
_EGRESS_RE = re.compile(
    r"(?:^|[\s;|&])(scp\s+\S+\s+\S+:|rclone\s+copy.*remote:|aws\s+s3\s+cp.*s3://|"
    r"curl\s+\S*\s*-d\s+@|gh\s+release\s+upload)",
    re.IGNORECASE,
)
_PRIVILEGE_RE = re.compile(
    r"(?:^|[\s;|&])(sudo\s+passwd|usermod\s+-aG\s+sudo|chown\s+root|chmod\s+u\+s|"
    r"visudo\b|setuid\b|setgid\b)",
    re.IGNORECASE,
)


def default_constitution() -> Constitution:
    return Constitution(
        [
            ConstitutionalRule(
                name="new_project_proposal",
                description="New project proposals cross the Sovereign boundary (Law 2).",
                kinds=frozenset({"project_proposal"}),
                decision=ApprovalDomain.APPROVAL_REQUIRED,
                suggested_narrowing="Run as background research (kind='research') first.",
            ),
            ConstitutionalRule(
                name="constitutional_change",
                description="Modifications to the constitution require Sovereign approval.",
                kinds=frozenset({"constitution_change", "policy_change"}),
                decision=ApprovalDomain.APPROVAL_REQUIRED,
            ),
            ConstitutionalRule(
                name="irreversible_destructive",
                description="Irreversible destructive operation on high-value state.",
                pattern=_DESTRUCTIVE_RE,
                decision=ApprovalDomain.APPROVAL_REQUIRED,
                suggested_narrowing="Use a snapshot/rollback-capable variant, or scope to /tmp.",
            ),
            ConstitutionalRule(
                name="data_egress",
                description="Data exfiltration crosses a trusted boundary.",
                pattern=_EGRESS_RE,
                decision=ApprovalDomain.APPROVAL_REQUIRED,
                suggested_narrowing="Stage locally and request review before egress.",
            ),
            ConstitutionalRule(
                name="privilege_modification",
                description="Privilege-elevation or identity-affecting change.",
                pattern=_PRIVILEGE_RE,
                decision=ApprovalDomain.APPROVAL_REQUIRED,
            ),
            ConstitutionalRule(
                name="strategic_initiative",
                description="Major strategic initiative — Domain A.",
                kinds=frozenset({"strategic_initiative", "major_shift"}),
                decision=ApprovalDomain.APPROVAL_REQUIRED,
            ),
        ]
    )
