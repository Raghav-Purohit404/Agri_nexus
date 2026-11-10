"""
FILE: farm_twin/domain/soil_state.py
PURPOSE: SoilState - everything the soil/water/carbon/nutrient/salinity models read and write, PER LAYER.

IMPLEMENT: class SoilLayer (all fields Quantified):
    top_m, bottom_m (layers default to 0.1 m compartments to 2.0 m; allow user layering from soil report horizons)
    sand_pct, silt_pct, clay_pct, bulk_density_g_cm3, om_pct or oc_pct, coarse_fragment_pct
    theta (current), theta_wp, theta_fc, theta_sat, theta_dry, ksat_mm_day, tau (drainage characteristic, see models/soil/water_balance.py)
    ph, ec_e_dSm (saturated-paste EC), ec_1to5, sar, esp_pct, cec_cmolc_kg, caco3_pct
    n_nitrate_kg_ha, n_ammonium_kg_ha, p_olsen_mg_kg, k_exch_mg_kg (or ammonium-acetate K), micro: zn, fe, mn, cu, b, s (mg/kg)
    salt_mass_kg_ha (derived/state), na_exch, ca_exch, mg_exch
    rothc_pools_tC_ha: {DPM,RPM,BIO,HUM,IOM}  (topsoil layer(s) only)
  class SoilState: layers: list[SoilLayer]; surface_storage_mm; water_table_depth_m|None;
    curve_number; rew_mm; evap_layer_depth_m; stage2_evaporation flag; w_surf; w_stage2   (evaporation state, see models/soil/water_balance.py)
    methods: total_available_water_mm(root_depth_m), depletion_mm(root_depth_m), soc_stock_tC_ha(depth), to_arrays() (vectorised views).
RULES: when only topsoil lab data exist, deeper layers are ESTIMATED by pedotransfer/regional priors with explicit uncertainty; never MEASURED.
TESTS: TAW for 1.0 m of loam equals sum over layers of 1000*(theta_fc-theta_wp)*dz.
"""
