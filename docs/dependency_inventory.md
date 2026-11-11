# Dependency inventory

Versions are pinned in `pyproject.toml`. Licence identifiers below are the package metadata/SPDX identifiers to confirm against the exact distribution before release; this inventory does not replace a generated SBOM or legal review.

| Package | Version | Licence | Purpose | Status |
|---|---:|---|---|---|
| numpy | 2.2.6 | BSD-3-Clause | arrays/scientific computing | Mandatory |
| pandas | 2.2.3 | BSD-3-Clause | tabular/time series | Mandatory |
| scipy | 1.15.3 | BSD-3-Clause | scientific routines | Mandatory |
| pydantic | 2.13.5 | MIT | validation/contracts | Mandatory |
| pydantic-settings | 2.12.0 | MIT | configuration | Mandatory |
| Pint | 0.24.4 | BSD-3-Clause | units | Mandatory |
| SQLAlchemy | 2.0.44 | MIT | ORM | Mandatory |
| GeoAlchemy2 | 0.20.0 | MIT | PostGIS geometry | Mandatory |
| Alembic | 1.17.0 | MIT | migrations | Mandatory |
| psycopg[binary] | 3.2.10 | LGPL-3.0-only (binary extra dependencies vary) | PostgreSQL driver | Mandatory |
| Shapely | 2.1.2 | BSD-3-Clause | geometry | Mandatory |
| pyproj | 3.7.2 | MIT | projections | Mandatory |
| GeoPandas | 1.1.1 | BSD-3-Clause | vector geospatial data | Mandatory |
| Rasterio | 1.4.3 | BSD-3-Clause | raster IO | Mandatory |
| xarray | 2025.10.1 | Apache-2.0 | weather/raster arrays | Mandatory |
| httpx | 0.28.1 | BSD-3-Clause | provider HTTP | Mandatory |
| tenacity | 9.1.2 | Apache-2.0 | retry utilities | Mandatory |
| pdfplumber | 0.11.7 | MIT | PDF text/table foundations | Mandatory |
| pytesseract | 0.3.13 | Apache-2.0 | optional OCR binding | Mandatory in current manifest |
| Pillow | 11.3.0 | MIT-CMU | image handling | Mandatory in current manifest |
| pvlib | 0.13.1 | BSD-3-Clause | PV validation/optional integration | Optional (`validation`) |
| pytest | 8.4.2 | MIT | tests | Development |
| Hypothesis | 6.148.1 | MPL-2.0 | property tests | Development |
| testcontainers | 4.13.2 | Apache-2.0 | DB integration tests | Development |
| mypy | 1.18.2 | MIT | type checking | Development |
| Ruff | 0.14.3 | MIT | linting | Development |

No GPL-licensed source was vendored. Verify exact license metadata, transitive dependencies, and psycopg binary packaging before distribution.

| Package | Version | Licence | Purpose | Status |
|---|---:|---|---|---|
| FastAPI | 0.162.2 | MIT | Python API | Optional (`app`); installed in `.venv311`; import succeeded in smoke check |
| python-multipart | 0.0.33 | Apache-2.0 | multipart upload parsing | Optional (`app`); installed in `.venv311` |
| Streamlit | 1.67.0 | Apache-2.0 | initial Python UI | Optional (`app`); installed in `.venv311`; not launched |
| LangGraph | 1.2.20 | MIT | agent workflow graph | Optional (`agents`); installed in `.venv311`; checkpoint and worker integrations incomplete |
| Pyomo | 6.10.1 | BSD-3-Clause | MILP model layer | Optional (`planning`); installed in `.venv311`; solver formulation not accepted |
| highspy | 1.15.1 | MIT | HiGHS solver interface | Optional (`planning`); installed in `.venv311`, but native module import blocked by Windows Application Control |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI runtime for FastAPI | Optional (`app`) |
| langgraph-checkpoint-postgres | 3.2.0 | MIT | PostgreSQL-backed LangGraph checkpoints | Optional (`agents`); factory integration required |
| emcee | 3.1.6 | MIT | Affine-invariant ensemble MCMC calibration | Optional (`learning`) |
| scikit-learn | 1.9.1 | BSD-3-Clause | Selected calibration diagnostics and future baseline models | Optional (`learning`) |
| LightGBM | 4.7.0 | MIT | Shallow tree residual corrector | Optional (`learning`); residual model is a candidate only |

## Plot planner frontend

The inventory below covers direct frontend dependencies. Transitive packages are locked in `frontend/pnpm-lock.yaml`; run `pnpm licenses list` in `frontend/` to inspect the complete installed tree.

| Package | Version | Licence | Purpose | Status |
|---|---:|---|---|---|
| React | 19.2.0 | MIT | Interactive UI rendering | Mandatory |
| React DOM | 19.2.0 | MIT | Browser rendering | Mandatory |
| Zustand | 5.0.8 | MIT | UI state and undo/redo history | Mandatory |
| polygon-clipping | 0.15.7 | MIT | Frontend plot-shape boolean operations | Mandatory |
| Vite | 7.1.12 | MIT | Frontend dev server and production bundling | Development |
| TypeScript | 5.9.3 | Apache-2.0 | Strict type checking | Development |
| Vitest | 5.1.0 | MIT | Unit tests | Development |
| Playwright | 1.65.0 | Apache-2.0 | Browser automation | Development |
| @axe-core/playwright | 4.10.2 | MPL-2.0 | Accessibility checks | Development |
| @testing-library/react | 16.3.0 | MIT | UI component tests | Development |
| @testing-library/user-event | 14.6.1 | MIT | UI event simulation | Development |
| @testing-library/jest-dom | 6.9.1 | MIT | DOM assertions | Development |
| jsdom | 27.0.1 | MIT | DOM test environment | Development |
| tsx | 4.20.6 | MIT | Run the TypeScript demo API fixture | Development |
| @types/geojson | 7946.0.16 | MIT | GeoJSON type definitions | Development |
| @types/node | 24.7.2 | MIT | Node API type definitions | Development |
| @types/react | 19.2.2 | MIT | React type definitions | Development |
| @types/react-dom | 19.2.2 | MIT | React DOM type definitions | Development |
| @vitejs/plugin-react | 5.0.4 | MIT | React transform for Vite | Development |
