# P04_ET0_Soil_Water

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
Implement FAO-56 ET0, pedotransfer, and the layered water balance with exact process order and mass-balance assertion.

## Files to implement (read each docstring)
farm_twin/models/et/reference_et.py, farm_twin/models/soil/pedotransfer.py, farm_twin/models/soil/water_balance.py

## Acceptance tests
Uccle FAO-56 example to 0.05 mm/d; CN example Q=16.1 mm; 10-yr mass balance closes within 0.5 mm/season.

## Definition of done
Tests green, docstrings preserved, verification/decision logs updated, unfinished items listed.
