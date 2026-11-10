"""Finite-sample split conformal intervals for blocked residual calibration.

The calibration rows must be held out from fitting and should be temporally
blocked when observations are serially dependent. Coverage is marginal, not
conditional; it does not establish scientific validity of the underlying model.
"""

from __future__ import annotations

import math
import numpy as np


def finite_sample_quantile(scores: np.ndarray, alpha: float = 0.1) -> float:
    """Return the conformal order statistic at ceil((n+1)(1-alpha))."""
    values = np.asarray(scores, dtype=float).ravel()
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not len(values) or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("scores must be a non-empty finite non-negative vector")
    rank = math.ceil((len(values) + 1) * (1 - alpha))
    if rank > len(values):
        return float("inf")
    return float(np.partition(values, rank - 1)[rank - 1])


def split_conformal_interval(
    predictions: np.ndarray, observed: np.ndarray, calibration_predictions: np.ndarray,
    calibration_observed: np.ndarray, *, alpha: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Calibrate symmetric absolute-residual intervals on a separate block."""
    pred, truth = np.asarray(predictions, float).ravel(), np.asarray(observed, float).ravel()
    cal_pred, cal_truth = np.asarray(calibration_predictions, float).ravel(), np.asarray(calibration_observed, float).ravel()
    if len(pred) != len(truth) or len(cal_pred) != len(cal_truth):
        raise ValueError("prediction and observation lengths differ")
    if not np.isfinite(pred).all() or not np.isfinite(truth).all() or not np.isfinite(cal_pred).all() or not np.isfinite(cal_truth).all():
        raise ValueError("conformal inputs must be finite")
    q = finite_sample_quantile(np.abs(cal_truth - cal_pred), alpha)
    return pred - q, pred + q, q
