"""
FILE: farm_twin/calibration/metrics.py
PURPOSE: Scoring functions. IMPLEMENT (numpy): rmse, mae, bias, nse = 1 - sum((o-p)^2)/sum((o-mean(o))^2), kge = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2) (alpha = sd_p/sd_o, beta = mean_p/mean_o), d_index (Willmott), crps_ensemble(samples, obs) = mean|X-y| - 0.5*mean|X-X'| (fair/unbiased variant for finite ensembles), interval_coverage(lo, hi, obs), pit_values, reliability_diagram bins, pinball loss for quantiles, relative errors for yield (%), r2. All handle NaN by pairwise deletion and return n used.
TESTS: hand-computed small arrays; CRPS of a point mass equals MAE.
"""

from __future__ import annotations

from typing import Any
import numpy as np


def _pair(a: Any, b: Any) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.asarray(a, dtype=float).ravel(), np.asarray(b, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError("inputs must have equal shape")
    ok = np.isfinite(x) & np.isfinite(y)
    return x[ok], y[ok]


def _scores(obs: Any, pred: Any) -> tuple[dict[str, float], int]:
    o, p = _pair(obs, pred)
    n = len(o)
    if not n:
        return {k: float("nan") for k in ("rmse", "mae", "bias", "nse", "kge", "d_index", "r2")}, 0
    e = p - o
    rmse = float(np.sqrt(np.mean(e * e)))
    denom = float(np.sum((o - np.mean(o)) ** 2))
    nse = float(1 - np.sum(e * e) / denom) if denom > 0 else float("nan")
    r = float(np.corrcoef(o, p)[0, 1]) if n > 1 and np.std(o) and np.std(p) else float("nan")
    alpha = float(np.std(p, ddof=1) / np.std(o, ddof=1)) if n > 1 and np.std(o, ddof=1) else float("nan")
    beta = float(np.mean(p) / np.mean(o)) if np.mean(o) else float("nan")
    kge = float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))
    dden = float(np.sum((np.abs(p - np.mean(o)) + np.abs(o - np.mean(o))) ** 2))
    dindex = float(1 - np.sum(e * e) / dden) if dden else float("nan")
    return {
        "rmse": rmse,
        "mae": float(np.mean(np.abs(e))),
        "bias": float(np.mean(e)),
        "nse": nse,
        "kge": kge,
        "d_index": dindex,
        "r2": r * r,
    }, n


def rmse(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["rmse"], _scores(obs, pred)[1]


def mae(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["mae"], _scores(obs, pred)[1]


def bias(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["bias"], _scores(obs, pred)[1]


def nse(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["nse"], _scores(obs, pred)[1]


def kge(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["kge"], _scores(obs, pred)[1]


def d_index(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["d_index"], _scores(obs, pred)[1]


def r2(obs: Any, pred: Any) -> tuple[float, int]:
    return _scores(obs, pred)[0]["r2"], _scores(obs, pred)[1]


def crps_ensemble(samples: Any, obs: float) -> float:
    x = np.asarray(samples, dtype=float).ravel()
    x = x[np.isfinite(x)]
    if not len(x) or not np.isfinite(obs):
        return float("nan")
    return float(np.mean(np.abs(x - obs)) - 0.5 * np.mean(np.abs(x[:, None] - x[None, :])))


def interval_coverage(lo: Any, hi: Any, obs: Any) -> tuple[float, int]:
    lower, upper, observed = (
        np.asarray(lo, float).ravel(),
        np.asarray(hi, float).ravel(),
        np.asarray(obs, float).ravel(),
    )
    if not (lower.shape == upper.shape == observed.shape):
        raise ValueError("inputs must have equal shape")
    ok = np.isfinite(lower) & np.isfinite(upper) & np.isfinite(observed)
    return (
        float(np.mean((observed[ok] >= lower[ok]) & (observed[ok] <= upper[ok]))) if np.any(ok) else float("nan"),
        int(ok.sum()),
    )


def pit_values(samples: Any, obs: Any) -> np.ndarray:
    x, y = np.asarray(samples, float), np.asarray(obs, float).ravel()
    if x.ndim != 2 or x.shape[1] != len(y):
        raise ValueError("samples must have shape (ensemble, observations)")
    return np.mean(x <= y[None, :], axis=0)


def pinball_loss(obs: Any, pred: Any, quantile: float) -> tuple[float, int]:
    if not 0 < quantile < 1:
        raise ValueError("quantile must be in (0,1)")
    o, p = _pair(obs, pred)
    e = o - p
    return float(np.mean(np.maximum(quantile * e, (quantile - 1) * e)) if len(e) else float("nan")), len(e)
