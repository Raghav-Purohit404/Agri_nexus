# Requirements

## Functional (F)
F1 Define plots by map, GeoJSON/KML/Shapefile import, or dimensions; area computed in local metric CRS.
F2 Ingest soil reports (CSV/XLSX/PDF/scan), water tests, weather, satellite, prices, tariffs; confirm extracted values with the user.
F3 Maintain FarmState with five-way provenance (measured, imported, estimated, model-predicted, missing).
F4 Estimate missing soil hydraulic properties by pedotransfer with uncertainty.
F5 Simulate daily soil water, crop growth/yield, salinity/sodicity, N/P/K indicators, monthly soil carbon, hourly PV, agrivoltaic shading.
F6 Run weather x parameter x price ensembles; report distributions, tail risk, variance attribution.
F7 Optimise allocation across plots and years (E[NPV], CVaR, water, carbon), return a Pareto frontier and decision stability.
F8 Rank measurements by value of information.
F9 Close the loop: outcomes -> error attribution -> calibration -> promotion gate -> rollback.
F10 Multi-agent assistant with tool grounding, approvals, audit.
F11 UI mobile-first, English/Hindi, units switchable.
F12 Fidelity transparency: every report states which model level/validation status produced it.

## Non-functional (N)
N1 Reproducibility: sim_run records config hash, input hash, seed, model + parameter versions.
N2 Performance: 1 plot x 1 season x 100 scenarios < 1 s; 10 yr x 50 scen x 5 plots < 5 min on a laptop CPU; no GPU needed.
N3 Security: RBAC, append-only audit, secrets via env, upload scanning, prompt-injection resistance.
N4 Offline tolerance: cached data, queued observations.
N5 Licensing hygiene: no GPL code vendored; GPL systems only across a process/API boundary (see licence analysis).
N6 Testability: pure kernels, golden fixtures, property-based tests, twin-experiment calibration tests.
