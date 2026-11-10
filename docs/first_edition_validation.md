# First-edition validation report

Date: 2026-11-10

## Result

**NOT ACCEPTED as a validated first edition.** The source tree compiles syntactically with CPython 3.13.17, and 70 original skeleton module docstrings remain intact. This does not establish correct imports, Python 3.11 compatibility, runtime behavior, or scientific validity.

## Checks performed

- CPython 3.13 `compileall` over `farm_twin/`, `migrations/`, and `tests/`: passed (syntax only).
- AST comparison of module docstrings against the preserved code skeleton: 70 checked, no differences.
- `pyproject.toml` parsed with `tomllib`; optional dependency groups are syntactically valid.
- `python -m pytest -q`: could not run because pytest is not installed (`No module named pytest`).
- Ruff and mypy: unavailable.
- Docker/PostgreSQL 16/PostGIS: unavailable; Alembic migration was not applied.
- Golden crop and Jodhpur solar fixtures: retained, not executed.
- Live provider integrations: not called.
- Security and performance profiling: not performed.

## Acceptance blockers

1. Install CPython 3.11 and the pinned project plus `dev`, `validation`, `app`, `agents`, and `planning` extras in a project environment. Resolve the lock set and test imports.
2. Run all unit, property, golden, and integration suites; fix failures without weakening tolerances.
3. Run PostgreSQL 16/PostGIS migration and repository tests.
4. Complete P01–P08 acceptance before treating P09–P16 as a valid continuation.
5. Replace P09's callback harness with a complete coupled engine, persistent sim-run and state deltas, shared-resource water allocation, and event outbox/scheduler.
6. Complete P10 generators, posterior/economic uncertainty integration, convergence and sensitivity confidence intervals.
7. Complete P11 posterior fitting, blocked validation, persisted candidate promotion/rollback and a promoted residual learner. Current ridge helper is exploratory only.
8. Complete P12 Pyomo/HiGHS MILP and robust/chance constraints; current enumerated solver is limited to small option spaces.
9. Persist P13 records and connect error attribution to hindcasts and measured outcomes.
10. Complete P14 tool execution timeout/retries, worker prompts/catalogue, human interrupt/resume, PostgreSQL checkpointing, and refusal/injection/evaluation suites.
11. Complete P15 route coverage, authentication/RBAC, idempotency storage, job queue, upload content inspection, and interactive bilingual UI.
12. Complete P16 CI, security review, profiling, field-validation reporting, and release gates.

Until these checks pass, scientific outputs remain development-only and must retain their model fidelity, provenance, placeholder, and validation banners.
