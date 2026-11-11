# Changelog

## Unreleased — P09–P16 continuation
- Added persistence adapters for simulation lifecycle, interventions, approval decisions, outcomes, calibration history, audit entries, and snapshot/delta reconstruction.
- Tightened soil water invariants and optimizer handling of incomplete/non-contiguous choices.
- Updated whole-edition implementation status and recorded that post-edit validation was intentionally not run per user direction.

## Unreleased

- Preserved the supplied Farm Digital Twin blueprint at `docs/blueprint/`.
- Added Python-only P01–P08 domain, persistence, geospatial/provider, scientific-kernel, solar, and finance foundations.
- Added migration and local PostGIS 16 Compose configuration.
- Added explicit implementation and scientific fidelity status documentation; no runtime test results are claimed because the requested Python 3.11 environment and Docker are unavailable.

## P09–P16 implementation note (2026-11-10)
- Added initial state/coupling, uncertainty, calibration/ML, allocation/VOI, feedback, governance/tool, API, and Streamlit boundaries.
- Added whole-edition P09–P16 status and acceptance blockers. These are implementation foundations, not accepted releases; tests and integrations remain unexecuted.
# Unreleased — Edition 1 coding continuation

- Added a runnable Streamlit demo that constructs an example FarmState, computes FAO-56 ET₀ and a layered one-day soil-water transition, and optionally evaluates clear-sky PV and explicit-input cashflow scenarios. Demo values remain ESTIMATED/user-supplied, with no crop-yield recommendation.
- Fixed Python 3.11 Pydantic annotation resolution for intervention dates and corrected payback to remain undefined when there is no initial investment to recover.

- Added optional learning dependencies for emcee, LightGBM, scikit-learn, and PostgreSQL LangGraph checkpoints; added a top-level `requirements.txt` editable install profile.
- Added a small-parameter emcee posterior runner, explicit ABC quantile rejection (not mislabeled as full ABC-SMC), and finite-sample split-conformal intervals.
- Replaced the ridge residual candidate with a shallow LightGBM correction trained against the physical-model residual using a chronological holdout, an extrapolation envelope, and hash-checked text artifacts.
- Added import-configured ASGI and persistent worker entry points; synchronous job handlers execute off the event loop.
- Expanded Docker Compose and added a Python 3.11 non-root image definition. The deployment requires explicit application identity/service and scientific worker factories.
- Corrected the quality endpoint to avoid treating every registered variable as a requirement and fixed recommendation audit before-state capture.
- No tests, lint, type checks, migrations, container builds, or DB operations were run during this coding pass.

# Unreleased

- Added a responsive React/TypeScript plot planner UI with polygon editing foundations, SVG layout, zone locking, undo/redo, drip overlays, explanation panels, and fixture API boundary. The planner demo is explicitly synthetic; see `frontend/RESULT.md` for tested functionality and open items.
