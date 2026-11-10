"""
FILE: farm_twin/optimization/multi_year.py
PURPOSE: 10-year investment/timing problem (sequence of decisions), solved as multi-stage with scenario trees reduced to a manageable size; Level 1 approximation = rolling horizon with re-optimisation.
IMPLEMENT: (1) capex timing: option 'install PV on plot A in year t' for t in 0..H (binary y[a,t]); budget by year with reinvestment of free cashflow (state variable cash_t tracked by scenario with linking constraints: cash_{t+1,s} = cash_{t,s} + CF_{t,s}(x,y) - repayments; cash_{t,s} >= 0 or borrowing at cost); non-anticipativity only for stage-1 decisions (here-and-now), later years decided by policy rules (e.g. install in year t if cash >= threshold) tested by simulation - the "decision rule" approach avoids a full scenario tree. (2) rolling horizon: at each annual review, update state with observed outcomes, re-run optimiser from that state (this is what the feedback loop does). (3) soil trajectory coupling: option payoffs depend on soil state at time t (reclamation first, then high-value crops) -> encode as option SEQUENCES (pre-simulated sequences of 3-5 years) rather than per-year binary decisions.
OUTPUT: StagedPlan(year -> decisions, trigger rules, expected cash path quantiles, regret table vs hindsight).
TESTS: with deterministic scenario the staged plan equals the simple NPV-optimal timing; non-anticipativity respected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np


@dataclass(frozen=True)
class StagedPlan:
    install_year: int
    decisions: tuple[bool, ...]
    expected_cash_path: tuple[float, ...]
    scenario_cash_paths: np.ndarray
    expected_npv: float
    trigger: str


def choose_install_year(
    cashflows_by_install_year: np.ndarray,
    capex: Sequence[float],
    discount_rate: float,
    horizon_years: int,
    starting_cash: float = 0.0,
) -> StagedPlan:
    """Choose one install year from pre-simulated annual cashflow paths, preserving a common first-stage choice."""
    paths = np.asarray(cashflows_by_install_year, float)
    costs = np.asarray(capex, float)
    if paths.ndim != 3:
        raise ValueError("cashflows must be [install_year, scenario, year]")
    n_years, n_scenarios, n_horizon = paths.shape
    if n_years != len(costs) or horizon_years > n_horizon or not 0 <= discount_rate:
        raise ValueError("inconsistent horizon, CAPEX, or discount rate")
    discount = (1 + discount_rate) ** np.arange(horizon_years + 1)
    values = []
    cash_paths = []
    for t in range(n_years):
        cf = paths[t, :, :horizon_years].copy()
        cf[:, 0] -= costs[t]
        npvs = (cf / discount[1:]).sum(axis=1)
        values.append(float(npvs.mean()))
        cash = starting_cash + np.cumsum(cf, axis=1)
        cash_paths.append(cash)
    best = int(np.argmax(values))
    decision = tuple(i == best for i in range(n_years))
    mean_path = np.mean(cash_paths[best], axis=0)
    return StagedPlan(
        best,
        decision,
        tuple(map(float, mean_path)),
        cash_paths[best],
        values[best],
        "install at selected year; later decisions require annual re-optimisation",
    )
