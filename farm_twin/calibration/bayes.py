"""
FILE: farm_twin/calibration/bayes.py
PURPOSE: Posterior estimation for the hierarchy using methods suited to expensive simulators with few observations.

METHODS (selectable, default first):
  1. Ensemble MCMC (affine-invariant, `emcee` allowed as dependency) over the <= 8 parameters of one level at a time (conditional on parent posterior means; 'sequential' hierarchical updating), 32+ walkers, 2,000+ steps, convergence by R-hat < 1.05 and ESS > 400; simulator calls are cheap enough (<10 ms/season vectorised) to run 100k evaluations.
  2. Approximate Bayesian Computation SMC (when likelihood is awkward, e.g. only season yield observed): distance = normalised RMSE across observed variables; tolerance schedule by quantiles.
  3. GLUE (informal likelihood) ONLY as a diagnostic, never for promotion.
  LIKELIHOOD: Gaussian on transformed outputs with observation error sigma_m = sqrt(sigma_meas^2 + sigma_struct^2); sigma_struct estimated (inverse-gamma prior) - captures model discrepancy; yield: relative error; soil moisture: sensor error (typ. 0.02-0.03 m3/m3) ; satellite fcover: mixed-pixel inflated error; EC: log-normal.
  OUTPUT: PosteriorSample (draws, summary, diagnostics), written to parameter_set(posterior). Draws are what the engine propagates (param_draws).
  GUARDS: reject fits if prior-posterior overlap suggests prior-data conflict (prior predictive check p<0.01) and flag for expert review rather than silently widening.
TESTS: recover known parameters from synthetic data (twin experiment) within 95 % intervals in >= 90 % of 100 trials (calibration coverage test); R-hat computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import numpy as np


@dataclass(frozen=True)
class PosteriorSample:
    draws: np.ndarray
    weights: np.ndarray
    method: str
    diagnostics: dict[str, float]
    promotion_eligible: bool = False


def importance_posterior(
    prior_draws: np.ndarray, log_likelihood: Callable[[np.ndarray], float], method: str = "importance"
) -> PosteriorSample:
    draws = np.asarray(prior_draws, float)
    if draws.ndim != 2 or not len(draws) or not np.isfinite(draws).all():
        raise ValueError("prior draws must be a finite [sample, parameter] matrix")
    logw = np.asarray([log_likelihood(row) for row in draws], float)
    if not np.isfinite(logw).any():
        raise ValueError("all prior draws have zero/non-finite likelihood")
    logw -= np.nanmax(logw)
    weights = np.exp(logw)
    weights /= weights.sum()
    ess = float(1 / np.sum(weights**2))
    return PosteriorSample(
        draws, weights, method, {"effective_sample_size": ess, "weight_max": float(weights.max())}, False
    )


def split_rhat(chains: np.ndarray) -> np.ndarray:
    """Split-chain Gelman-Rubin R-hat; input [chain, draw, parameter]."""
    x = np.asarray(chains, float)
    if x.ndim != 3 or x.shape[0] < 2 or x.shape[1] < 4:
        raise ValueError("R-hat requires >=2 chains and >=4 draws")
    half = x.shape[1] // 2
    split = np.concatenate((x[:, :half, :], x[:, -half:, :]), axis=0)
    n = split.shape[1]
    means = split.mean(axis=1)
    between = n * means.var(axis=0, ddof=1)
    within = split.var(axis=1, ddof=1).mean(axis=0)
    return np.sqrt(((n - 1) / n * within + between / n) / within)


def posterior_conflict(prior_predictive_p_value: float, threshold: float = 0.01) -> bool:
    if not 0 <= prior_predictive_p_value <= 1:
        raise ValueError("p-value must be in [0,1]")
    return prior_predictive_p_value < threshold


def emcee_posterior(
    log_probability: Callable[[np.ndarray], float], initial: np.ndarray, *,
    steps: int = 2000, burn_in: int | None = None, seed: int = 0,
) -> PosteriorSample:
    """Run affine-invariant ensemble MCMC for a small parameter block.

    Returns posterior draws and conservative diagnostics. A run is merely a
    candidate: thresholds do not replace the independent promotion gate.
    """
    try:
        import emcee
    except ImportError as exc:
        raise RuntimeError("Install the learning extra to use ensemble MCMC") from exc
    center = np.asarray(initial, float).ravel()
    ndim = len(center)
    if not 1 <= ndim <= 8 or not np.isfinite(center).all():
        raise ValueError("initial vector must contain 1-8 finite parameters")
    if steps < 100:
        raise ValueError("steps must be >= 100")
    nwalkers = max(32, 4 * ndim)
    rng = np.random.default_rng(seed)
    positions = center + rng.normal(0, 1e-4, size=(nwalkers, ndim))
    sampler = emcee.EnsembleSampler(nwalkers, ndim, log_probability)
    sampler.run_mcmc(positions, steps, progress=False)
    discard = min(steps - 1, burn_in if burn_in is not None else steps // 2)
    chains = sampler.get_chain(discard=discard, flat=False)
    flattened = sampler.get_chain(discard=discard, flat=True)
    try:
        # emcee's integrated autocorrelation estimate is unavailable for short chains.
        tau = np.asarray(sampler.get_autocorr_time(discard=discard, quiet=True), float)
        ess = float(nwalkers * len(chains[0]) / np.max(tau))
    except Exception:
        ess = 0.0
    try:
        # Use split R-hat with walkers as chains and parameter dimensions intact.
        rhat_values = split_rhat(np.transpose(chains, (1, 0, 2)))
        rhat_max = float(np.max(rhat_values))
    except (ValueError, FloatingPointError):
        rhat_max = float("inf")
    diagnostics = {"rhat_max": rhat_max, "effective_sample_size": ess,
                   "acceptance_fraction": float(np.mean(sampler.acceptance_fraction))}
    eligible = rhat_max < 1.05 and ess > 400
    return PosteriorSample(flattened, np.full(len(flattened), 1 / len(flattened)), "emcee", diagnostics, eligible)


def abc_quantile_rejection(
    prior_sampler: Callable[[np.random.Generator, int], np.ndarray],
    simulator_summary: Callable[[np.ndarray], np.ndarray], observed_summary: np.ndarray, *,
    particles: int = 500, rounds: int = 4, quantile: float = 0.5, seed: int = 0,
) -> PosteriorSample:
    """ABC rejection with a sequential quantile tolerance schedule.

    This is deliberately identified as quantile rejection, not full ABC-SMC:
    prior proposals are independent and weights are uniform. It cannot
    authorize promotion by itself.
    """
    if particles < 20 or rounds < 1 or not 0 < quantile < 1:
        raise ValueError("invalid ABC-SMC controls")
    observed = np.asarray(observed_summary, float).ravel()
    if not len(observed) or not np.isfinite(observed).all():
        raise ValueError("observed summary must be finite and non-empty")
    rng = np.random.default_rng(seed)
    candidates = np.asarray(prior_sampler(rng, particles), float)
    if candidates.ndim != 2 or len(candidates) != particles or not np.isfinite(candidates).all():
        raise ValueError("prior_sampler must return a finite [particles, parameters] matrix")
    summaries = np.asarray([np.asarray(simulator_summary(row), float).ravel() for row in candidates])
    if summaries.shape[1:] != observed.shape or not np.isfinite(summaries).all():
        raise ValueError("simulator summaries must match observed summary dimensions")
    scale = np.maximum(np.std(summaries, axis=0, ddof=1), 1e-12)
    distances = np.sqrt(np.mean(((summaries - observed) / scale) ** 2, axis=1))
    tolerances = []
    accepted = np.ones(particles, dtype=bool)
    for _ in range(rounds):
        tolerance = float(np.quantile(distances[accepted], quantile))
        tolerances.append(tolerance)
        accepted &= distances <= tolerance
        if not accepted.any():
            break
    draws = candidates[accepted]
    if not len(draws):
        raise ValueError("ABC tolerance sequence accepted no particles")
    return PosteriorSample(draws, np.full(len(draws), 1 / len(draws)), "abc_quantile_rejection",
                           {"final_tolerance": tolerances[-1], "accepted": float(len(draws)),
                            "prior_particles": float(particles)}, False)
