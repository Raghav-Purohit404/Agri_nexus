"""
FILE: farm_twin/models/crop/stress.py
PURPOSE: Stress coefficients (0-1, 1 = no stress): water (4 types), temperature (heat, cold), aeration, salinity (NEW), nitrogen/fertility (NEW).

WATER STRESS (root-zone depletion fraction) - standard AquaCrop form [reference implementation confirms the structure; verify numerics against golden]:
   Dr_rel = (Dr_fraction - p_up) / (p_lo - p_up)  clipped [0,1]   (Dr_fraction = Dr/TAW)
   Ks = 1 - (exp(fshape*Dr_rel) - 1)/(exp(fshape) - 1)           (fshape = 0 -> linear Ks = 1 - Dr_rel)
   Four stresses with separate (p_up, p_lo, fshape): canopy EXPANSION (p_up1,p_lo1,fshape_w1), STOMATAL closure (p_up2, fshape_w2; p_lo=1), SENESCENCE (p_up3, fshape_w3), POLLINATION (p_up4; fshape fixed). Stomatal Ks_sto drives transpiration reduction.
   ET0-dependent threshold adjustment (crop-type dependent): p_adj = p_ref + 0.04*(5 - ET0) bounded [0,1] (applied for CropType in leafy/fruit/grain; not for ...) - Codex: implement behind a flag `adjust_p_for_et0` default True and validate on golden.
   Also compute `Ks_aer` (aeration stress): theta above (theta_sat - Aer/100) in the root zone for > 3 days -> Ks_aer = 1 - (theta - theta_aer)/(theta_sat - theta_aer) (lowest layer-weighted).
   Water-stress while germinating: no emergence if top-zGerm theta < theta_wp + GermThr*(theta_fc - theta_wp) (GermThr default 0.2); emergence delayed daily; after 'max delay' crop fails -> status DEAD.
TEMPERATURE STRESS:
   Heat (pollination): fraction of flowers failing from heat rises logistically with daily Tmax between Tmax_up (default 40 C, onset) and Tmax_lo (default 45 C, complete failure) - use the published AquaCrop logistic form and confirm it against the AquaCrop reference manual; constants live in the crop file.
   Cold (pollination): linear/logistic between Tmin_up (default 10 C) and Tmin_lo (5 C).
   Biomass temperature stress: GDD < GDD_lo -> Ks_bio temp = clip(GDD/GDD_lo,0,1)? (use the crop-file `GDD_lo` and the published `Bio-temp stress` form; default off for C3? implement as switch.)
SALINITY STRESS (NEW - the reference implementation has none):
   Maas-Hoffman threshold-slope: Yr_rel = 1 - (b/100)*(ECe_root - a) for ECe_root > a else 1 ; a = threshold (dS/m), b = slope (%/dS/m). ECe_root = depth-weighted mean root-zone saturation-extract EC (weights = root fraction per layer, optionally with water-uptake weights 40/30/20/10 for top-to-bottom quarters).
   Apply as: Ks_sal = max(0, Yr_rel). Pathway (choose ONE primary to avoid double counting): default = reduce the BIOMASS INCREMENT, dB *= Ks_sal, leave transpiration unchanged; alternative (config switch, sensitivity analysis only) = reduce transpiration demand by Ks_sal.
   Dynamic variant: use the van Genuchten-Hoffman sigmoid Yr = 1/(1 + (ECe/EC50)^p) with crop params (EC50, p) when available (literature values need sourcing; leave the table empty with provenance flag).
   The (a, b) table MUST ship as an editable CSV `crop_salt_tolerance.csv` with columns crop, a_dSm, b_pct_per_dSm, source, confidence. DO NOT invent values: seed only crops where the author-confirmed literature values are available (e.g. wheat a=6.0, b=7.1; barley a=8.0, b=5.0; cotton a=7.7, b=5.2 per FAO Irrigation & Drainage Paper 29 - UNVERIFIED in this blueprint; Codex must check against the source document and record the check) and mark others `missing` -> model raises MissingDataError unless user supplies a value.
FERTILITY (NITROGEN) STRESS (NEW):
   N stress factor from supply/demand: Ks_N = clip(N_supply_cum / N_demand_cum, 0, 1)^? - Level 1: Ks_N = clip(N_uptake_potential / N_demand, 0, 1) where N_demand = Nc(W)*dW (critical dilution curve Nc = a*W^-b, W in t DM/ha; crop-specific a,b: wheat a=5.35 %, b=0.442 [Justes 1994, UNVERIFIED here]; default for others: use a=4.5,b=0.4 flagged 'placeholder' and block production use until set) and supply from models/soil/nutrients.py. Effect: dB *= Ks_N (biomass), and canopy expansion CGC *= Ks_N^0.5 (as a config option). Also HI unaffected at Level 1.
   Phosphorus/potassium: Level 1 uses a relative-yield response (Mitscherlich): RY = 1 - exp(-c*(S + F)) with S = soil test index, F = fertiliser; c by crop - ship CSV with placeholders flagged; used as a multiplier on biomass (min of N, P, K per Liebig is NOT used; use multiplicative with caution flag).
 COMBINATION RULE (document in code): dB_actual = WP* * (Tr/ET0) * Ks_temp * min?(...) -> we use  dB = dB_water * Ks_sal * Ks_N * Ks_PK (multiplicative, each bounded below by 0) AND log the contributing factor series so an agent can explain what limited growth. Multiplicative combination is a simplification; the Level 3 DSSAT adapter gives the alternative.
TESTS: golden water stress series; Ks monotone in depletion; Ks_sal=1 below threshold, linear above, 0 at 100 % loss; combination factors logged.
"""

from __future__ import annotations

import math

from farm_twin.core.errors import MissingDataError


def water_stress(dr_fraction: float, p_up: float, p_lo: float, fshape: float) -> float:
    if not 0 <= dr_fraction <= 1 or not 0 <= p_up < p_lo <= 1 or fshape < 0:
        raise ValueError("invalid depletion or stress threshold parameters")
    dr_rel = min(1.0, max(0.0, (dr_fraction - p_up) / (p_lo - p_up)))
    if fshape == 0:
        return 1 - dr_rel
    return 1 - (math.expm1(fshape * dr_rel) / math.expm1(fshape))


def salinity_stress(ece_root_dSm: float, threshold_dSm: float | None, slope_pct_per_dSm: float | None) -> float:
    if threshold_dSm is None or slope_pct_per_dSm is None:
        raise MissingDataError(
            "Crop salt tolerance parameters are required", context={"required": ["threshold_dSm", "slope_pct_per_dSm"]}
        )
    return min(1.0, max(0.0, 1 - (slope_pct_per_dSm / 100) * max(0, ece_root_dSm - threshold_dSm)))


def nitrogen_stress(
    uptake_potential_kg_ha: float, biomass_increment_t_ha: float, biomass_t_ha: float, a_pct: float, b: float
) -> float:
    if min(uptake_potential_kg_ha, biomass_increment_t_ha, biomass_t_ha) < 0:
        raise ValueError("nitrogen and biomass values cannot be negative")
    demand_kg_ha = (a_pct * max(biomass_t_ha, 1e-9) ** (-b)) * biomass_increment_t_ha * 10
    return min(1.0, max(0.0, uptake_potential_kg_ha / max(1e-12, demand_kg_ha)))


def combine_biomass_factors(*factors: float) -> float:
    result = 1.0
    for factor in factors:
        result *= min(1.0, max(0.0, factor))
    return result
