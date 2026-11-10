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

from __future__ import annotations

from dataclasses import dataclass
from math import log

import numpy as np


@dataclass(frozen=True)
class HydraulicEstimate:
    theta_wp: float
    theta_fc: float
    theta_sat: float
    theta_dry: float
    ksat_mm_day: float
    tau: float
    theta_sd: float = 0.03
    ln_ksat_sd: float = 1.0


def saxton_rawls(
    sand_pct: float,
    clay_pct: float,
    om_pct: float,
    density_factor: float = 1.0,
    measured_ksat_mm_day: float | None = None,
) -> HydraulicEstimate:
    if not 0.9 <= density_factor <= 1.3:
        raise ValueError("density_factor must be in [0.9,1.3]")
    s, c = sand_pct / 100, clay_pct / 100
    wp0 = -0.024 * s + 0.487 * c + 0.006 * om_pct + 0.005 * s * om_pct - 0.013 * c * om_pct + 0.068 * s * c + 0.031
    wp = wp0 + 0.14 * wp0 - 0.02
    fc0 = -0.251 * s + 0.195 * c + 0.011 * om_pct + 0.006 * s * om_pct - 0.027 * c * om_pct + 0.452 * s * c + 0.299
    fc = fc0 + (1.283 * fc0**2 - 0.374 * fc0 - 0.015)
    sat0 = 0.278 * s + 0.034 * c + 0.022 * om_pct - 0.018 * s * om_pct - 0.027 * c * om_pct - 0.584 * s * c + 0.078
    sat33 = sat0 + (0.636 * sat0 - 0.107)
    sat_base = (fc + sat33) + (-0.097 * s + 0.043)
    rho_normal = (1 - sat_base) * 2.65
    rho_df = rho_normal * density_factor
    porosity_comp = (1 - rho_df / 2.65) - (1 - rho_normal / 2.65)
    fc += 0.2 * porosity_comp
    sat = 1 - rho_df / 2.65
    if not 0 < wp < fc < sat < 1:
        raise ValueError("specified pedotransfer equations produced nonphysical hydraulic values")
    lam = 1 / ((log(1500) - log(33)) / (log(fc) - log(wp)))
    ksat = measured_ksat_mm_day if measured_ksat_mm_day is not None else 1930 * (sat - fc) ** (3 - lam) * 24
    tau = min(1.0, max(0.0, round(0.0866 * ksat**0.35, 2)))
    return HydraulicEstimate(wp, fc, sat, wp / 2, ksat, tau)


def van_genuchten_theta(
    h_cm: float | np.ndarray, theta_r: float, theta_s: float, alpha_per_cm: float, n: float
) -> float | np.ndarray:
    if alpha_per_cm <= 0 or n <= 1 or not theta_r < theta_s:
        raise ValueError("invalid van Genuchten parameters")
    m = 1 - 1 / n
    h = np.abs(np.asarray(h_cm, dtype=float))
    out = theta_r + (theta_s - theta_r) / (1 + (alpha_per_cm * h) ** n) ** m
    return float(out) if out.ndim == 0 else out


def mualem_k(
    theta: float | np.ndarray,
    theta_r: float,
    theta_s: float,
    alpha_per_cm: float,
    n: float,
    ksat_cm_day: float,
    pore_connectivity: float = 0.5,
) -> float | np.ndarray:
    m = 1 - 1 / n
    se = np.clip((np.asarray(theta, dtype=float) - theta_r) / (theta_s - theta_r), 0, 1)
    term = 1 - (1 - se ** (1 / m)) ** m
    result = ksat_cm_day * se**pore_connectivity * term**2
    return float(result) if result.ndim == 0 else result
