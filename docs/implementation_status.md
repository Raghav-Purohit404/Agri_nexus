# Implementation status — Edition 1 (P01–P16)

Status key: **coded** means source exists; **unit-tested** requires a passing executed test suite; **integration-tested** requires execution against the relevant service; **scientifically validated** requires comparison to accepted references or field data. These states are distinct.

| Stage | Status | Scope present | Acceptance blockers |
|---|---|---|---|
| P01 Core domain | Coded; tests not run | Typed entities, IDs, provenance, Pint units, validation contracts | Python 3.11 dependencies and domain tests not executed; validate pydantic models and FarmState contracts. |
| P02 Database | Coded; not applied | SQLAlchemy models, repository foundations, Alembic migration, PostGIS schema | No PostgreSQL 16/PostGIS or Docker available; repository coverage and migration integrity unverified. |
| P03 GIS/providers/ingestion | Partial coded; tests not run | UTM geometry, terrain/Sentinel kernels, Open-Meteo/NASA/SoilGrids/configured market adapters, quality checks, soil report foundations | Sentinel scene download/series and robust PDF/table/unit parsing absent; live integrations and schema checks absent. |
| P04 ET0/water | Partial coded; tests not run | FAO-56 ET0, Hargreaves fallback, PTF, daily bucket and runoff | Water balance does not yet satisfy all required process ordering and boundary behavior; no fixture executed. |
| P05 Crop | Partial coded; tests not run | Crop library, phenology, canopy, stress, biomass/HI kernels, adapter boundary | Native engine not golden validated; derived daily wheat fixture missing; multiple crop values are placeholders; external executables absent. |
| P06 Soil chemistry/carbon | Partial coded; tests not run | RothC, nutrient, amendment, salinity/sodicity kernels | No validated daily coupled ledger; placeholder constants and local calibration gaps remain. |
| P07 Solar/agrivoltaics | Partial coded; golden check fails for two fixture values | Solar/PV, layout and shading/radiation/coupling foundations; solar-position fixture test for Jodhpur | At solar noon, independent pvlib and local geometry produce ~2.8° on 2026-06-21 and ~49.7° on 2026-12-21; retained fixture expects 5.39° and 50.00°. Do not change model/tolerance until reference timestamp/value is resolved. Daily energy golden not run; agrivoltaic crop response remains experimental. |
| P08 Finance | Coded; tests not run | Water/energy cost, cashflow KPIs, scenario interfaces | No textbook or integration tests executed; explicit price/tariff scenario inputs required. |

## Runtime setup

Install CPython 3.11, then from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The command above is setup guidance only and was not executed in this coding pass. Start PostgreSQL 16/PostGIS with Docker Compose, configure trusted API and worker factories, then run `alembic upgrade head`. No migration or provider request was executed in this coding pass.

## Next work

Before calling Edition 1 complete, resolve outstanding P01–P16 blockers and run complete Python 3.11 validation. Subsequent architecture begins after P16; P09 was implemented only as a partial foundation in this edition.

## P09–P16 implementation status

| Stage | Current status | Present in this edition | Outstanding acceptance work |
|---|---|---|---|
| P09 State Engine | Partial | Deterministic injected-model stepping, hindcast, state hashes/deltas, mass-balance hook, deterministic coupling order, async event bus, PostgreSQL outbox and state-history repository foundations | Composition of full scientific modules, replay/state persistence in the engine, shared-resource allocation, delivery-worker lifecycle, and acceptance tests remain. |
| P10 Uncertainty | Partial | Historical replay, block bootstrap, climate-shift and parameterized synthetic weather, summaries, nested variance, LHS and Sobol/Jansen sensitivity kernels | No calibrated station dataset or joint simulation runner; synthetic generator parameters must be supplied and empirically fitted. Convergence and confidence intervals remain. |
| P11 Calibration/ML | Partial | Hierarchical shrinkage, importance weights, emcee ensemble sampler, ABC quantile rejection (explicitly not full ABC-SMC), promotion gate/drift monitor, temporal holdout LightGBM residual candidate, finite-sample split-conformal intervals, text artifact/hash persistence | No identifiability analysis, automatic temporal cross-validation/promotion persistence, calibration report workflow, or empirical coverage. Models remain candidates and require independent gate and domain evidence. |
| P12 Optimisation/VOI | Partial | Payoff builder/Pareto filtering, enumerated CVaR and minimax regret, optional Pyomo CVaR/chance-constrained formulations, multi-year cashflow selection, EVPI/EVSI | Solver-backed formulations and scientific decision wiring are unverified; no relaxations/IIS or optimizer API integration. |
| P13 Feedback Loop | Partial | Recommendation/approval/execution/outcome lifecycle and error attribution | Ledger is in-memory; persistence, actual-weather hindcast, prediction linking, calibration-candidate review, scheduler, and reporting remain. |
| P14 Tools/Agents | Partial | Typed tool/agent state, allowlists, HMAC approval tokens, optional LangGraph orchestration, numeric evidence matcher | Tokens/audit are process-local; timeout, supervisor-worker plan, resume/checkpoint persistence, complete tool inventory, and eval suite remain. |
| P15 API/UI | Partial | FastAPI DB application service, idempotency storage, Postgres leased job queue/worker boundary, optional OIDC adapter, request limits and uploads; Streamlit Python client, Dockerfile and Compose service definitions | Deployment must inject trusted auth/service/worker factories; parser, scanner, scientific job handlers, complete API contracts and UI workflows are not available by default. No deployment run. |
| P16 Hardening/Evals | Not complete | Runtime factory boundaries, non-root container, dependency inventory, limitation and evaluation documentation | No security review, threat model completion, profiling, full-edition regression, field-validation dashboard, release criteria, or actual deployment verification. |

P09–P16 source and contracts are still partial. The current coding pass did not execute any checks or database operations as requested. Do not mark any new stage unit-tested, integration-tested, or accepted until later validation under Python 3.11 with the corresponding extras and required services.
