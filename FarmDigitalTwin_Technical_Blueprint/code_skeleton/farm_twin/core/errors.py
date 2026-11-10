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
