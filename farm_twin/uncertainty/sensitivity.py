"""
FILE: farm_twin/uncertainty/sensitivity.py
PURPOSE: Global sensitivity analysis to show which uncertain inputs actually matter (drives data-collection priorities and value-of-information).
IMPLEMENT: Morris elementary effects (screening, r=20 trajectories) -> mu*, sigma ; Sobol first-order and total indices via Saltelli sampling (N*(2D+2) runs) with Jansen estimators: S_i = (V - 0.5*mean((f(B)-f(A_B^i))^2))/V ; ST_i = 0.5*mean((f(A)-f(A_B^i))^2)/V ; bootstrap CIs; supports vector outputs (yield, NPV, SOC change, ECe). One-at-a-time tornado for decision-makers. Parameter ranges come from priors/posteriors (log-uniform for rates).
Output table `sensitivity_report` ranking inputs (soil EC, irrigation water EC, rainfall, price, discount rate, tau_eff ...). Used by VOI (voi/sensor_value.py) and by the Planning agent's 'what to measure first' answer.
TESTS: Ishigami function: analytic S1 = (0.314, 0.442, 0), ST = (0.558, 0.442, 0.244) recovered within 0.03 with N=2^14.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import numpy as np


@dataclass(frozen=True)
class SobolResult:
    first_order: np.ndarray
    total_order: np.ndarray
    variance: float
    evaluations: int


def saltelli_samples(bounds: np.ndarray, n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    b = np.asarray(bounds, float)
    if b.ndim != 2 or b.shape[1] != 2 or np.any(b[:, 1] <= b[:, 0]) or n < 2:
        raise ValueError("invalid bounds or sample size")
    d = len(b)
    a = rng.random((n, d))
    bb = rng.random((n, d))
    width = b[:, 1] - b[:, 0]
    return b[:, 0] + a * width, b[:, 0] + bb * width


def sobol_jansen(
    function: Callable[[np.ndarray], float], bounds: np.ndarray, n: int, rng: np.random.Generator
) -> SobolResult:
    a, b = saltelli_samples(bounds, n, rng)
    ya = np.asarray([function(x) for x in a])
    yb = np.asarray([function(x) for x in b])
    variance = float(np.var(np.concatenate((ya, yb)), ddof=1))
    if variance <= 0:
        return SobolResult(np.zeros(a.shape[1]), np.zeros(a.shape[1]), variance, n * (2 * a.shape[1] + 2))
    d = a.shape[1]
    s1 = np.empty(d)
    st = np.empty(d)
    for i in range(d):
        abi = a.copy()
        abi[:, i] = b[:, i]
        yabi = np.asarray([function(x) for x in abi])
        st[i] = 0.5 * np.mean((ya - yabi) ** 2) / variance
        s1[i] = 1 - 0.5 * np.mean((yb - yabi) ** 2) / variance
    return SobolResult(s1, st, variance, n * (2 * d + 2))


def ishigami(x: np.ndarray, a: float = 7.0, b: float = 0.1) -> float:
    v = np.asarray(x, float)
    return float(np.sin(v[0]) + a * np.sin(v[1]) ** 2 + b * v[2] ** 4 * np.sin(v[0]))
