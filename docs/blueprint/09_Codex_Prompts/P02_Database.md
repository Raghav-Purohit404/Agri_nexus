# P02_Database

You are implementing one stage of the Farm Digital Twin. 
RULES (apply always):
1. Read code_skeleton/CONVENTIONS.md and the docstring of EVERY file listed below. The docstring is the specification: implement exactly it; keep the docstring at the top of the file.
2. Do not look for or copy third-party model source code. Implement from the specification. Use only the libraries named in pyproject.toml comments.
3. Where a spec says UNVERIFIED / literature / VERIFY, verify against the cited literature, record the check in docs/verification_log.md, and fix the spec constant if wrong.
4. Where a spec is ambiguous, do not guess silently: write the decision in docs/model_decisions.md and add a test.
5. Write the tests listed in each docstring first (TDD). Golden data is in code_skeleton/tests/golden/.
6. Pure functions for kernels, pydantic for I/O, type hints everywhere, no global state, rng passed explicitly.
7. Never fabricate parameters or data; use Quantified provenance; placeholders are flagged, never hidden.
8. Finish with: all tests green, mypy clean, a short CHANGELOG entry, and a list of any spec items you could not complete.

## Task
Implement db/schema.sql as Alembic migrations (PostGIS), repositories, append-only/audit triggers, views.

## Files to implement (read each docstring)
farm_twin/db/schema.sql, farm_twin/db/repositories.py

## Acceptance tests
testcontainers: idempotent re-import creates zero rows; observation.source cannot be MODEL_PREDICTED; audit_log rejects UPDATE/DELETE.

## Definition of done
Tests green, docstrings preserved, verification/decision logs updated, unfinished items listed.
