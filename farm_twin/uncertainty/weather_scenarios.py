"""
FILE: farm_twin/uncertainty/weather_scenarios.py
PURPOSE: Generate joint weather scenario ensembles for 1-season and 10-year horizons. Weather is the dominant risk in arid rainfed/irrigated systems.

IMPLEMENT (selectable):
  1. HISTORICAL_REPLAY: each historical year (e.g. 1990-2025) is one scenario (preserves inter-variable correlation; N ~ 35). Default for season-level decisions.
  2. BLOCK_BOOTSTRAP for multi-year horizons: sample years with replacement (or monthly blocks of 15-30 days, preserving intra-season persistence), concatenate; N=200-1000.
  3. PARAMETRIC GENERATOR (when long records absent): first-order two-state Markov chain for rain occurrence (p01, p11 per month), gamma (or mixed-exponential) distribution for wet-day amounts (shape, scale per month), temperatures from a multivariate normal conditioned on wet/dry state with monthly means/covariances and lag-1 autocorrelation (WGEN-type: residual AR(1) of standardised Tmax, Tmin, Rs). Fit by method of moments/MLE per month; verify generated statistics (mean annual rain, wet-day freq, dry-spell length distribution, Tmax/Tmin means) against the observed within tolerances (mean annual rain +/-10 %, dry-spell P90 +/-15 %).
  4. CLIMATE_SHIFT: apply delta factors (monsoon rain scale, +dT, heat-wave frequency multiplier) to any of the above; scenarios labelled explicitly; never presented as forecasts.
  5. SEASONAL FORECAST conditioning (optional): if an IMD/ECMWF tercile forecast is supplied, reweight historical years by analog similarity (e.g. ENSO/IOD state) with weights bounded [0.5,2] - flagged experimental.
  OUTPUT: WeatherScenarioSet(scenarios: array[N, T, vars], year_labels, method, fit_diagnostics, seed). Shared across plots (spatially identical at farm scale) and shared across candidate plans (common random numbers).
TESTS: Markov chain reproduces wet-day frequency; generator diagnostics; replay count; CRN identical across plans.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence
import numpy as np


class WeatherMethod(str, Enum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    BLOCK_BOOTSTRAP = "BLOCK_BOOTSTRAP"
    PARAMETRIC = "PARAMETRIC"
    CLIMATE_SHIFT = "CLIMATE_SHIFT"


@dataclass(frozen=True)
class WeatherScenarioSet:
    scenarios: np.ndarray
    year_labels: tuple[str, ...]
    variables: tuple[str, ...]
    method: WeatherMethod
    seed: int
    fit_diagnostics: Mapping[str, float]


def historical_replay(
    data: np.ndarray, years: Sequence[str], variables: Sequence[str], seed: int = 0
) -> WeatherScenarioSet:
    x = np.asarray(data, float)
    if x.ndim != 3 or x.shape[0] != len(years) or x.shape[2] != len(variables):
        raise ValueError("expected array [year, day, variable]")
    return WeatherScenarioSet(
        x.copy(),
        tuple(map(str, years)),
        tuple(variables),
        WeatherMethod.HISTORICAL_REPLAY,
        seed,
        {"scenario_count": float(len(years))},
    )


def block_bootstrap(
    data: np.ndarray,
    years: Sequence[str],
    variables: Sequence[str],
    n: int,
    rng: np.random.Generator,
    block_years: int = 1,
    seed: int = 0,
) -> WeatherScenarioSet:
    x = np.asarray(data, float)
    if x.ndim != 3 or n < 1 or block_years < 1:
        raise ValueError("invalid bootstrap dimensions")
    indexes = []
    for _ in range(n):
        picks = []
        while len(picks) < x.shape[0]:
            start = int(rng.integers(0, x.shape[0]))
            picks.extend((start + j) % x.shape[0] for j in range(block_years))
        indexes.append(picks[: x.shape[0]])
    samples = x[np.asarray(indexes)].reshape(n, -1, x.shape[2])
    return WeatherScenarioSet(
        samples,
        tuple(f"bootstrap-{i}" for i in range(n)),
        tuple(variables),
        WeatherMethod.BLOCK_BOOTSTRAP,
        seed,
        {"scenario_count": float(n)},
    )


def climate_shift(
    data: np.ndarray,
    variables: Sequence[str],
    *,
    temperature_delta_c: float = 0.0,
    rain_scale: float = 1.0,
    seed: int = 0,
) -> np.ndarray:
    if rain_scale < 0:
        raise ValueError("rain_scale must be non-negative")
    out = np.array(data, float, copy=True)
    for i, name in enumerate(variables):
        if name.lower() in {"tmin", "tmax", "temperature"}:
            out[..., i] += temperature_delta_c
        if name.lower() in {"rain", "precipitation", "pr"}:
            out[..., i] *= rain_scale
    return out


def generate_parametric_weather(
    n_scenarios: int,
    days: int,
    monthly: Mapping[str, np.ndarray],
    rng: np.random.Generator,
    observed_diagnostics: Mapping[str, float] | None = None,
    seed: int = 0,
) -> WeatherScenarioSet:
    """Generate daily rain and weather using user-fitted monthly WGEN parameters.

    Parameters use month-indexed arrays: p01, p11, gamma_shape, gamma_scale,
    means [12,3] for Tmax/Tmin/Rs, covariance [12,3,3], and AR1 [12].
    This routine intentionally does not supply regional defaults or assert forecast skill.
    """
    if n_scenarios < 1 or days < 1:
        raise ValueError("scenario and day counts must be positive")
    required = {"p01", "p11", "gamma_shape", "gamma_scale", "means", "covariance", "ar1"}
    missing = required - set(monthly)
    if missing:
        raise ValueError(f"WGEN parameter set missing {sorted(missing)}")
    arrays = {key: np.asarray(value, dtype=float) for key, value in monthly.items()}
    for key in ("p01", "p11", "gamma_shape", "gamma_scale", "ar1"):
        if arrays[key].shape != (12,):
            raise ValueError(f"{key} must have 12 monthly values")
    if arrays["means"].shape != (12, 3) or arrays["covariance"].shape != (12, 3, 3):
        raise ValueError("means and covariance must have shapes [12,3] and [12,3,3]")
    if np.any((arrays["p01"] < 0) | (arrays["p01"] > 1)) or np.any((arrays["p11"] < 0) | (arrays["p11"] > 1)):
        raise ValueError("wet-day transition probabilities must be in [0,1]")
    if np.any(arrays["gamma_shape"] <= 0) or np.any(arrays["gamma_scale"] <= 0) or np.any(np.abs(arrays["ar1"]) >= 1):
        raise ValueError("gamma parameters must be positive and AR1 must be stationary")
    scenarios = np.zeros((n_scenarios, days, 4), dtype=float)
    month_index = np.minimum(11, np.arange(days) * 12 // days)
    for scenario in range(n_scenarios):
        wet = False
        residual = np.zeros(3)
        for day, month in enumerate(month_index):
            prob = arrays["p11"][month] if wet else arrays["p01"][month]
            wet = bool(rng.random() < prob)
            rain = float(rng.gamma(arrays["gamma_shape"][month], arrays["gamma_scale"][month])) if wet else 0.0
            residual = arrays["ar1"][month] * residual + rng.multivariate_normal(np.zeros(3), arrays["covariance"][month])
            scenarios[scenario, day, 0] = arrays["means"][month, 0] + residual[0]
            scenarios[scenario, day, 1] = arrays["means"][month, 1] + residual[1]
            scenarios[scenario, day, 2] = rain
            scenarios[scenario, day, 3] = max(0.0, arrays["means"][month, 2] + residual[2])
    wet_freq = float(np.mean(scenarios[:, :, 2] > 0))
    annual_rain = float(np.mean(scenarios[:, :, 2].sum(axis=1)))
    diagnostics = {"generated_wet_day_fraction": wet_freq, "generated_period_rain_mm": annual_rain}
    if observed_diagnostics:
        for key, value in observed_diagnostics.items():
            if key not in diagnostics or not np.isfinite(value):
                continue
            diagnostics[f"relative_error_{key}"] = abs(diagnostics[key] - value) / max(abs(value), 1e-12)
    return WeatherScenarioSet(
        scenarios,
        tuple(f"wgen-{i}" for i in range(n_scenarios)),
        ("tmax_c", "tmin_c", "rain_mm", "rs_mj_m2"),
        WeatherMethod.PARAMETRIC,
        seed,
        diagnostics,
    )
