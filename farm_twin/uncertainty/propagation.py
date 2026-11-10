"""
FILE: farm_twin/uncertainty/propagation.py
PURPOSE: Monte Carlo over THREE uncertainty sources, kept separate so reports can attribute variance: (A) weather (aleatory), (B) parameter/structural (epistemic; posterior draws), (C) economic (prices, tariffs, costs).
IMPLEMENT: sample_params(parameter_set, n, rng) (posterior draws or prior if not calibrated), sample_prices(price_model, n, rng, corr_with_yield), joint_runs(scenario, n_weather, n_param, n_price, rng) with a budget cap: total sims = n_weather x n_param (default 50 x 20 = 1000) but economics post-processing is cheap so n_price may be larger. Variance decomposition by nested ANOVA (law of total variance): Var(Y) = E[Var(Y|weather)] + Var(E[Y|weather]) etc. Latin hypercube sampling for parameters (scipy.stats.qmc), Sobol sequence for economics.
 Output summaries: mean, sd, quantiles (5,25,50,75,95), P(Y<threshold), CVaR; ALWAYS return samples for downstream optimisation.
 Convergence diagnostic: bootstrap SE of mean and of 5th percentile; auto-increase N until relative SE < 2 % (cap).
TESTS: variance decomposition sums to total on synthetic additive model; LHS marginals uniform.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import numpy as np


@dataclass(frozen=True)
class EnsembleSummary:
    mean: float
    sd: float
    quantiles: dict[str, float]
    probability_below_threshold: float | None
    cvar: float
    samples: np.ndarray
    variance_components: dict[str, float]


def summarize(samples: np.ndarray, threshold: float | None = None, alpha: float = 0.95) -> EnsembleSummary:
    x = np.asarray(samples, float).ravel()
    x = x[np.isfinite(x)]
    if not len(x):
        raise ValueError("at least one finite sample required")
    q = np.quantile(x, [0.05, 0.25, 0.5, 0.75, 0.95])
    cutoff = np.quantile(x, 1 - alpha)
    tail = x[x <= cutoff]
    return EnsembleSummary(
        float(x.mean()),
        float(x.std(ddof=1)) if len(x) > 1 else 0.0,
        dict(zip(("q05", "q25", "q50", "q75", "q95"), map(float, q))),
        None if threshold is None else float(np.mean(x < threshold)),
        float(tail.mean()),
        x,
        {},
    )


def variance_decomposition(values: np.ndarray) -> dict[str, float]:
    """Balanced matrix rows=weather draws, columns=parameter draws; ANOVA total variance."""
    x = np.asarray(values, float)
    if x.ndim != 2 or min(x.shape) < 2 or not np.isfinite(x).all():
        raise ValueError("values must be a finite 2D balanced nested matrix")
    total = float(x.var(ddof=1))
    weather = float(x.mean(axis=1).var(ddof=1))
    param = float(x.mean(axis=0).var(ddof=1))
    # Components are attributed from marginal means; residual interaction is explicit.
    interaction = max(0.0, total - weather - param)
    scale = weather + param + interaction
    if scale:
        weather, param, interaction = [v * total / scale for v in (weather, param, interaction)]
    return {"weather": weather, "parameter": param, "interaction_residual": interaction, "total": total}


def joint_runs(
    simulator: Callable[[int, int, int], float],
    n_weather: int,
    n_param: int,
    n_price: int,
    rng: np.random.Generator,
    budget: int = 1000,
) -> np.ndarray:
    if min(n_weather, n_param, n_price) < 1:
        raise ValueError("sample counts must be positive")
    if n_weather * n_param > budget:
        raise ValueError("simulation budget exceeded")
    return np.asarray(
        [simulator(w, p, int(rng.integers(0, n_price))) for w in range(n_weather) for p in range(n_param)], float
    )


def sample_parameters(
    bounds: np.ndarray,
    n: int,
    rng: np.random.Generator,
    log_uniform: np.ndarray | None = None,
) -> np.ndarray:
    """Latin-hypercube draws from explicit ranges; ranges are never inferred or fabricated."""
    from scipy.stats import qmc

    b = np.asarray(bounds, dtype=float)
    if b.ndim != 2 or b.shape[1] != 2 or n < 1 or np.any(b[:, 1] <= b[:, 0]):
        raise ValueError("bounds must be finite [parameter, lower/upper] intervals")
    use_log = np.zeros(len(b), dtype=bool) if log_uniform is None else np.asarray(log_uniform, dtype=bool)
    if use_log.shape != (len(b),) or np.any(use_log & (b[:, 0] <= 0)):
        raise ValueError("log-uniform parameters require positive lower bounds")
    seed = int(rng.integers(0, 2**32 - 1))
    unit = qmc.LatinHypercube(d=len(b), seed=seed).random(n)
    result = b[:, 0] + unit * (b[:, 1] - b[:, 0])
    if np.any(use_log):
        result[:, use_log] = np.exp(np.log(b[use_log, 0]) + unit[:, use_log] * np.log(b[use_log, 1] / b[use_log, 0]))
    return result


def sample_prices(means: np.ndarray, covariance: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Joint price/tariff/cost draws with user-supplied covariance, truncated at zero."""
    mu = np.asarray(means, dtype=float)
    cov = np.asarray(covariance, dtype=float)
    if mu.ndim != 1 or cov.shape != (len(mu), len(mu)) or n < 1:
        raise ValueError("means and covariance dimensions disagree")
    if not np.isfinite(mu).all() or np.any(mu < 0):
        raise ValueError("price means must be finite and nonnegative")
    if not np.allclose(cov, cov.T, atol=1e-10) or np.linalg.eigvalsh(cov).min() < -1e-9:
        raise ValueError("economic covariance must be positive semidefinite and symmetric")
    return np.maximum(0.0, rng.multivariate_normal(mu, cov, size=n))
