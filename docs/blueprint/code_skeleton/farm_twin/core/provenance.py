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
