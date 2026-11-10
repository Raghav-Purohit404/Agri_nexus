"""
FILE: farm_twin/voi/value_of_information.py
PURPOSE: Answer 'which measurement/experiment would most reduce decision risk per rupee?'.
IMPLEMENT:
  EVPI = E_theta[ max_d U(d, theta) ] - max_d E_theta[ U(d, theta) ]  computed on the scenario/param ensemble (decisions d = allocations from the payoff table; theta = uncertain parameter draws such as soil EC, Ksat, RUE, tau_eff): EVPI is an UPPER BOUND on what any information can be worth.
  EVSI for a specific measurement m with noise model: preposterior analysis by simulation: for j in 1..J: draw theta_j from the current posterior, simulate the measurement y_j = g(theta_j) + noise, update the posterior (importance reweighting of the ensemble: w_i propto N(y_j | g(theta_i), sigma^2)), choose d*(y_j) maximising weighted expected utility, evaluate its TRUE utility under theta_j. EVSI = mean_j U(d*(y_j), theta_j) - max_d E U(d, theta) ; net value = EVSI - cost(m).
  Candidate measurements (catalogue, editable CSV with costs in INR, noise sd, delay): soil lab test (EC, pH, texture, OC, N, P, K), saturated-paste ECe at depth, irrigation-water analysis, soil-moisture probe network, weather station, ceptometer/PAR survey under panels, test strip trial (crop under panel vs open), yield sampling plots, infiltration test.
  Ranking output: table(measurement, EVSI, cost, net value, ROI, time-to-information) + 'recommended first measurement' + data-quality improvements it would unlock.
  Efficient approximation: because the payoff table is already simulated, preposterior reweighting needs no new simulations.
TESTS: EVPI = 0 when one decision dominates in all draws; EVSI <= EVPI; perfect-information measurement (sigma->0) approaches EVPI.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class VOIResult:
    evpi: float
    evsi: float
    cost: float
    net_value: float
    roi: float


def evpi(utilities: np.ndarray, probabilities: np.ndarray | None = None) -> float:
    u = np.asarray(utilities, float)
    if u.ndim != 2 or not np.isfinite(u).all():
        raise ValueError("utilities must be finite [decision, parameter draw]")
    p = np.full(u.shape[1], 1 / u.shape[1]) if probabilities is None else np.asarray(probabilities, float)
    if p.shape != (u.shape[1],) or np.any(p < 0) or not np.isclose(p.sum(), 1):
        raise ValueError("invalid draw probabilities")
    return float(np.dot(p, np.max(u, axis=0)) - np.max(u @ p))


def evsi(
    utilities: np.ndarray,
    measurement_by_draw: np.ndarray,
    noise_sd: float,
    rng: np.random.Generator,
    probabilities: np.ndarray | None = None,
    replicates: int = 500,
) -> float:
    u = np.asarray(utilities, float)
    g = np.asarray(measurement_by_draw, float)
    if u.ndim != 2 or g.shape != (u.shape[1],) or noise_sd < 0 or replicates < 1:
        raise ValueError("invalid EVSI inputs")
    p = np.full(u.shape[1], 1 / u.shape[1]) if probabilities is None else np.asarray(probabilities, float)
    baseline = float(np.max(u @ p))
    posterior_value = 0.0
    for _ in range(replicates):
        truth = int(rng.choice(len(g), p=p))
        y = g[truth] + rng.normal(0, noise_sd)
        if noise_sd == 0:
            w = np.zeros(len(g))
            w[truth] = 1.0
        else:
            logw = -0.5 * ((y - g) / noise_sd) ** 2 + np.log(np.maximum(p, 1e-300))
            logw -= logw.max()
            w = np.exp(logw)
            w /= w.sum()
        decision = int(np.argmax(u @ w))
        posterior_value += u[decision, truth]
    return float(posterior_value / replicates - baseline)


def value_of_information(
    utilities: np.ndarray,
    measurement_by_draw: np.ndarray,
    noise_sd: float,
    cost: float,
    rng: np.random.Generator,
    probabilities: np.ndarray | None = None,
    replicates: int = 500,
) -> VOIResult:
    perfect = evpi(utilities, probabilities)
    partial = min(perfect, max(0.0, evsi(utilities, measurement_by_draw, noise_sd, rng, probabilities, replicates)))
    net = partial - cost
    return VOIResult(perfect, partial, cost, net, partial / cost if cost > 0 else float("inf"))
