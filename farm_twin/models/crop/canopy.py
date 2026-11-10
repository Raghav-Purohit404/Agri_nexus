"""
FILE: farm_twin/models/crop/canopy.py
PURPOSE: Canopy cover (CC, fraction of ground covered) trajectory - the engine of transpiration and growth.

PARAMETERS: CC0 (initial cover = PlantPop*SeedSize*1e-8 [fraction], with plants/ha and seed cover cm2/plant), CCx (max), CGC (canopy growth coeff, fraction/GDD or /day), CDC (decline coeff), tmax_cc (time to reach CCx), t_sen (start of senescence).

EQUATIONS [VERIFIED forms from the reference implementation]:
  A. Exponential phase (CC <= CCx/2):  CC(t) = CC0 * exp(CGC * t)           t = time since emergence (adjusted time)
  B. Saturating phase  (CC >  CCx/2):  CC(t) = CCx - 0.25*(CCx^2/CC0)*exp(-CGC*t)
  C. Senescence/decline (after t_sen): CC(t) = CCx*[1 - 0.05*(exp(tt*CDC*3.33*((CCx+2.29)/(CCx0_senesc+2.29))/(CCx+2.29)) - 1)]   (tt = time since senescence start; CC >= 0)
     Codex: reproduce this form exactly; the CDC sign convention is crop-file dependent (stored as per-day negative or positive in some libraries) -> normalise to POSITIVE rate at ingestion and test.
  D. Daily increments are computed by evaluating the curve at t and t-1 (time-shifted, adjusted for delays), then CC_new = max(CC_old, curve) while growing (cover never decreases before senescence), with the stress modifications below.
 STRESS EFFECTS (water stress coefficients Ks_exp (canopy expansion), Ks_sen (senescence), Ks_pol, Ks_sto - see stress.py):
  * Canopy expansion stress: when Ks_exp < 1 the daily canopy growth uses CGC_act = CGC * Ks_exp, and calendar progress of the canopy clock is delayed by (1 - Ks_exp) of a day (calendar crops) or (1 - Ks_exp)*GDD (thermal crops): accumulate delayed_days / delayed_gdd in CropState and subtract from t_adj.
  * CCx is also reduced: CCxAct = CCx * (something dependent on canopy-expansion stress threshold); once CC reaches the stress-reduced ceiling it is capped (`CCx_W` stored in state).
  * Early canopy senescence: when Ks_sen < 1 the canopy declines faster. Implement with the decline curve C using a CDC multiplied by a stress-dependent factor, then calibrate the factor so that the golden Tunis wheat daily CC series is matched within 0.01; record the final form in docs/model_decisions.md (the exact reference formula is not reproduced here).
  * Pollination failure and frost/heat reduce CC? NO: they act on HI only (harvest_index.py).
 Adjustment factor for canopy cover under cold stress (GDD crops with Tmin < Tmin_lethal threshold): skip unless crop file defines cold stress; leave a hook `canopy_cold_stress(cc, tmin)`.
 PERENNIAL / REGROWTH: out of scope Level 1 (document as unsupported -> raise NotImplementedError for crop.cycle=='perennial').
 API: pure functions cc_growth(...), cc_decline(...), cc_required_time(...), cc_adjusted_for_microclimate(cc, f_par_available) (identity at Level 1; shade-affected canopy comes via radiation limitation in biomass_hi.py).
 NOTE: the formulas above are the standard published AquaCrop canopy equations; Level-1 acceptance = reproduce the golden daily CC series for Tunis wheat within 0.01.
TESTS: closed-form A/B continuity at CC=CCx/2; golden CC series; CC never exceeds CCx; decline reaches 0.
"""

from __future__ import annotations

import math


def cc_curve(
    t: float,
    cc0: float,
    ccx: float,
    cgc: float,
    t_sen: float | None = None,
    cdc: float = 0.0,
    ccx0_senesc: float | None = None,
) -> float:
    if not 0 <= cc0 <= ccx <= 1 or cgc < 0:
        raise ValueError("canopy parameters outside physical bounds")
    if t_sen is not None and t > t_sen:
        start = ccx if ccx0_senesc is None else ccx0_senesc
        exponent = (t - t_sen) * abs(cdc) * 3.33 * ((ccx + 2.29) / (start + 2.29)) / (ccx + 2.29)
        return min(ccx, max(0.0, ccx * (1 - 0.05 * (math.exp(min(50, exponent)) - 1))))
    if cc0 == 0:
        return 0.0
    exp_cover = cc0 * math.exp(min(50, cgc * t))
    if exp_cover <= ccx / 2:
        return min(ccx, max(0.0, exp_cover))
    return min(ccx, max(0.0, ccx - 0.25 * (ccx**2 / cc0) * math.exp(max(-50, -cgc * t))))


def cc_growth(t: float, cc0: float, ccx: float, cgc: float, cc_prev: float = 0, ks_exp: float = 1.0) -> float:
    target = cc_curve(t, cc0, ccx, cgc * min(1.0, max(0.0, ks_exp)))
    return min(ccx, max(cc_prev, target))


def cc_decline(
    t: float, t_sen: float, ccx: float, cdc: float, ccx0_senesc: float | None = None, ks_sen: float = 1.0
) -> float:
    return cc_curve(t, ccx, ccx, 0.0, t_sen, abs(cdc) * max(1.0, 2 - ks_sen), ccx0_senesc)


def cc_required_time(target_cc: float, cc0: float, ccx: float, cgc: float) -> float:
    if not cc0 < target_cc <= ccx or cgc <= 0:
        raise ValueError("target CC must be between cc0 and ccx, with positive CGC")
    return (
        math.log(target_cc / cc0) / cgc
        if target_cc <= ccx / 2
        else -math.log((ccx - target_cc) * 4 * cc0 / (ccx**2)) / cgc
    )


def cc_adjusted_for_microclimate(cc: float, f_par_available: float) -> float:
    if not 0 <= cc <= 1 or not 0 <= f_par_available <= 1:
        raise ValueError("cover and available PAR fraction must be in [0,1]")
    return cc
