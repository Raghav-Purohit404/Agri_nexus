"""
FILE: farm_twin/models/crop/aquacrop_native.py
PURPOSE: Level-1 crop engine ("AquaCrop-equivalent", water-driven). The orchestrator that runs one plot-season day by day.
IT MUST BE AN ORIGINAL IMPLEMENTATION written from this specification (modules: phenology_roots, canopy, stress, transpiration_biomass_hi, soil/water_balance), vectorised over (scenario) axis with numba or numpy.

DAILY ORDER OF OPERATIONS [VERIFIED against the reference daily loop]:
   day = weather row (Tmax,Tmin,P,ET0,date)
   1  if date outside [planting, maturity]: only soil water balance with no crop (fallow evaporation)
   2  GDD(day); advance crop calendar (t_adj, stage)
   3  growth stage (emergence -> ... ) and `crop_alive` flag
   4  pre-irrigation-day stress/depletion check: compute TAW, Dr at start of day
   5  root development (Zr)
   6  irrigation decision (policy in interventions) -> gross applied depth
   7  water balance part 1: drainage, runoff & infiltration (CN), irrigation, infiltration to layers
   8  capillary rise / groundwater (if enabled)
   9  stress coefficients (water: exp, sto, sen, pol; aeration; temperature; salinity; nitrogen)  [stress.py]
  10  canopy development (CC) using Ks_exp/Ks_sen [canopy.py]
  11  soil evaporation (two-stage with CC shading) [water_balance]
  12  transpiration demand & actual with root extraction [transpiration_biomass_hi]
  13  biomass accumulation (dB) with all stress multipliers [transpiration_biomass_hi]
  14  harvest index / yield formation [transpiration_biomass_hi]
  15  update CropState, ledger, check mass balance, emit DailyOutput(row)
  16  maturity / death check -> season summary (yield, water use, WUE, irrigation, stress days by type)
INPUTS: plot soil layers (pedotransfer or measured), crop parameter set (library + hierarchy overrides), weather (Tmax,Tmin,P,ET0 [+Rs, u2, RH for ET0]), planting date, irrigation policy, fertility inputs, optional microclimate factors.
OUTPUTS: DailyOutput DataFrame: date, dap, gdd_cum, stage, cc, zr, theta_layers, dr_mm, taw_mm, ks_*, es_mm, tr_mm, tr_pot_mm, runoff_mm, deep_perc_mm, irr_mm, biomass_t_ha, hi_adj, yield_t_ha, n_stress, sal_stress + SeasonSummary.
SCENARIO VECTORISATION: simulate N weather scenarios simultaneously (arrays shape [N]) - target performance: 1 plot x 1 season x 100 scenarios < 1 s with numba.
VALIDATION: golden fixtures from tests/golden/ (AquaCrop Tunis wheat: rainfed yields 8.930, 8.393, 9.139, 8.776, 8.710, 8.913 t/ha for seasons 1980-85 with Sandy Loam, planting 15 Oct, FC initial water; irrigated SMT=70 % in all four stages: seasonal irrigation 36.0, 85.9, 62.2, 111.0, 50.0, 36.9 mm). Acceptance: yield +/-3 %, irrigation +/-5 mm, daily CC +/-0.01.
EXTENSIBILITY: Crop-specific modules plug via CropTraits flags: determinate/indeterminate, CropType {leafy, root, fruit/grain}, perennial (unsupported L1), legume N fixation hook (supply term in nutrients.py), C4 flag (affects WP normalisation and CO2 response).
KNOWN LIMITS TO PRINT IN EVERY REPORT: water-driven growth (no explicit light/N/P/K dynamics unless modules attached), no pest/disease, no lodging, no waterlogging beyond aeration factor, no salinity feedback on soil unless salinity.py is attached.
"""
