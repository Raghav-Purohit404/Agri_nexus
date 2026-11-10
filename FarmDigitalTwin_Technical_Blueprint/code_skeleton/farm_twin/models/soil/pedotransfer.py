"""
FILE: farm_twin/models/soil/pedotransfer.py
PURPOSE: Soil hydraulic properties from texture + organic matter + density when lab values for theta_wp/fc/sat/ksat are not measured.

IMPLEMENT the Saxton & Rawls (2006)-type pedotransfer regressions EXACTLY as follows (S = sand fraction 0-1, C = clay fraction 0-1, OM = organic matter in %; DF = density factor 0.9-1.3, default 1.0):
  theta_wp_pred = -0.024*S + 0.487*C + 0.006*OM + 0.005*S*OM - 0.013*C*OM + 0.068*S*C + 0.031
  theta_wp = theta_wp_pred + 0.14*theta_wp_pred - 0.02
  theta_fc_pred (33 kPa) = -0.251*S + 0.195*C + 0.011*OM + 0.006*S*OM - 0.027*C*OM + 0.452*S*C + 0.299
  theta_fc_adj = theta_fc_pred + (1.283*theta_fc_pred^2 - 0.374*theta_fc_pred - 0.015)
  theta_s33_pred = 0.278*S + 0.034*C + 0.022*OM - 0.018*S*OM - 0.027*C*OM - 0.584*S*C + 0.078
  theta_s33_adj  = theta_s33_pred + (0.636*theta_s33_pred - 0.107)
  theta_sat_base = (theta_fc_adj + theta_s33_adj) + (-0.097*S + 0.043)
  rho_normal = (1 - theta_sat_base)*2.65 ; rho_DF = rho_normal*DF
  porosity_comp = (1 - rho_DF/2.65) - (1 - rho_normal/2.65) ; theta_fc = theta_fc_adj + 0.2*porosity_comp ; theta_sat = 1 - rho_DF/2.65
  lambda = 1 / ((ln 1500 - ln 33) / (ln theta_fc - ln theta_wp))
  Ksat [mm/day] = 1930*(theta_sat - theta_fc)^(3 - lambda) * 24
  theta_dry = theta_wp / 2
  (These are the exact forms used by the AquaCrop soil-property generator; they are an empirical regression with documented RMSE ~ 0.02-0.04 m3/m3 for theta and a factor of several for Ksat -> MUST return an Uncertainty: theta sd 0.03, ln(Ksat) sd 1.0.)
  tau (drainage characteristic) from Ksat [VERIFIED in source]: tau = round(0.0866 * Ksat_mm_day**0.35, 2), clamped to [0, 1]. If a measured Ksat exists, use it here.
  Curve number defaults by hydrologic soil group: do NOT hard-code a CN table from memory. Ship an editable CSV (curve_numbers.csv: land cover x treatment x hydrologic condition x HSG A-D) seeded from the USDA TR-55 cropland tables (Codex: transcribe from the TR-55 document and verify), provenance 'literature_TR55'. HSG assignment from Ksat/texture via an editable lookup.
  Capillary-rise parameters aCR, bCR by texture class (FAO classes: sand, loamy sand, sandy loam, loam, silt loam, silty clay loam, clay...) -> CSV table, user-editable, same provenance policy.
  Also provide: van Genuchten helper (theta(h) with alpha, n, theta_r, theta_s) and Mualem-van Genuchten K(theta) for the Level 3 Richards-equation option; Rosetta-style neural PTF is Level 3 and only if a validated implementation is installed (do not re-train).
TESTS: loam (S=0.40,C=0.20,OM=2): assert theta_wp, theta_fc, theta_sat, Ksat within 1e-3 of an independent hand/spreadsheet calculation (Codex: compute once in a notebook step-by-step, commit values as golden); monotonicity: more clay -> higher wp; theta_wp < theta_fc < theta_sat always.
"""
