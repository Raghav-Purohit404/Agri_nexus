"""
FILE: farm_twin/state/engine.py
PURPOSE: FarmStateEngine - runs FarmState(t) + InterventionPlan + weather -> FarmState(t+1...T). The ONLY orchestrator of models; everything else (agents, optimiser, API) calls it.

DESIGN: operator splitting with a fixed daily order (deterministic, mass-conserving). For each day d and each plot p (plots are independent except via shared water/finance):
   1. forcing(d): weather_d (scenario draw), microclimate factors for p (agrivoltaic/ground_radiation, precomputed per day), PV config.
   2. apply interventions scheduled on d (plant, irrigate, fertilise, amend, land-use change) -> validate -> mutate a COPY of the plot state.
   3. ET0 for the plot (reference_et with microclimate scales).
   4. soil water + crop daily step (crop engine owns the water balance call) -> fluxes.
   5. salinity step (uses water fluxes), nutrients step (uses fluxes + crop demand) -> stress factors for NEXT day (one-day lag is deliberate, documented).
   6. solar hourly for the day (PV plots) - may be batched weekly for speed since PV state is not feedback-coupled to crops except via shade (precomputed).
   7. property-level: water-source ledger (sum plot irrigation demand vs availability; unmet demand reduces applied irrigation proportionally by priority list), costs/revenue events appended to cashflow ledger.
   8. month end: carbon step (RothC) using aggregated residue inputs, monthly T and moisture; recompute pedotransfer-dependent soil properties from updated OM annually.
   9. season end/harvest: yield, residue, crop history record; roll CropState to FALLOW.
   10. checks: MassBalanceError on water/salt/N/C ledgers; FarmState.validate(); emit state delta.
COUPLING GRAPH (state/coupling.py): declare which model outputs feed which inputs; engine topologically sorts; cyclic dependencies (water<->salinity<->crop) are resolved by the explicit one-day lag. Capability negotiation (models/base.py) decides which processes are active.
PARALLELISM: scenario axis vectorised inside models; plot axis via joblib/ProcessPool (no shared mutable state); 10 yr x 50 scenarios x 5 plots target < 5 min on a laptop CPU (no GPU required).
PERSISTENCE: write sim_run row first; store KPIs and quantile paths in `prediction`; state deltas in `state_delta`; failures stored with traceback hash; engine is idempotent given (input_hash, rng_seed).
APIS: run(scenario) -> ScenarioResult ; run_one(plot, start, end, weather, plan) ; step(state, forcing, actions) -> (state, fluxes) ; what_if(base_state, plan_variant) (copy-on-write; uses common random numbers) ; hindcast(plot, start, end) which runs from the last MEASURED state with ACTUAL weather and ACTUAL interventions - the basis of calibration & validation.
UNCERTAINTY PROPAGATION: engine accepts `param_draws` (from calibration posteriors) and `weather_draws`; outputs carry ensembles; engine never returns a single number as 'the answer' - returns summary stats + samples.
TESTS: 1-plot fallow year (only evaporation) mass balance; two-plot independence; reproducibility; fixture regression against crop-engine golden; hindcast uses actual not planned interventions.
"""
