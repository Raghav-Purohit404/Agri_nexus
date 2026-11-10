"""
FILE: farm_twin/api/routers.py
PURPOSE: FastAPI service exposing the core to the UI and agents. Versioned under /api/v1; OpenAPI auto-generated; pydantic models from domain; auth via OIDC/JWT (RBAC from agents/governance).
ROUTES (all return provenance-bearing models):
  /properties, /properties/{id}/plots (CRUD; geometry GeoJSON in/out), /plots/{id}/state?date= (FarmState view), /plots/{id}/observations (POST idempotent, GET series),
  /uploads/soil-report (multipart -> ingestion pipeline -> IngestionResult needing confirmation), /uploads/{id}/confirm,
  /data/weather?lon&lat&start&end, /data/forecast, /quality/{plot_id} (issues + completeness),
  /simulate/season (POST: plot, crop, plan, n_weather) -> sim_run id (async job; GET /jobs/{id}), /scenarios (CRUD), /scenarios/{id}/run, /scenarios/compare,
  /optimize (POST) -> job -> Pareto frontier ; /voi/rank ; /recommendations/{id} ; /recommendations/{id}/approve|reject|modify (human only),
  /outcomes (POST) ; /calibration/status|history ; /models (registry, versions, validation status) ; /agent/chat (SSE stream of agent events + approval interrupts) ; /agent/threads/{id}/resume.
  Long jobs run in a worker queue (Celery/RQ or arq) with progress events; results stored in DB; idempotency keys on POST.
  Rate limits, request size limits (uploads 25 MB), content-type sniffing, virus scan hook for uploads, CORS allowlist, structured logging with request ids.
TESTS: contract tests from OpenAPI; auth/RBAC; idempotency; upload size limit.
"""
