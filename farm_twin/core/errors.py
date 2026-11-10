"""
FILE: farm_twin/core/errors.py
PURPOSE: Single exception hierarchy used by every layer.

IMPLEMENT:
    class FarmTwinError(Exception): base; carries `.code: str` and `.context: dict` (JSON-serialisable).
    class UnitError(FarmTwinError)             wrong/unknown unit, unit mismatch in an operation.
    class RangeError(FarmTwinError)            value outside physically valid range (RANGES table in core/units.py).
    class MissingDataError(FarmTwinError)      required input is MISSING and no ESTIMATED fallback is permitted.
    class MassBalanceError(FarmTwinError)      |inputs - outputs - dStorage| > tolerance (0.5 mm water; 1e-6 relative for carbon).
    class InfeasibleError(FarmTwinError)       optimisation model infeasible (carry a conflict hint if the solver gives one).
    class ApprovalRequiredError(FarmTwinError) an agent attempted a gated action without a valid human approval token.
    class ProvenanceViolation(FarmTwinError)   attempt to overwrite MEASURED data with non-measured, or upgrade provenance.
    class ModelNotValidatedError(FarmTwinError) attempt to use/promote a parameter set that failed the promotion gate.
RULES: every exception serialises via `.to_dict()` -> {"code","message","context"}; the dict is returned verbatim
       inside tool-call results so agents can reason about failures.
TESTS: tests/test_core.py::test_error_serialisation
"""

from __future__ import annotations

from typing import Any


class FarmTwinError(Exception):
    """Base error with a stable machine-readable code and JSON context."""

    code = "farm_twin_error"

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "context": self.context}


class UnitError(FarmTwinError):
    code = "unit_error"


class RangeError(FarmTwinError):
    code = "range_error"


class MissingDataError(FarmTwinError):
    code = "missing_data"


class MassBalanceError(FarmTwinError):
    code = "mass_balance_error"


class InfeasibleError(FarmTwinError):
    code = "infeasible"


class ApprovalRequiredError(FarmTwinError):
    code = "approval_required"


class ProvenanceViolation(FarmTwinError):
    code = "provenance_violation"


class ModelNotValidatedError(FarmTwinError):
    code = "model_not_validated"
