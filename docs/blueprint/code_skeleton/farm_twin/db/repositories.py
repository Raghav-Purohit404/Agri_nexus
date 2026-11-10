"""
FILE: farm_twin/db/repositories.py
PURPOSE: Repository layer (SQLAlchemy 2.x + GeoAlchemy2). No SQL outside this package.

IMPLEMENT: PropertyRepo, PlotRepo (create/update with area recomputed in local CRS; spatial queries: plots_within(bbox), neighbours(plot)),
    ObservationRepo (insert_many idempotent via the UNIQUE key; latest(plot, variable, depth), series(plot, variable, t0, t1); supersede() instead of UPDATE/DELETE),
    EstimateRepo, PredictionRepo (bulk COPY insert for ensembles), ParameterSetRepo (resolve_effective(model, plot_id) walks PLOT->FARM->REGIONAL->GENERIC
    returning merged params + a provenance chain), SimRunRepo, InterventionRepo, RecommendationRepo, CalibrationRepo, AuditRepo (append-only).
RULES: observations are append-only (corrections create a new row and set superseded_by); every write passes through core.provenance validation;
       repositories return pydantic domain objects, never ORM rows.
TESTS: use testcontainers-postgis; idempotent re-import of the same soil report creates zero new rows; resolve_effective merges levels correctly.
"""
