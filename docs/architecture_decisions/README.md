# Architecture decisions

## ADR 0001 — Python-only application foundation

**Decision:** Keep domain logic, scientific models, APIs, persistence orchestration, and initial UI in Python. Use the Python 3.11 stack declared in `pyproject.toml`.

**Reason:** The project directive requires Python-only implementation and common typed contracts across the scientific modules.

**Consequences:** This repository contains no JavaScript application. FastAPI/Streamlit integration belongs to later P15; do not mark it implemented in P01–P08.

## ADR 0002 — Provenance and immutable observations

**Decision:** Represent provenance as a first-class contract and separate observations, estimates, and predictions in persistence.

**Reason:** Calibration and closed-loop learning must not overwrite measured data or promote unvalidated candidates.

**Consequences:** Database triggers and migration behavior must be checked against a live PostgreSQL/PostGIS instance before claiming persistence acceptance.
