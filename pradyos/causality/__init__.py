"""CAUSALITY plane — counterfactual credit assignment (autonomy L5).

See :mod:`pradyos.causality.engine`. Estimates whether a cause actually produced
an effect (P(effect|cause) − P(effect|¬cause)) — the "what if I hadn't?" question.
"""

from __future__ import annotations

from pradyos.causality.engine import CausalEngine, CausalError

__all__ = ["CausalEngine", "CausalError"]
