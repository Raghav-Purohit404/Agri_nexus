"""
FILE: farm_twin/models/soil/salinity.py
PURPOSE: Root-zone salt and sodicity dynamics (missing from the water-driven crop engine; REQUIRED for arid-zone farms with saline groundwater). Level 1 = layered salt mass balance coupled to the daily water fluxes.

STATE per layer i: salt_mass_i (kg/ha; derived from measured ECe at init), na/ca/mg exchangeable and solution cations (meq/L) when SAR tracking is enabled.
UNIT FACTS (implement as constants, user-overridable): total dissolved solids TDS (mg/L) ~= 640 * EC (dS/m) for EC <= 5; ~= 800 * EC for EC > 5 (US Salinity Lab approximation) ; so salt (kg/ha) = TDS(mg/L)*water(mm)*0.01.
   derivation: 1 mm over 1 ha = 10,000 L*... = 10 m3 = 10,000 L -> mg/L * L = mg ; /1e6 -> kg ; so kg/ha = TDS_mg_L * mm * 0.01. 
INITIAL CONDITION: from ECe measured on saturation extract: salt_mass = 640*ECe*theta_sat*dz*1000*0.01 (kg/ha per layer). If only EC(1:5) is known convert with the texture-dependent factor ECe = f*EC1:5 (f ~ 5-10, sand 11..clay 5.? -> ship table CSV, ESTIMATED with +/-30 % uncertainty).
DAILY STEP (after the water balance, using its fluxes):
   1. Salt input: irrigation salt = EC_iw*640*gross_irrigation_mm*0.01 [kg/ha] added to the top layer (rain ~ 0 salt; optionally 10-20 mg/L).
   2. Advection downwards: for each layer i with downward water flux F_i (mm, from drainage module) and water content W_i (mm = 1000*theta_i*dz_i): complete-mixing displacement  concentration c_i = S_i/(W_i + F_in_i) ; salt leaving = c_i*F_i ; S_i += salt_in - salt_out. (Process top->bottom; guarantees S_i >= 0.)
   3. Evaporation and transpiration remove water but not salt -> concentration rises automatically because W decreases (no explicit term).
   4. Capillary rise (if water table): adds salt = EC_gw*640*CR*0.01 to the layer receiving the upward flux.
   5. Diagnostics: EC_sw_i = S_i/(640*W_i*0.01) [dS/m soil-water EC] ; ECe_i = EC_sw_i * theta_i/theta_sat_i  ; root-zone ECe = weighted by root fraction (and 40/30/20/10 uptake weights option) -> feeds stress.py Ks_sal.
   6. Precipitation of gypsum/CaCO3, ion-pairing and cation-exchange equilibria are NOT modelled at L1 (document; EC above ~ 8 dS/m with high SO4 overestimates solubility).
SODICITY (SAR/ESP):
   SAR_iw = Na/sqrt((Ca+Mg)/2) with concentrations in meq/L (mmol_c/L).
   ESP (%) = 100*(-0.0126 + 0.01475*SAR)/(1 + (-0.0126 + 0.01475*SAR)) (USDA Handbook 60 empirical relation) - used as quick estimate when CEC/ESP not measured.
   Level 1 sodicity: track equilibrium SAR_soil from irrigation water SAR after leaching (SAR_dw ~ SAR_iw / sqrt(LF-ish) is NOT used; use SAR_soil <- SAR_soil + (SAR_target - SAR_soil)*min(1, drainage_mm/pore_volume_mm) with SAR_target = SAR_iw*(1+8.4-pHc)-type Suarez adjustment OPTIONAL) ; effect of ESP: Ksat reduction factor fsodic = 1 - 0.015*max(0, ESP-5) (floor 0.1) when irrigation water EC < 0.7 dS/m (dispersion risk), else 1 -> literature relation, flag ESTIMATED; apply by scaling layer Ksat and tau recomputation.
LEACHING REQUIREMENT: LR = EC_iw / (5*ECe_target - EC_iw) (Rhoades, surface irrigation; ECe_target = ECe at the desired yield level, e.g. crop threshold 'a'). Gross extra water: depth_applied = ET/(1-LR), i.e. extra = ET*LR/(1-LR). Implement leaching_requirement(ec_iw, ec_e_target) and extra_water_mm(et_mm, lr); expose lr_method enum {rhoades_surface (default), drip_frequent (needs user-supplied factor)}.
RECLAMATION SIMULATION: given amendments (amendments.py) and ponded leaching depth Dw, ECe after leaching of fraction: ECe_final = ECe_0*(C_f) where the empirical Reeve-Bower: leaching depth ratio Dw/Ds (Ds = soil depth) of 1.0 removes ~70-80 % of salt for continuous ponding; use `fraction_remaining = (a)*(Dw/Ds)^-b` with (a,b) calibratable and flagged as literature-placeholder; MUST be calibrated locally; implement as simulation using step 2 with ponded infiltration instead.
OUTPUT: SalinityDaily: ece_by_layer, root_zone_ece, sar_root, esp_root, leach_fraction (season), salt_balance (kg/ha: in/out/storage).
VALIDATION: salt mass balance closure (input - output - dStorage = 0 +/- 1 kg/ha); steady-state test: constant irrigation with LF=0.2, ECiw=1.5 -> drainage-water EC -> ECiw/LF = 7.5 dS/m after enough pore volumes (tolerance 5 %).
TESTS: as above + non-negativity + unit conversion kg/ha<->dS/m round trip.
FIDELITY LABEL: Level 1 (empirical), validated only if the user supplies repeated ECe measurements; otherwise output MUST carry `unvalidated_locally`.
"""
