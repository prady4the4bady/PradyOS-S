"""Phase 106 — Sovereign Moment Sketch (Gan, Ding, Tai, Sheng, Bailis & Madden, 2018).

A **mergeable quantile sketch** that summarises a stream by its first ``k``
*power-sum moments* ``C[i] = Σ xⁱ`` (``i = 0 .. k-1``) together with the observed
``min`` / ``max``. Quantiles are *not* stored — they are reconstructed at query
time by fitting a **maximum-entropy (MaxEnt)** distribution to the moments: among
all densities on ``[min, max]`` whose moments match the observed ones, the
maximum-entropy choice is

    p(x) ∝ exp(Σ_j λ_j · xⁿ_j)

where ``xⁿ`` is ``x`` rescaled to ``[-1, 1]`` (Chebyshev domain — far better
conditioned than raw powers) and the Lagrange multipliers ``λ`` are solved so the
fitted moments match the empirical ones. We minimise the dual potential

    L(λ) = log ∫ exp(Σ_j λ_j xʲ) dx − Σ_j λ_j μ_j

(``μ`` = normalised empirical moments ``C[j]/C[0]`` in the rescaled domain) with
``scipy.optimize.minimize`` (L-BFGS-B); its gradient is ``fitted_moment − μ``.
``quantile(q)`` then integrates the fitted density to a CDF and inverts it via
bisection to find ``v`` with ``CDF(v) = q``.

Moments are **trivially mergeable** — element-wise addition of the power sums and
``min`` / ``max`` of the bounds — so distributed partitions combine in constant
time. Fully deterministic (no randomness; the ``seed`` is carried for API parity
with the other sovereign sketches). Thread-safe via a single ``threading.Lock``.

Requires :mod:`numpy` / :mod:`scipy` (declared in ``pyproject.toml``).
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
from scipy import integrate, optimize
from scipy.integrate import trapezoid


class MomentSketchError(Exception):
    """Raised for an invalid Moment-Sketch configuration / operation. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class MomentSketch:
    """Power-sum moment sketch with maximum-entropy quantile reconstruction."""

    _GRID = 200  # quadrature / CDF-inversion grid resolution on [-1, 1]

    def __init__(self, k: int = 15, seed: int = 0) -> None:
        self._validate(k, seed)
        self._k = k
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(k: Any, seed: Any) -> None:
        if not _is_pos_int(k):
            raise MomentSketchError(k)
        if not _is_int(seed):
            raise MomentSketchError(seed)

    def _init_state(self) -> None:
        self._C = [0.0] * self._k
        self._min: float | None = None
        self._max: float | None = None

    # ── ingestion ────────────────────────────────────────────────────────────────────
    def add(self, x: float) -> None:
        """Add a single value ``x``; updates each power sum and the min / max bounds."""
        if not _is_number(x):
            raise MomentSketchError(x)
        xf = float(x)
        with self._lock:
            p = 1.0
            for i in range(self._k):
                self._C[i] += p
                p *= xf
            self._min = xf if self._min is None else min(self._min, xf)
            self._max = xf if self._max is None else max(self._max, xf)

    def add_many(self, values: Any) -> None:
        """Add every value in an iterable (validates each)."""
        try:
            seq = list(values)
        except TypeError as exc:
            raise MomentSketchError(values) from exc
        for v in seq:
            self.add(v)

    # ── MaxEnt machinery (pure, operates on a snapshot) ────────────────────────────────
    def _rescale(self, x: np.ndarray) -> np.ndarray:
        """Map raw values in ``[min, max]`` to the Chebyshev domain ``[-1, 1]``."""
        lo, hi = self._min, self._max
        if hi <= lo:
            return np.zeros_like(x)
        return 2.0 * (x - lo) / (hi - lo) - 1.0

    def _empirical_scaled_moments(self) -> np.ndarray:
        """Normalised moments ``E[xʲ]`` in the rescaled ``[-1, 1]`` domain, ``j = 0..k-1``.

        Computed from the raw power sums via the binomial expansion of
        ``((2x - (lo+hi)) / (hi-lo))ʲ`` so no re-scan of the data is needed."""
        n = self._C[0]
        lo, hi = self._min, self._max
        raw = np.array(self._C, dtype=float) / n  # E[x^i], raw domain
        if hi <= lo:  # degenerate: single value
            mu = np.zeros(self._k)
            mu[0] = 1.0
            return mu
        a = 2.0 / (hi - lo)
        b = -(hi + lo) / (hi - lo)  # scaled = a*x + b
        mu = np.zeros(self._k)
        for j in range(self._k):
            # E[(a x + b)^j] = Σ_m C(j,m) a^m b^(j-m) E[x^m]
            acc = 0.0
            for m in range(j + 1):
                acc += _binom(j, m) * (a**m) * (b ** (j - m)) * raw[m]
            mu[j] = acc
        return mu

    def _fit_lambdas(self, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Solve for MaxEnt multipliers; return ``(lambdas, grid, density_on_grid)``."""
        grid = np.linspace(-1.0, 1.0, self._GRID)
        # Vandermonde of powers x^0..x^(k-1) on the grid.
        powers = np.vstack([grid**j for j in range(self._k)])  # (k, GRID)

        def neg_dual(lam: np.ndarray):
            z_density = np.exp(powers.T @ lam)  # (GRID,)
            zint = trapezoid(z_density, grid)
            if not np.isfinite(zint) or zint <= 0:
                return 1e12, np.zeros_like(lam)
            logz = np.log(zint)
            obj = logz - lam @ mu
            # gradient_j = E_fit[x^j] - mu_j
            fitted = (
                np.array([trapezoid(powers[j] * z_density, grid) for j in range(self._k)]) / zint
            )
            return obj, fitted - mu

        lam0 = np.zeros(self._k)
        res = optimize.minimize(
            neg_dual, lam0, jac=True, method="L-BFGS-B", options={"maxiter": 500, "ftol": 1e-10}
        )
        lam = res.x
        density = np.exp(powers.T @ lam)
        zint = trapezoid(density, grid)
        if not np.isfinite(zint) or zint <= 0:
            density = np.ones_like(grid)
            zint = np.trapz(density, grid)
        density = density / zint
        return lam, grid, density

    # ── query ──────────────────────────────────────────────────────────────────────────
    def quantile(self, q: float) -> float:
        """Return value ``v`` with ``CDF(v) = q`` (``q`` strictly in (0, 1)) via MaxEnt fit."""
        if not _is_number(q) or not (0.0 < q < 1.0):
            raise MomentSketchError(q)
        with self._lock:
            if self._C[0] <= 0:
                raise MomentSketchError("empty")
            lo, hi = self._min, self._max
            if hi <= lo:  # all identical values
                return float(lo)
            mu = self._empirical_scaled_moments()
            _, grid, density = self._fit_lambdas(mu)
        # Build CDF on the grid and invert by interpolation (scaled domain → raw).
        cdf = integrate.cumulative_trapezoid(density, grid, initial=0.0)
        cdf = cdf / cdf[-1]
        scaled_v = float(np.interp(q, cdf, grid))
        raw_v = lo + (scaled_v + 1.0) * (hi - lo) / 2.0
        return float(min(max(raw_v, lo), hi))

    # ── merge / lifecycle ────────────────────────────────────────────────────────────────
    def merge(self, other: MomentSketch) -> MomentSketch:
        """Merge ``other`` (same ``k``) in: element-wise power-sum add, min/max of bounds."""
        if not isinstance(other, MomentSketch):
            raise MomentSketchError(other)
        with other._lock:
            if other._k != self._k:
                raise MomentSketchError(other._k)
            o_C = list(other._C)
            o_min, o_max = other._min, other._max
        with self._lock:
            for i in range(self._k):
                self._C[i] += o_C[i]
            if o_min is not None:
                self._min = o_min if self._min is None else min(self._min, o_min)
            if o_max is not None:
                self._max = o_max if self._max is None else max(self._max, o_max)
        return self

    def merge_state(self, state: dict) -> MomentSketch:
        """Merge a serialized state dict (``{k, moments, min_val, max_val}``) in."""
        if not isinstance(state, dict):
            raise MomentSketchError(state)
        other = MomentSketch.from_state(state)
        return self.merge(other)

    @classmethod
    def from_state(cls, state: dict) -> MomentSketch:
        """Reconstruct a sketch from a serialized ``stats()``-style state dict."""
        if not isinstance(state, dict) or "moments" not in state:
            raise MomentSketchError(state)
        moments = state["moments"]
        if not isinstance(moments, list | tuple) or len(moments) < 1:
            raise MomentSketchError(moments)
        sk = cls(k=len(moments), seed=int(state.get("seed", 0)))
        sk._C = [float(m) for m in moments]
        mn, mx = state.get("min_val"), state.get("max_val")
        sk._min = None if mn is None else float(mn)
        sk._max = None if mx is None else float(mx)
        return sk

    def reset(self, k: int | None = None, seed: int | None = None) -> None:
        """Clear all moments / bounds; optionally reconfigure ``k`` / ``seed``."""
        with self._lock:
            nk = self._k if k is None else k
            ns = self._seed if seed is None else seed
            self._validate(nk, ns)
            self._k, self._seed = nk, ns
            self._init_state()

    def __len__(self) -> int:
        with self._lock:
            return int(self._C[0])

    @property
    def k(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def total_count(self) -> float:
        with self._lock:
            return self._C[0]

    def stats(self) -> dict:
        """Summary: ``k`` / ``total_count`` (= C[0]) / ``min_val`` / ``max_val`` /
        ``moments`` (the list of ``k`` power sums)."""
        with self._lock:
            return {
                "k": self._k,
                "seed": self._seed,
                "total_count": self._C[0],
                "min_val": self._min,
                "max_val": self._max,
                "moments": list(self._C),
            }


def _binom(n: int, r: int) -> float:
    """Binomial coefficient C(n, r) as a float (small n; avoids importing math.comb churn)."""
    if r < 0 or r > n:
        return 0.0
    r = min(r, n - r)
    num = 1.0
    for i in range(r):
        num = num * (n - i) / (i + 1)
    return num
