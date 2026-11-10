"""
FILE: farm_twin/calibration/promotion_gate.py
PURPOSE: No calibrated parameter set is used in production unless it PROVES it predicts held-out data better than the parent set. This is the safety mechanism behind 'the model learns without degrading'.

PROCEDURE promote(candidate_set):
   1. Temporal blocked cross-validation (leave-one-season-out, never random splits - weather autocorrelation) producing out-of-sample predictions for candidate and for the current ACTIVE parent.
   2. Metrics per variable: RMSE, MAE, bias, NSE, KGE, and PROBABILISTIC: CRPS and 90 % interval coverage (should be 0.85-0.95) and PIT histogram check.
   3. Criteria (all must hold): CRPS(candidate) <= 0.95*CRPS(parent) on pooled held-out data; no variable's RMSE worsens by > 10 %; coverage within 0.80-0.97; physical-sanity checks pass (parameters in valid ranges; simulated mass balances unchanged); minimum evidence: >= 2 independent seasons or >= 8 independent observation points at that level; stability: parameters change < 3 posterior SD vs the previous promoted set unless justified.
   4. Decision logged in calibration_run(decision, reason, metrics_before/after). PROMOTE -> status VALIDATED then ACTIVE (previous ACTIVE -> RETIRED, kept for rollback). REJECT -> status REJECTED with reasons.
   5. DRIFT MONITOR (post-promotion): rolling prediction-error z-scores; if |mean z| > 2 for 3 consecutive outcomes or coverage collapses -> auto-ROLLBACK to previous ACTIVE and raise AnomalyDetected.
   6. Human override: agent cannot promote; only the gate (or a human with ApprovalToken for model changes).
TESTS: candidate trained on noise fails; genuinely better synthetic candidate passes; rollback triggers on injected bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import numpy as np


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reasons: tuple[str, ...]


def evaluate_candidate(
    parent_crps: Mapping[str, float],
    candidate_crps: Mapping[str, float],
    parent_rmse: Mapping[str, float],
    candidate_rmse: Mapping[str, float],
    coverage90: float,
    n_seasons: int,
    n_points: int,
    physical_sanity: bool,
    parameter_sd_change: float,
) -> PromotionDecision:
    reasons = []
    keys = set(parent_crps) & set(candidate_crps)
    if not keys:
        reasons.append("no comparable held-out CRPS")
    elif sum(candidate_crps[k] for k in keys) > 0.95 * sum(parent_crps[k] for k in keys):
        reasons.append("pooled CRPS improvement below required 5 percent")
    for key in set(parent_rmse) & set(candidate_rmse):
        if candidate_rmse[key] > 1.10 * parent_rmse[key]:
            reasons.append(f"RMSE worsened >10% for {key}")
    if not 0.80 <= coverage90 <= 0.97:
        reasons.append("90% interval coverage outside 0.80-0.97")
    if n_seasons < 2 and n_points < 8:
        reasons.append("insufficient independent evidence")
    if not physical_sanity:
        reasons.append("physical sanity check failed")
    if parameter_sd_change >= 3:
        reasons.append("parameter change exceeds stability threshold")
    return PromotionDecision(not reasons, tuple(reasons))


class DriftMonitor:
    def __init__(self, threshold: float = 2.0, consecutive: int = 3):
        self.threshold = threshold
        self.consecutive = consecutive
        self._z = []

    def add(self, z: float, coverage: float | None = None) -> bool:
        self._z.append(float(z))
        self._z = self._z[-self.consecutive :]
        return (len(self._z) == self.consecutive and abs(float(np.mean(self._z))) > self.threshold) or (
            coverage is not None and coverage < 0.8
        )


class ParameterSetLifecycle:
    """Explicit in-memory promotion/rollback state machine; persistence must use CalibrationRepo."""

    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.active_by_scope: dict[str, str] = {}
        self.previous_by_scope: dict[str, str] = {}
        self.history: list[dict[str, str]] = []

    def register_candidate(self, candidate_id: str) -> None:
        if candidate_id in self.status:
            raise ValueError("parameter set id already registered")
        self.status[candidate_id] = "CANDIDATE"

    def apply_gate(self, scope: str, candidate_id: str, decision: PromotionDecision) -> str:
        if self.status.get(candidate_id) != "CANDIDATE":
            raise ValueError("only a registered candidate can be evaluated")
        if not decision.promote:
            self.status[candidate_id] = "REJECTED"
            self.history.append({"scope": scope, "candidate": candidate_id, "decision": "REJECTED"})
            return "REJECTED"
        previous = self.active_by_scope.get(scope)
        if previous:
            self.status[previous] = "RETIRED"
            self.previous_by_scope[scope] = previous
        self.status[candidate_id] = "ACTIVE"
        self.active_by_scope[scope] = candidate_id
        self.history.append({"scope": scope, "candidate": candidate_id, "decision": "PROMOTED"})
        return "PROMOTED"

    def rollback(self, scope: str, reason: str) -> str:
        active = self.active_by_scope.get(scope)
        previous = self.previous_by_scope.get(scope)
        if active is None or previous is None:
            raise ValueError("no previous active parameter set available for rollback")
        self.status[active] = "ROLLED_BACK"
        self.status[previous] = "ACTIVE"
        self.active_by_scope[scope] = previous
        self.history.append({"scope": scope, "candidate": active, "decision": "ROLLBACK", "reason": reason})
        return previous
