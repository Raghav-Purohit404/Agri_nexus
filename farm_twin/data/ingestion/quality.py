"""
FILE: farm_twin/data/ingestion/quality.py
PURPOSE: Data quality engine used by the Data Quality Agent AND by batch imports.

IMPLEMENT checks (each returns Issue(severity, code, variable, plot, message, suggested_action)):
  range_check (core.units.RANGES); unit_check; missing_check (required-variable matrix per model: e.g. AquaCrop-native needs sand/clay/OM or theta_wp/fc/sat/ksat per layer);
  duplicate_check (same key within tolerance); inconsistency_check:
      - physical: theta_fc <= theta_sat, theta_wp < theta_fc, Tmax >= Tmin, rain >= 0, Rs <= Ra (extra-terrestrial; 1.0 tolerance 5%), ea <= es
      - cross-variable: sand+silt+clay=100; ESP vs SAR (ESP ~ 100*(-0.0126+0.01475*SAR)/(1+(-0.0126+0.01475*SAR)) within +/- 5 points else warn)
  stale_check(rules per variable: weather forecast > 24 h; prices > 7 d; soil biology/OC > 3 y; satellite > 15 d)
  outlier_check on series: robust z (median/MAD) > 5 flagged, not removed;
  gap_report(series): list of gaps with lengths; gap_fill(series, method) ONLY for weather and ONLY short gaps (<= 3 d linear for temperature, 0 for rain unless another source covers it) producing ESTIMATED values with flag `gap_filled`.
  completeness_score(plot, model) in [0,1] per required-variable matrix -> drives Value-of-Information ranking (see voi/).
TESTS: each check has positive/negative fixtures; gap-fill never touches MEASURED rain.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable

from pydantic import BaseModel

from farm_twin.core.provenance import Quantified, ValueSource, estimated
from farm_twin.core.provenance import Uncertainty


class Issue(BaseModel):
    severity: str
    code: str
    variable: str | None = None
    plot: str | None = None
    message: str
    suggested_action: str | None = None


def range_check(variable: str, value: float, low: float, high: float) -> list[Issue]:
    return (
        []
        if low <= value <= high
        else [
            Issue(
                severity="ERROR",
                code="out_of_range",
                variable=variable,
                message=f"{value} is outside [{low},{high}]",
                suggested_action="verify source value and unit",
            )
        ]
    )


def missing_check(values: dict[str, Any], required: Iterable[str]) -> list[Issue]:
    return [
        Issue(
            severity="WARN",
            code="missing_required",
            variable=k,
            message="required variable is missing",
            suggested_action="supply evidence or use an explicit quantified estimate",
        )
        for k in required
        if values.get(k) is None
    ]


def duplicate_check(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[Issue]:
    seen = set()
    issues = []
    for row in rows:
        key = tuple(row.get(k) for k in key_fields)
        if key in seen:
            issues.append(Issue(severity="WARN", code="duplicate", message=f"duplicate key {key}"))
        seen.add(key)
    return issues


def inconsistency_check(row: dict[str, Any]) -> list[Issue]:
    checks = [
        ("theta_fc", "theta_sat", lambda a, b: a <= b, "field capacity must not exceed saturation"),
        ("theta_wp", "theta_fc", lambda a, b: a < b, "wilting point must be below field capacity"),
        ("tmin_c", "tmax_c", lambda a, b: a <= b, "minimum temperature exceeds maximum"),
        ("rain_mm", None, lambda a, b: a >= 0, "rainfall cannot be negative"),
    ]
    issues = []
    for a, b, predicate, message in checks:
        if row.get(a) is not None and (b is None or row.get(b) is not None) and not predicate(row[a], row.get(b)):
            issues.append(Issue(severity="ERROR", code="physical_inconsistency", variable=a, message=message))
    texture = [row.get(k) for k in ("sand_pct", "silt_pct", "clay_pct")]
    if all(v is not None for v in texture) and abs(sum(texture) - 100) > 2:
        issues.append(Issue(severity="ERROR", code="texture_sum", message="sand+silt+clay must sum to 100 +/- 2%"))
    return issues


def outlier_check(series: Iterable[float], variable: str, threshold: float = 5) -> list[Issue]:
    values = list(series)
    if len(values) < 3:
        return []
    med = median(values)
    mad = median([abs(v - med) for v in values])
    if mad == 0:
        return []
    return [
        Issue(
            severity="WARN",
            code="robust_outlier",
            variable=variable,
            message=f"value {v} has robust z-score > {threshold}",
        )
        for v in values
        if 0.6745 * abs(v - med) / mad > threshold
    ]


def gap_fill_weather(
    values: list[Quantified[float]], *, variable: str, max_gap_days: int = 3
) -> list[Quantified[float]]:
    if variable not in {"temperature", "tmax_c", "tmin_c", "rain_mm"}:
        raise ValueError("gap filling is allowed only for weather variables")
    out = list(values)
    if variable == "rain_mm":
        return out
    for i, q in enumerate(out):
        if q.prov.source != ValueSource.MISSING:
            continue
        left = next((j for j in range(i - 1, max(-1, i - max_gap_days - 1), -1) if out[j].value is not None), None)
        right = next((j for j in range(i + 1, min(len(out), i + max_gap_days + 2)) if out[j].value is not None), None)
        if left is not None and right is not None and right - left - 1 <= max_gap_days:
            value = out[left].value + (out[right].value - out[left].value) * (i - left) / (right - left)
            out[i] = estimated(
                value,
                q.unit,
                method="linear_weather_gap_fill",
                parent_ids=[],
                uncertainty=Uncertainty(kind="sd", sd=abs(out[right].value - out[left].value) / 2),
                model_version="quality-1",
            )
    return out


def completeness_score(values: dict[str, Any], required: Iterable[str]) -> float:
    fields = list(required)
    return sum(values.get(k) is not None for k in fields) / len(fields) if fields else 1.0
