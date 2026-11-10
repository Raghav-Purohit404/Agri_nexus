"""
FILE: farm_twin/core/provenance.py
PURPOSE: Make the measured / imported / estimated / predicted / missing distinction impossible to ignore.

IMPLEMENT:
    class ValueSource(str, Enum): MEASURED, IMPORTED, ESTIMATED, MODEL_PREDICTED, MISSING

    class Uncertainty(BaseModel):
        kind: Literal["sd","interval","ensemble","none"]
        sd: float | None; lo: float | None; hi: float | None; level: float | None   # level e.g. 0.9
        samples: list[float] | None    # small ensembles only (<=200); large ensembles are stored as arrays on disk

    class Provenance(BaseModel):
        source: ValueSource
        method: str | None             # "lab:ICP-OES", "pedotransfer:saxton_rawls_2006", "model:aquacrop_native@1.0.0"
        dataset_id: str | None         # FK to dataset registry or uploaded file id
        observed_at: datetime | None
        retrieved_at: datetime | None
        uncertainty: Uncertainty | None
        parent_ids: list[str] = []     # provenance DAG: which inputs produced an ESTIMATED / PREDICTED value
        model_version: str | None
        parameter_set_id: str | None
        quality_flags: list[str] = []  # "stale","gap_filled","out_of_range_clipped","unit_converted"

    class Quantified(BaseModel, Generic[T]):
        value: T | None                # None if and only if source == MISSING
        unit: str                      # canonical unit string, validated against core.units
        prov: Provenance

    FUNCTIONS:
        measured(value, unit, *, method, dataset_id, observed_at, uncertainty=None) -> Quantified
        estimated(value, unit, *, method, parent_ids, uncertainty) -> Quantified     # uncertainty REQUIRED
        predicted(value, unit, *, model_version, parameter_set_id, parent_ids, uncertainty) -> Quantified
        missing(unit, reason) -> Quantified
        require_measured(q) -> value        # raises MissingDataError unless source in {MEASURED, IMPORTED}
        merge_prefer_measured(a, b)         # newest MEASURED wins; ESTIMATED never beats MEASURED
        assert_no_provenance_upgrade(old, new)   # raises ProvenanceViolation

    DB MAPPING: table `observation` holds only MEASURED/IMPORTED; `estimate` holds ESTIMATED; `prediction` holds
    MODEL_PREDICTED. They are physically separate tables on purpose (see db/schema.sql).
TESTS: tests/test_core.py::test_cannot_upgrade_estimated_to_measured, ::test_missing_has_no_value,
       ::test_estimated_requires_uncertainty
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from farm_twin.core.errors import MissingDataError, ProvenanceViolation

T = TypeVar("T")


class ValueSource(str, Enum):
    MEASURED = "MEASURED"
    IMPORTED = "IMPORTED"
    ESTIMATED = "ESTIMATED"
    MODEL_PREDICTED = "MODEL_PREDICTED"
    MISSING = "MISSING"


class Uncertainty(BaseModel):
    kind: Literal["sd", "interval", "ensemble", "none"]
    sd: float | None = None
    lo: float | None = None
    hi: float | None = None
    level: float | None = None
    samples: list[float] | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> "Uncertainty":
        if self.kind == "sd" and (self.sd is None or self.sd < 0):
            raise ValueError("sd uncertainty requires sd >= 0")
        if self.kind == "interval" and (self.lo is None or self.hi is None or self.lo > self.hi):
            raise ValueError("interval uncertainty requires lo <= hi")
        if self.kind == "ensemble" and (self.samples is None or len(self.samples) > 200):
            raise ValueError("ensemble uncertainty requires at most 200 samples")
        return self


class Provenance(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    source: ValueSource
    method: str | None = None
    dataset_id: str | None = None
    observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    uncertainty: Uncertainty | None = None
    parent_ids: list[str] = Field(default_factory=list)
    model_version: str | None = None
    parameter_set_id: str | None = None
    quality_flags: list[str] = Field(default_factory=list)


class Quantified(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    value: T | None
    unit: str
    prov: Provenance

    @model_validator(mode="after")
    def missing_has_no_value(self) -> "Quantified[T]":
        if (self.prov.source == ValueSource.MISSING) != (self.value is None):
            raise ValueError("value is None if and only if source is MISSING")
        if self.prov.source == ValueSource.ESTIMATED and self.prov.uncertainty is None:
            raise ValueError("ESTIMATED values require quantified uncertainty")
        return self


def _q(value: T | None, unit: str, source: ValueSource, **kwargs: object) -> Quantified[T]:
    return Quantified(value=value, unit=unit, prov=Provenance(source=source, **kwargs))


def measured(
    value: T,
    unit: str,
    *,
    method: str,
    dataset_id: str | None = None,
    observed_at: datetime | None = None,
    uncertainty: Uncertainty | None = None,
) -> Quantified[T]:
    return _q(
        value,
        unit,
        ValueSource.MEASURED,
        method=method,
        dataset_id=dataset_id,
        observed_at=observed_at,
        uncertainty=uncertainty,
    )


def imported(
    value: T,
    unit: str,
    *,
    method: str,
    dataset_id: str | None = None,
    retrieved_at: datetime | None = None,
    uncertainty: Uncertainty | None = None,
    quality_flags: list[str] | None = None,
) -> Quantified[T]:
    return _q(
        value,
        unit,
        ValueSource.IMPORTED,
        method=method,
        dataset_id=dataset_id,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        uncertainty=uncertainty,
        quality_flags=quality_flags or [],
    )


def estimated(
    value: T,
    unit: str,
    *,
    method: str,
    parent_ids: list[str] | None,
    uncertainty: Uncertainty,
    model_version: str | None = None,
) -> Quantified[T]:
    return _q(
        value,
        unit,
        ValueSource.ESTIMATED,
        method=method,
        parent_ids=parent_ids or [],
        uncertainty=uncertainty,
        model_version=model_version,
    )


def predicted(
    value: T,
    unit: str,
    *,
    model_version: str,
    parameter_set_id: str,
    parent_ids: list[str] | None,
    uncertainty: Uncertainty | None = None,
) -> Quantified[T]:
    return _q(
        value,
        unit,
        ValueSource.MODEL_PREDICTED,
        model_version=model_version,
        parameter_set_id=parameter_set_id,
        parent_ids=parent_ids or [],
        uncertainty=uncertainty,
    )


def missing(unit: str, reason: str) -> Quantified[None]:
    return _q(None, unit, ValueSource.MISSING, method=reason)


def require_measured(q: Quantified[T]) -> T:
    if q.value is None or q.prov.source not in {ValueSource.MEASURED, ValueSource.IMPORTED}:
        raise MissingDataError("A measured or imported value is required", context={"source": q.prov.source.value})
    return q.value


def merge_prefer_measured(a: Quantified[T], b: Quantified[T]) -> Quantified[T]:
    if a.prov.source == ValueSource.MEASURED and b.prov.source != ValueSource.MEASURED:
        return a
    if b.prov.source == ValueSource.MEASURED and a.prov.source != ValueSource.MEASURED:
        return b
    if a.prov.source == ValueSource.IMPORTED and b.prov.source == ValueSource.ESTIMATED:
        return a
    if b.prov.source == ValueSource.IMPORTED and a.prov.source == ValueSource.ESTIMATED:
        return b
    return max(
        (a, b),
        key=lambda item: item.prov.observed_at or item.prov.retrieved_at or datetime.min.replace(tzinfo=timezone.utc),
    )


def assert_no_provenance_upgrade(old: Quantified[object], new: Quantified[object]) -> None:
    if (old.prov.source == ValueSource.MEASURED and new.prov.source != ValueSource.MEASURED) or (
        new.prov.source == ValueSource.MEASURED and old.prov.source != ValueSource.MEASURED
    ):
        raise ProvenanceViolation("Measured observations cannot be overwritten or assigned to derived values")
