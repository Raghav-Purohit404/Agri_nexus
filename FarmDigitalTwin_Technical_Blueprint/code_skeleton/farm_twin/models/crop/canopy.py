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
