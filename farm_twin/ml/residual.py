"""Physics-first LightGBM residual correction with temporal holdout and bounds.

The returned object is a calibration candidate. This module never promotes it;
deployment must use the independent calibration promotion gate. Conformal
intervals describe held-out residual coverage only and do not imply model
validity outside the calibration population.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import numpy as np

from farm_twin.ml.conformal import finite_sample_quantile


@dataclass
class ResidualModel:
    feature_min: np.ndarray
    feature_max: np.ndarray
    booster_text: str
    residual_quantile: float
    status: str
    reason: str | None = None
    training_data_hash: str | None = None
    n_train: int = 0
    n_calibration: int = 0

    def _booster(self):
        import lightgbm as lgb
        return lgb.Booster(model_str=self.booster_text)


def train_residual(
    features: np.ndarray, observed: np.ndarray, physical: np.ndarray, *,
    min_outcomes: int = 30, alpha: float = 0.1, calibration_fraction: float = 0.3,
    dates: np.ndarray | None = None, seed: int = 0,
) -> ResidualModel:
    x = np.asarray(features, float)
    y, base = np.asarray(observed, float).ravel(), np.asarray(physical, float).ravel()
    empty = ResidualModel(np.array([]), np.array([]), "", float("nan"), "DISABLED")
    if x.ndim != 2 or len(x) != len(y) or len(y) != len(base):
        raise ValueError("feature and target dimensions disagree")
    if len(y) < min_outcomes:
        empty.reason = f"requires >= {min_outcomes} independent outcomes; got {len(y)}"
        return empty
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(base).all():
        raise ValueError("training inputs must be finite")
    if not 0 < calibration_fraction < 0.5 or not 0 < alpha < 1:
        raise ValueError("invalid calibration_fraction or alpha")
    order = np.arange(len(y))
    if dates is not None:
        d = np.asarray(dates)
        if len(d) != len(y):
            raise ValueError("dates length differs from outcomes")
        order = np.argsort(d, kind="stable")
    else:
        # Preserve input order: callers must supply chronological rows.
        order = np.arange(len(y))
    n_cal = max(1, int(np.ceil(len(y) * calibration_fraction)))
    train_idx, cal_idx = order[:-n_cal], order[-n_cal:]
    if len(train_idx) < 20 or len(cal_idx) < 5:
        empty.reason = "blocked split requires >=20 fit and >=5 calibration outcomes"
        return empty
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise RuntimeError("Install the learning extra to train residual models") from exc
    target = y - base
    train = lgb.Dataset(x[train_idx], label=target[train_idx], free_raw_data=False)
    model = lgb.train(
        {"objective": "regression", "metric": "l2", "verbosity": -1, "seed": seed,
         "feature_fraction_seed": seed, "bagging_seed": seed, "num_leaves": 7,
         "max_depth": 4, "learning_rate": 0.03, "lambda_l1": 1.0,
         "lambda_l2": 5.0, "feature_fraction": 0.9, "bagging_fraction": 0.9,
         "bagging_freq": 1, "deterministic": True, "force_col_wise": True},
        train, num_boost_round=100
    )
    cal_residual = target[cal_idx] - model.predict(x[cal_idx], num_threads=1)
    q = finite_sample_quantile(np.abs(cal_residual), alpha)
    training_hash = hashlib.sha256(
        np.ascontiguousarray(np.column_stack((x[train_idx], y[train_idx], base[train_idx]))).tobytes()
    ).hexdigest()
    return ResidualModel(np.quantile(x[train_idx], 0.01, axis=0),
                         np.quantile(x[train_idx], 0.99, axis=0), model.model_to_string(), q,
                         "CANDIDATE", training_data_hash=training_hash,
                         n_train=len(train_idx), n_calibration=len(cal_idx))


def predict_residual(model: ResidualModel, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(features, float)
    if x.ndim != 2:
        raise ValueError("features must be a matrix")
    if model.status != "CANDIDATE":
        return np.full(len(x), np.nan), np.full(len(x), np.inf)
    if x.shape[1] != len(model.feature_min) or not np.isfinite(x).all():
        raise ValueError("feature dimensions disagree or values are non-finite")
    inside = np.all((x >= model.feature_min) & (x <= model.feature_max), axis=1)
    correction = model._booster().predict(x, num_threads=1)
    return np.where(inside, correction, np.nan), np.where(inside, model.residual_quantile, np.inf)


def save_residual(model: ResidualModel, directory: str | Path, model_id: str) -> Path:
    """Persist only LightGBM text and a JSON manifest; never unpickle artifacts."""
    if not model_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("model_id may contain only letters, digits, '-' and '_'")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / f"{model_id}.txt").resolve()
    if path.parent != root:
        raise ValueError("artifact path escaped its directory")
    path.write_text(model.booster_text, encoding="utf-8")
    manifest = {"model_id": model_id, "format": "lightgbm-text", "status": model.status,
                "feature_min": model.feature_min.tolist(), "feature_max": model.feature_max.tolist(),
                "residual_quantile": model.residual_quantile, "training_data_hash": model.training_data_hash,
                "n_train": model.n_train, "n_calibration": model.n_calibration,
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".json").write_text(json.dumps(manifest, sort_keys=True, allow_nan=False), encoding="utf-8")
    return path


def load_residual(path: str | Path) -> ResidualModel:
    model_path = Path(path).resolve()
    manifest = json.loads(model_path.with_suffix(".json").read_text(encoding="utf-8"))
    text = model_path.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest["artifact_sha256"]:
        raise ValueError("residual artifact hash mismatch")
    return ResidualModel(np.asarray(manifest["feature_min"], float), np.asarray(manifest["feature_max"], float),
                         text, float(manifest["residual_quantile"]), manifest["status"],
                         training_data_hash=manifest.get("training_data_hash"),
                         n_train=int(manifest.get("n_train", 0)), n_calibration=int(manifest.get("n_calibration", 0)))
