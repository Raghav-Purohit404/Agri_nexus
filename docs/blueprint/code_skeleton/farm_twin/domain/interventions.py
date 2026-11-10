"""
FILE: farm_twin/domain/interventions.py
PURPOSE: Typed Interventions - the ONLY way state is changed by decisions.

IMPLEMENT (pydantic discriminated union on `kind`):
    Plant(plot, crop, variety, date, population, method {SOW, TRANSPLANT}), Harvest(plot, date), Irrigate(plot, date, gross_mm, method, source),
    IrrigationPolicy(plot, mode {FIXED_SCHEDULE, SOIL_MOISTURE_THRESHOLD, ET_REPLACEMENT, RAINFED}, smt_pct_taw per growth stage, max_depth_mm, interval_days, season_cap_mm),
    ApplyFertiliser(plot, date, product, kg_product_ha, N/P2O5/K2O fractions, method), ApplyOrganic(plot, date, kind {FYM, COMPOST, CROP_RESIDUE, GREEN_MANURE},
        t_dry_matter_ha, c_fraction, n_fraction), ApplyAmendment(plot, date, product {GYPSUM, SULPHUR, LIME}, kg_ha),
    ChangeLandUse(plot, date, new_use), InstallPV(plot, PVConfig, date), InstallInfra(asset), Mulch(plot, pct_cover, dates), SetIrrigationSystem(...), TillageEvent(plot, date, depth_m)
    class InterventionPlan: list[Intervention] ordered by date; validate(farm_state) (e.g. cannot Plant on a PV_GROUND plot; cannot exceed budget)
    Every intervention has `proposed_by` {USER, OPTIMIZER, AGENT:<name>}, `approval_id|None`, `status {PROPOSED, APPROVED, EXECUTED, REJECTED}`.
RULE: only status==APPROVED (or user-created) interventions may be executed against ACTUAL records; simulation may run PROPOSED plans as hypotheticals.
"""
