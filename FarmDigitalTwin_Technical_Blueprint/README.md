# Farm Digital Twin - Technical Blueprint for Codex

A complete build specification for a probabilistic, agent-assisted digital twin of small (55-120 m2 pilot plots, any size) farm properties:
soil, water, crop, solar, agrivoltaic, finance, optimisation, calibration, and a governed multi-agent layer.

## Master PDF
`FarmDigitalTwin_Master_Technical_Reference.pdf` (37 pages) explains the architecture and states every formula in typeset form with worked numbers and evidence status. Read it first; the skeleton docstrings are the build specs.

## How to use this ZIP with Codex
1. Read `08_Implementation/00_BUILD_ORDER.md` and `code_skeleton/CONVENTIONS.md`.
2. Run the prompts in `09_Codex_Prompts/` IN ORDER (P00 ... P16). Each prompt names the skeleton files it must implement.
3. Every file in `code_skeleton/farm_twin/` is a SPECIFICATION: a module docstring with the exact equations, algorithms, signatures, units, edge cases and tests. Implement the code under that docstring and keep the docstring.
4. Golden regression data is in `code_skeleton/tests/golden/` (extracted by actually running reference software while writing this blueprint).

## What is verified vs. not (read `03_Open_Source_Research/Source_Code_Inspection/inspection_log.md`)
Specs tagged [VERIFIED] were read from real source code. Specs tagged UNVERIFIED / literature / VERIFY were written from domain knowledge and MUST be checked by Codex against the cited literature before use. Provider endpoints were not verifiable from the authoring sandbox.

## Folder map
- 01_Project_Definition - goals, requirements, scope
- 02_Architecture - system design, data flow, diagrams (Mermaid)
- 03_Open_Source_Research - what was inspected, licences, what each model contributes and where it is weak
- 04_Scientific_Models - MODEL_FIDELITY_MATRIX and model notes
- 05_Data_Infrastructure - data sources, quality, ingestion
- 06_Agentic_AI - agent design, tools, governance
- 07_Optimization_And_Finance - decision layer
- 08_Implementation - build order, testing, validation, acceptance
- 09_Codex_Prompts - ready-to-run prompts
- code_skeleton - the Python package specification + golden fixtures
