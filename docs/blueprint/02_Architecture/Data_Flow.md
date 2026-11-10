# Data Flow (end to end)

1. Onboarding: user -> Intake agent -> Property/Plot (area in local CRS).
2. Data room: uploads/providers -> ingestion -> validation -> `observation` (measured/imported) + `estimate` (pedotransfer, priors) -> quality report + completeness per model.
3. Quality gate: insufficient data -> VOI-ranked request OR explicit "proceed with assumptions".
4. Initial FarmState built (layers, pools, salts, N) with provenance.
5. Candidate options generated per plot (crop bundles, PV, agrivoltaic, reclaim, fallow).
6. Simulation: weather ensemble x parameter draws -> engine -> payoff table (NPV, water, carbon, ECe, capex).
7. Optimiser (MILP CVaR) -> Pareto + stability.
8. Validation gate attaches fidelity warnings -> Explainer -> report -> approval interrupt.
9. Approved plan executed by user; interventions & observations logged.
10. Outcomes -> error attribution (weather vs management vs model) -> calibration -> promotion gate -> parameter hierarchy updated -> next cycle.
