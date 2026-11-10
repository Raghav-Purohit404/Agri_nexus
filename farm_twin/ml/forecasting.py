"""Optional baseline short-horizon alert nowcasts; outputs are not crop-model forecasts."""

from __future__ import annotations
import numpy as np


def persistence_nowcast(observations: np.ndarray, horizon: int = 7) -> np.ndarray:
    values = np.asarray(observations, float)
    if horizon < 1 or values.ndim != 1:
        raise ValueError("observations must be a vector and horizon positive")
    valid = values[np.isfinite(values)]
    if not len(valid):
        return np.full(horizon, np.nan)
    return np.repeat(valid[-1], horizon)
