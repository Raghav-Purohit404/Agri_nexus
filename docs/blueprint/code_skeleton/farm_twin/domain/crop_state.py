"""
FILE: farm_twin/domain/crop_state.py
PURPOSE: CropState for one plot-season (the state vector of the crop simulator) + crop history.

IMPLEMENT: class CropState:
    crop_id, variety, planting_date, status {FALLOW, PLANTED, EMERGED, FLOWERING, YIELD_FORMATION, SENESCENCE, MATURE, HARVESTED, DEAD}
    dap (days after planting), gdd_cum, delayed_calendar_days, delayed_gdd (stress-induced phenology delay)
    canopy_cover (CC, fraction 0-1), cc_nostress, ccx_act, ccx_w, cc_prev, t_early_senescence_days, premature_senescence flag
    root_depth_m, root_cor (r_cor), biomass_t_ha, biomass_nostress_t_ha, harvest_index_ref, harvest_index_adj,
    f_pre, f_pol, f_post (HI adjustment factors), yield_formation flag, pct_lag_phase
    transpiration_cum_mm, evaporation_cum_mm, irrigation_cum_mm, drought stress counters (days of Ksw<1 by type)
    n_uptake_cum_kg_ha, n_stress_factor, salinity_stress_factor
  class CropHistoryRecord: plot_id, season, crop, variety, planting_date, harvest_date, yield_t_ha: Quantified, irrigation_mm, fertiliser applications, notes.
TESTS: serialisation round trip; CropState default for FALLOW has canopy_cover == 0.
"""
