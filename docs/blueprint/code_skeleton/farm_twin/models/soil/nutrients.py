"""
FILE: farm_twin/models/soil/nutrients.py
PURPOSE: Soil fertility (NPK) module - NEW; the reference crop engine does not model fertility. Level 1 is mechanistic for N (largest, most mobile), empirical for P and K.

NITROGEN (daily, per layer i): pools NH4_i, NO3_i (kg N/ha). Fluxes:
  1. Fertiliser: urea -> hydrolysis to NH4: first order k_hyd = 0.4 /day at 25 C (prior; temperature factor f_T = 2^((T-25)/10)); ammonia volatilisation from surface-broadcast urea = frac_vol * urea_N_remaining_surface where frac_vol prior 0.15 +/- 0.10 increasing with pH>7.5 and dry soil surface and absent when incorporated/irrigated within 24 h (flag: priors, calibrate). DAP: NH4 + P; MOP: K.
  2. Nitrification NH4 -> NO3: rate = k_nit * f_T * f_theta * NH4 ; k_nit = 0.2 /day prior; f_theta = 0 below theta_wp, rising to 1 at 0.6*theta_sat-ish (piecewise linear), falling to 0.5 at saturation.
  3. Mineralisation/immobilisation from organic matter, linked to carbon model: for each decomposed pool flux (monthly RothC -> distribute to days by the daily rate factor), N_min = sum_pools [C_decomp_pool/CN_pool] - [C_to_BIO + C_to_HUM]/CN_BIOHUM ; priors CN_DPM/RPM = residue-specific (10-80; input from residue quality, cereal straw ~ 80, legume residue ~ 20, FYM ~ 15), CN_BIO = CN_HUM = 8.5. Net negative = immobilisation (limited by available mineral N). Legume N fixation: N_fix = fraction_ndfa*N_uptake_crop (priors by crop; flagged) added to crop N supply.
  4. Leaching of nitrate: downward with drainage flux F_i (mm) using the SAME complete-mixing displacement algorithm as salinity.py: leaving_i = NO3_i * F_i / (W_i + F_in_i), so water and solute transport share one tested routine. Nitrate leaving the root zone is LOST; report as leaching loss (kg N/ha).
  5. Denitrification: when theta > 0.9*theta_sat: loss = k_den*NO3 with k_den prior 0.02 /day (very uncertain; flagged), else 0.
  6. Crop uptake: demand = Nc(W)*dW (stress.py critical dilution curve) ; supply capacity per layer = (NH4_i + NO3_i) * root_frac_i * f_uptake (f_uptake <= 0.1/day... prior; calibratable) ; actual uptake = min(demand, sum capacity) ; N stress Ks_N = actual/demand cumulative (stress.py). Uptake removed in proportion to layer availability.
  7. Return of N with residues feeds the carbon module input (residue N = C_in/CN).
PHOSPHORUS & POTASSIUM (empirical L1): soil test index (Olsen P mg/kg; ammonium-acetate K) + fertiliser applied -> relative yield multiplier RY = 1 - exp(-c*(S_index + e*F)) , e = fertiliser efficiency; (c, e) crop specific; classes Low/Medium/High thresholds ship as editable CSV (user/agronomist-approved; Indian state advisories differ; NO hard-coded advisories). P fixation: residual effect decays 10-30 %/yr (prior).
MICRONUTRIENTS (Zn, Fe, B, S...): L1 = flag-only: compare soil test with critical level table (CSV, user-confirmed) -> produce `deficiency_risk` indicator and recommended amendment line items; no yield simulation (document).
FERTILISER RECOMMENDATION LOGIC (used by the agronomy agent): N rate = max(0, (N_demand_target - N_supply_soil_est - N_fix) / efficiency) ; efficiency prior 0.4-0.6 (split applications raise it); compute via model-in-the-loop: simulate rates 0..R_max in 20 kg steps under weather scenarios and pick the economically optimal rate (marginal revenue = marginal cost) with CVaR variant. Output includes uncertainty and the soil-test method compatibility check.
OUTPUT: daily mineral N by layer, fluxes (min, nit, leach, vol, denit, uptake), season N balance (inputs: fert, org, fixation, deposition ~ 5 kg/ha/yr prior; outputs: uptake, leach, vol, denit; dStorage), Ks_N series.
LEVEL-3 CROSS CHECK: external process model's soil N module (see crop/dssat_adapter.py) on a few farms.
VALIDATION: N mass balance closes within 0.5 kg N/ha; zero-drainage run -> no leaching; urea hydrolysis 1st-order analytic check; uptake never exceeds availability.
TESTS: as listed.
FIDELITY LABEL: N = Level 1 (mechanistic-simple, priors only until calibrated); P/K = Level 1 empirical; micro = indicator only.
"""
