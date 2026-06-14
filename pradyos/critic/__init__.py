"""CRITIC plane — an adversarial critic ensemble (judgment gate, L4).

See :mod:`pradyos.critic.ensemble`. Several skeptical critics score a proposal
across dimensions (safety/correctness/value); any blocker vetoes it. Used to vet
self-edits and goals before the Sovereign's apply-gate.
"""

from __future__ import annotations

from pradyos.critic.ensemble import Critic, CriticEnsemble, Critique, default_critics

__all__ = ["Critic", "CriticEnsemble", "Critique", "default_critics"]
