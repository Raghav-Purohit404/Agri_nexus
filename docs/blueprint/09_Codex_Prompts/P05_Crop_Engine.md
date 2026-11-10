# P05_Crop_Engine

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
FIRST: in a throwaway virtualenv, extract golden fixtures: dump wheat params AND derived values (CC0, CGC, CDC, stage dates, HIGC, tLinSwitch, dHILinear) and daily CC/Ks/biomass/yield for the Tunis wheat run (rainfed and SMT70). THEN implement phenology/roots, canopy, stress, transpiration/biomass/HI, orchestrator, crop library (-9 sentinels as None), DSSAT adapter skeleton (skipped if exe missing).

## Files to implement (read each docstring)
farm_twin/models/crop/*.py, farm_twin/models/base.py

## Acceptance tests
golden yields +/-3%, irrigation +/-5 mm, daily CC +/-0.01; HIGC search; Zr monotone; 100 scenarios x 1 season < 1 s.

## Definition of done
Tests green, docstrings preserved, verification/decision logs updated, unfinished items listed.
