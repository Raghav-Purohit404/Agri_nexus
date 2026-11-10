# Farm Digital Twin

A Python-only scientific foundation for a hierarchical, region-independent farm digital twin. Source foundations span P01–P16; implementation, testing, integration, and scientific acceptance statuses are tracked separately and remain incomplete in several areas.

## Runtime

Use CPython 3.11; see [implementation status](docs/implementation_status.md) for setup and environment notes.

Launch the interactive, local demo with `python -m streamlit run farm_twin/ui/demo_app.py` after installing the pinned app dependencies. It computes a one-day ET₀ and layered soil-water transition, with optional clear-sky PV and user-input-only finance panels. All demo inputs are explicitly ESTIMATED/user-supplied assumptions; it produces no crop-yield recommendation and is not field validated. The demo does not require PostgreSQL, Docker, authentication, or provider credentials.

## Scientific scope

Domain values preserve provenance. The current science modules include ET0, soil water and pedotransfer foundations, crop-model kernels, RothC-style carbon, nutrient and salinity kernels, solar/PV calculations, agrivoltaic radiation/coupling foundations, and deterministic finance functions. Their implementation, test, integration, and scientific-validation statuses differ; see [model decisions](docs/model_decisions.md) and [verification log](docs/verification_log.md).

## Database

PostgreSQL 16 with PostGIS is configured in Docker Compose; migrations use Alembic. Apply the initial migration only after configuring a local database. This session could not launch Docker or validate the migration against a running database.

## Dependencies and license notes

Exact direct dependency pins are in `pyproject.toml`; a purpose and license inventory is in [dependency inventory](docs/dependency_inventory.md). No third-party repository source was copied into this project.

## Tests

Run `python -m pytest` from the project root after installing the `dev` extra. Previously recorded results predate this coding pass; no checks were run on the latest changes. Golden fixtures are retained unchanged; see the verification log for known unresolved reference mismatches.
# Runtime entry points

The project is Python-only. Install the complete pinned Edition 1 environment
with `python -m pip install -r requirements.txt` in CPython 3.11. The editable
project metadata and optional extras are the source of truth for dependency
versions; `docs/dependency_inventory.md` records purpose and licence.

The API entry point is `farm_twin.api.runtime:app` (FastAPI/Uvicorn), and the
initial UI is `farm_twin/ui/app_spec.py` (Streamlit). The API intentionally
requires `FARM_TWIN_SERVICE_FACTORY=your_package:factory` to return a configured
`SQLApplicationService`; the factory must provide a PostgreSQL session factory,
a verified OIDC token verifier, and any enabled scientific/data adapters. The
separate worker entry point `python -m farm_twin.api.worker` requires
`FARM_TWIN_WORKER_FACTORY=your_package:factory` returning a session factory
and idempotent handlers. These contracts avoid insecure default identity and
mock simulation output. Without them, only API health/OpenAPI are available and
protected operations return an explicit unavailable response.

Docker Compose defines PostGIS, API, worker, and Streamlit containers. Apply
the Python Alembic migration explicitly after PostGIS is ready; the API does
not mutate the database schema at startup. A deployment must configure the
service factories, OIDC trust, secrets, allowed CORS origins, upload scanner,
and model/provider adapters before exposing it to users. The implementation
status and verification log distinguish code from tested, integrated, and
scientifically validated functionality.
