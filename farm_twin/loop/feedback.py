"""
FILE: farm_twin/loop/feedback.py
PURPOSE: Close the loop: recommendation -> approval -> execution -> outcome -> error analysis -> calibration -> better recommendation.
IMPLEMENT:
  record_recommendation(scenario_result, chosen_plan) writes recommendation with EXPECTED KPI distributions and assumptions (immutable).
  record_approval(...) (human decision) ; record_execution(intervention actual_payload) ; record_outcome(plot, variable, observed value/time) auto-links to the prediction made for that (plot, variable, date, run) and computes error, standardised error z = (obs - mean)/sd, PIT value, and whether obs fell in the 90 % interval.
  error_analysis(): attribute error by driver: re-run the SAME plan with ACTUAL weather & ACTUAL interventions (hindcast) -> splits total error into (i) weather realisation, (ii) management deviation, (iii) residual model/parameter error. Only (iii) feeds calibration.
  triggers: after each harvest or batch of >= N outcomes -> schedule calibration_run; after each calibration decision -> report to user in plain language ('model changed because ...' or 'model unchanged because it did not beat the current version').
  learning ledger: monotone log of model version changes and their measured effects on out-of-sample error; rendered in the UI as 'Is the twin getting better?'
TESTS: error attribution on synthetic case where only weather differs -> residual error ~0; PIT uniform for a calibrated synthetic model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4
import math


@dataclass(frozen=True)
class RecommendationRecord:
    id: str
    plan: Mapping[str, Any]
    expected: Mapping[str, Any]
    assumptions: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class OutcomeRecord:
    id: str
    recommendation_id: str
    plot_id: str
    variable: str
    observed: float
    observed_at: datetime
    predicted_mean: float
    predicted_sd: float
    error: float
    z: float


class LearningLedger:
    """Append-only in-memory contract; persistence belongs to the database adapter."""

    def __init__(self) -> None:
        self.recommendations: list[RecommendationRecord] = []
        self.approvals = []
        self.executions = []
        self.outcomes = []
        self.calibration_events = []

    def record_recommendation(self, result: Mapping[str, Any], plan: Mapping[str, Any]) -> RecommendationRecord:
        row = RecommendationRecord(
            str(uuid4()),
            dict(plan),
            dict(result.get("expected", {})),
            tuple(result.get("assumptions", ())),
            datetime.now(timezone.utc),
        )
        self.recommendations.append(row)
        return row

    def record_approval(self, recommendation_id: str, decision: str, actor_id: str, note: str = "") -> dict[str, str]:
        if decision not in {"APPROVED", "REJECTED", "MODIFIED"}:
            raise ValueError("invalid approval decision")
        row = {"recommendation_id": recommendation_id, "decision": decision, "actor_id": actor_id, "note": note}
        self.approvals.append(row)
        return row

    def record_execution(self, recommendation_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        row = {
            "recommendation_id": recommendation_id,
            "payload": dict(payload),
            "recorded_at": datetime.now(timezone.utc),
        }
        self.executions.append(row)
        return row

    def record_outcome(
        self,
        recommendation_id: str,
        plot_id: str,
        variable: str,
        observed: float,
        predicted: Mapping[str, float],
        observed_at: datetime,
    ) -> OutcomeRecord:
        mean = float(predicted["mean"])
        sd = float(predicted.get("sd", 0))
        error = float(observed - mean)
        row = OutcomeRecord(
            str(uuid4()),
            recommendation_id,
            plot_id,
            variable,
            float(observed),
            observed_at,
            mean,
            sd,
            error,
            error / sd if sd > 0 else math.nan,
        )
        self.outcomes.append(row)
        return row

    @staticmethod
    def attribute_error(
        observed: float,
        forecast_prediction: float,
        actual_weather_prediction: float,
        actual_management_prediction: float,
    ) -> dict[str, float]:
        return {
            "weather": float(forecast_prediction - actual_weather_prediction),
            "management": float(actual_weather_prediction - actual_management_prediction),
            "residual": float(observed - actual_management_prediction),
        }
