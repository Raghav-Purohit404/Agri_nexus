"""
FILE: farm_twin/state/coupling.py
PURPOSE: Explicit model-coupling registry and capability negotiation.

IMPLEMENT: Edge(source_model.output -> target_model.input, transform, lag_days). Registered edges (minimum set):
   weather -> reference_et ; reference_et -> crop ; microclimate -> reference_et/crop/soil_temperature ; soil_water.fluxes -> salinity, nutrients ; salinity.root_ece -> crop.Ks_sal ;
   nutrients.Ks_N,Ks_PK -> crop.dB ; crop.residue_C -> rothc.inputs ; rothc.SOC -> soil_properties(OM%) -> pedotransfer (annual) ; crop.irrigation_applied -> water_state.ledger -> finance ;
   crop.yield -> finance.revenue ; solar.energy -> finance ; ground_radiation -> crop_coupling -> (crop, et0, rothc).
   topological_order(edges, active_models) ; detect_cycles -> must be broken by an edge with lag_days >= 1 else raise.
   negotiate(required_processes, available_models) -> composition plan or raises CapabilityError listing the missing process (e.g. 'salinity requested but crop model lacks it and no salinity model registered').
TESTS: cycle detection; negotiation outputs expected composition; lag edge resolves salinity<->crop cycle.
"""
